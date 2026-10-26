from identity import resolve_building_identity, match_record
from models.schemas import EvidenceItem, Finding
from reconciliation import reconcile_evidence, invalidate_findings
from workflow import LegalResearchWorkflow


def item(id, status, **metadata):
    return EvidenceItem(evidence_id=id,kind='complaint',source='fixture',description='heating report',date='2026-01-01',status=status,building_address='214 East 7th Street',metadata={'issue':'heat',**metadata})


def test_disagreement_duplicates_and_history():
    r = resolve_building_identity('214 East 7th Street')
    records = [item('a','open',origin_record_id='1'),item('copy','open',origin_record_id='1'),item('inspection','no_violation')]
    result = reconcile_evidence(records,[match_record(e,r) for e in records])
    assert result.duplicate_groups == [['a','copy']]
    assert result.conflicts and all(not c.resolved for c in result.conflicts)
    assert result.historical_ids


def test_rejected_building_invalidates_dependent_findings(heat_task,heat_context):
    from unittest.mock import Mock
    from agents.researcher import research
    from agents.planner import make_plan
    wrong = item('wrong','open',bin='1000099')
    records = heat_context.evidence + [wrong]
    context = heat_context.model_copy(update={'evidence':records})
    draft = research(heat_task,heat_context,make_plan(heat_task,heat_context))
    draft.findings[0].evidence_ids.append('wrong')
    draft.evidence_ids_used.append('wrong')
    result = LegalResearchWorkflow(researcher=Mock(return_value=draft),max_revision_cycles=0).run(heat_task,context)
    assert 'wrong' in result.reconciliation.rejected_ids
    assert result.reconciliation.invalidated_finding_ids
    assert result.findings[0].valid is False
    assert not result.findings[0].legal_conclusions
    assert result.status.value != 'completed'
    assert context.evidence[-1].evidence_id == 'wrong'


def test_conflict_not_resolved_by_confirmed_violation(heat_task,heat_context):
    e = item('inspection','no_violation')
    context = heat_context.model_copy(update={'evidence':heat_context.evidence+[e]})
    task = heat_task.model_copy(update={'evidence_ids':[]})
    result = LegalResearchWorkflow().run(task,context)
    assert result.status.value == 'inconclusive'
    assert result.findings[0].contradictory_evidence_ids
