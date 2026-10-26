"""MOCK scenarios only; none of these rows are real NYC records."""
from datetime import UTC, datetime
import json
from unittest.mock import patch

import pytest
from identity import resolve_building_identity
from integration import board_update, review_records, root_critic
from models.identity import IdentityResult, RecordMatch
from models.schemas import CriticIssue, CriticReport
from reporting import write_report
from tools.zetaris import ColumnMap, identity_candidate, map_rows
from workflow import LegalResearchWorkflow
from agents.critic import critique_draft
from agents.researcher import research


def reviewed(context, decision='accepted'):
    return [RecordMatch(evidence_id=e.evidence_id, decision=decision, method='mock_upstream', confidence=.9, reason='Mock review', scope=e.metadata.get('scope','building')) for e in context.evidence]


def test_external_review_is_consumed_without_rematching(heat_task, heat_context):
    heat_context.record_matches = reviewed(heat_context)
    with patch('workflow.match_record', side_effect=AssertionError('Must not rematch')):
        result = LegalResearchWorkflow().run(heat_task, heat_context)
    assert result.status.value == 'completed'


def test_external_rejections_cannot_support_findings(heat_task, heat_context):
    heat_context.record_matches = reviewed(heat_context, 'rejected')
    result = LegalResearchWorkflow().run(heat_task, heat_context)
    assert not any(f.evidence_ids for f in result.findings)
    assert not board_update(result, heat_context.evidence)['legal_findings']


@pytest.mark.parametrize('mode', ['live', 'recorded_replay', 'mock'])
def test_non_sample_mode_never_uses_fictional_identity(mode, heat_task, heat_context):
    heat_context.data_mode = mode
    result = LegalResearchWorkflow().run(heat_task, heat_context)
    assert result.critic_outcome.value == 'BLOCKED'
    assert result.identity.verification_status == 'missing'


def test_incomplete_review_fails_closed(heat_task, heat_context):
    heat_context.record_matches = reviewed(heat_context)[:1]
    result = LegalResearchWorkflow().run(heat_task, heat_context)
    assert result.status.value == 'error'
    assert not result.findings


def test_live_input_cannot_explicitly_supply_fictional_identity(heat_task, heat_context):
    heat_context.identity = IdentityResult.model_validate(resolve_building_identity(heat_task.building.address))
    heat_context.data_mode = 'live'
    result = LegalResearchWorkflow().run(heat_task, heat_context)
    assert result.status.value == 'inconclusive'
    assert result.errors[0].code == 'execution_stopped'
    assert not result.findings


def test_root_bridge_keeps_quarantined_records_out(heat_task, heat_context):
    for e in heat_context.evidence:
        e.metadata['matcher_confidence'] = .9
    heat_context.evidence[0].building_address = '999 Wrong Street'
    matches, decisions = review_records(heat_context.evidence, {'address_raw':heat_task.building.address})
    heat_context.record_matches = matches
    result = LegalResearchWorkflow().run(heat_task, heat_context)
    held = heat_context.evidence[0].evidence_id
    assert decisions[0]['decision'] == 'quarantine'
    assert all(held not in f.evidence_ids for f in result.findings)


def test_bbl_review_does_not_upgrade_scope(heat_task, heat_context):
    ident = resolve_building_identity(heat_task.building.address)
    e = heat_context.evidence[0]
    e.metadata = {'bbl': ident['identifiers']['bbl'], 'scope': 'building'}
    heat_context.evidence = [e]
    heat_context.record_matches = reviewed(heat_context)
    result = LegalResearchWorkflow().run(heat_task, heat_context)
    assert result.record_matches[0].decision == 'quarantined'
    assert not any(f.evidence_ids for f in result.findings)


def test_mock_mapping_preserves_provenance_and_identity():
    mapping = ColumnMap(dataset='mock-dataset', source='Mock Zetaris view', record_id='id', address='addr', description='text', event_date='when', status='state', kind='complaint', scope='building', identifiers={'bin':'bin'}, source_url='url')
    rows = [{'id':'007', 'addr':'1 Mock St', 'text':'Heat allegation', 'when':'2026-01-01T00:00:00Z', 'state':'closed', 'bin':'1000001', 'url':None}]
    records = map_rows(rows, mapping, retrieved_at=datetime(2026,10,25,tzinfo=UTC))
    e = records[0]
    assert e.evidence_id == 'mock-dataset:007'
    assert e.metadata['origin_record_id'] == '007'
    assert e.kind.value == 'complaint' and e.status == 'closed'
    assert e.metadata['source_url'] is None
    assert not identity_candidate(e).identifiers[0].authoritative
    assert identity_candidate(e, authoritative=True).identifiers[0].record_id == '007'
    with pytest.raises(ValueError):
        map_rows(rows*2, mapping, retrieved_at=datetime.now(UTC))


def test_root_rejection_then_corrected_match_is_mock_feedback_loop():
    critic = root_critic()
    building = {'bbl':'1013570031', 'address_raw':'327 EAST 55 STREET'}
    row = dict(building, record_id='mock:1', dataset='violations', matcher_confidence=.9)
    row['bbl']='1013570032'
    assert critic.review_link(row, building)['decision'] == 'reject'
    row['bbl']=building['bbl']
    assert critic.review_link(row, building)['decision'] == 'accept'
    assert critic.review_finding({'record_ids':[]}, {'mock:1'})['rule'] == 'R9'


def test_legal_critique_revises_actual_bad_draft(heat_task, heat_context, tmp_path):
    calls = []
    def researcher(*args, **kwargs):
        draft = research(*args, **kwargs)
        calls.append(draft)
        if len(calls) == 1:
            draft.findings[0].legal_conclusions[0].statement = 'The landlord violated the law.'
        return draft
    result = LegalResearchWorkflow(researcher=researcher).run(heat_task, heat_context)
    assert result.revision_cycles == 1
    assert result.review_history[0].outcome.value == 'REVISE'
    assert result.review_history[-1].outcome.value == 'PASS'
    assert result.plans[0] != result.plans[1]
    pack = write_report(result, heat_context.evidence, tmp_path)
    assert not pack['safety_certification']
    assert json.loads((tmp_path/'sample_report.json').read_text())['result']['data_mode'] == 'sample'
    assert 'violated the law' not in (tmp_path/'sample_report.md').read_text().split('## Review history')[0]


def test_real_mode_unknown_source_version_is_unresolved(heat_task, heat_context):
    candidate = resolve_building_identity(heat_task.building.address)['candidates'][0]
    for identifier in candidate['identifiers']:
        identifier.update(authoritative=True, fictional=False)
    heat_context.identity = IdentityResult.model_validate(resolve_building_identity(heat_task.building.address, {'candidates':[candidate]}))
    heat_context.data_mode='mock'
    result = LegalResearchWorkflow().run(heat_task, heat_context)
    assert result.status.value == 'inconclusive'
    assert any(i.code == 'applicability_unresolved' for i in result.critic_issues)


def test_failed_legal_revision_is_withheld_from_report(heat_task, heat_context, tmp_path):
    def unsafe(*args, **kwargs):
        draft = research(*args, **kwargs)
        draft.findings[0].legal_conclusions[0].statement = 'The tenant is liable.'
        return draft
    result = LegalResearchWorkflow(researcher=unsafe, max_revision_cycles=0).run(heat_task, heat_context)
    assert result.critic_outcome.value == 'REVISE'
    report = write_report(result, heat_context.evidence, tmp_path)
    assert not report['board_update']['legal_findings']
    assert report['board_update']['withheld_finding_ids']
