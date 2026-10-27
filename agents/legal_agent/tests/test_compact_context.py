"""Compact model context: bounded size, lossless conflict grouping, citation domain, budget guard."""
import json
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from agents.model_agents import ModelAgents
from citations import selection_schema
from context import MAX_SHOWN_RECORDS, agent_context, conflict_components, context_bytes
from models.identity import IdentityResult
from models.reconciliation import EvidenceConflict, ReconciliationResult
from models.schemas import EvidenceItem, InvestigationContext, LegalIssueTask, ResearchPlan
from tools.execution import ExecutionStopped
from tools.llm import request_budget, request_size

OUTPUTS = Path(__file__).resolve().parents[3] / 'outputs'
# Saved live runs (243 records / 329 conflict pairs and 332 records / 66 pairs).
FIXTURES = {'686 3 AVE': '20261027T010007027879Z_ede05905-0f4b-426a-9b84-704a3d60c530',
            '337 E 49 ST': '20261027T010715417102Z_82889544-50e3-48dd-b3b8-ae43f2a422dd'}
QUESTION = 'Due diligence before signing: interpret accepted property records with explicit coverage and legal applicability limits.'


@pytest.fixture(autouse=True)
def default_limits(monkeypatch):
    for key, value in {'LEGAL_CONTEXT_MAX_BYTES': '60000', 'LEGAL_CONTEXT_MAX_TOKENS': '60000', 'LEGAL_MODEL_MAX_TOKENS': '100000'}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv('LEGAL_MODEL_PAYLOAD_MAX_BYTES', raising=False)


def task_for(evidence, address='1 TEST ST'):
    return LegalIssueTask(task_id='t', question=QUESTION, building=dict(address=address), evidence_ids=[e.evidence_id for e in evidence])


def fixture_building(name):
    path = OUTPUTS / FIXTURES[name] / 'investigation_report.json'
    if not path.exists():
        pytest.skip('saved run not available')
    report = json.loads(path.read_text())
    evidence = [EvidenceItem.model_validate(e) for e in report['evidence_audit']]
    context = InvestigationContext(data_mode=report['data_mode'], data_provider=report['provider'],
        identity=IdentityResult.model_validate(report['identity']), evidence=evidence, source_coverage=report['coverage'],
        reconciliation=ReconciliationResult.model_validate(report['legal_assessment']['reconciliation']),
        as_of=date.fromisoformat(report['generated_at'][:10]))
    return task_for(evidence, report['identity']['canonical_address']), context


def synthetic_building(scale=1):
    """243 records / 150 accepted / ~329 conflict pairs at scale 1; everything doubles at scale 2."""
    evidence, accepted, held = [], [], []
    for i in range(243 * scale):
        eid = f'wvxf-dwi5:{2000000 + i}'
        closed = i % 4 == 1
        evidence.append(EvidenceItem(evidence_id=eid, kind='complaint' if i % 3 else 'confirmed_violation', source='Department of Housing Preservation and Development (HPD) via zetaris',
            date=date(2015, 1, 1) + timedelta(days=i * 11), description=f'NOVDESCRIPTION: record {i} ' + 'boiler heat hot water repair ' * 3,
            status='VIOLATION DISMISSED' if closed else 'NOV SENT OUT', building_address='1 TEST ST',
            metadata={'source_url': f'https://data.cityofnewyork.us/resource/wvxf-dwi5.json?id={i}', 'origin_record_id': str(i), 'issue': 'heat', 'raw_record': {'x': 'y' * 500}}))
        (accepted if i % 8 < 5 else held).append(eid)
    closed_ids = [e for i, e in enumerate(i.evidence_id for i in evidence) if i % 4 == 1 and e in accepted]
    open_ids = [e for i, e in enumerate(i.evidence_id for i in evidence) if i % 4 != 1 and e in accepted]
    pairs = [(c, o) for c in closed_ids[:12 * scale] for o in open_ids[:28]][:329 * scale]
    coverage = [{'source': f'src_{n}', 'title': f'Source {n}', 'status': 'retrieved', 'complete_for_filter': True, 'records_returned': n,
        'historical_coverage': 'long dataset description ' * 40, 'historical_extent_verification': 'Not independently audited.',
        'attempts': [{'filter': 'x' * 120, 'rows': n}] , 'limitations': []} for n in range(20)]
    rec = ReconciliationResult(accepted_ids=accepted, quarantined_ids=held, historical_ids=[e.evidence_id for e in evidence],
        conflicts=[EvidenceConflict(category='condition_status_disagreement', evidence_ids=list(p),
            explanation='Records differ in date/status (2015-01-01/NOV SENT OUT; 2016-01-01/VIOLATION DISMISSED). Inspection or closure is a point-in-time result. Neither proves nor disproves an ongoing condition.') for p in pairs],
        limitations=['No complete public-record coverage is asserted.'])
    ctx = InvestigationContext(data_mode='live', data_provider='zetaris', evidence=evidence, source_coverage=coverage, reconciliation=rec,
        unresolved_questions=['Is the current condition corrected?'])
    return task_for(evidence), ctx, pairs


def test_conflict_grouping_is_lossless():
    _, ctx, pairs = synthetic_building()
    groups = conflict_components(ctx.reconciliation.conflicts, ctx.evidence)
    where = {eid: n for n, g in enumerate(groups) for eid in g['evidence_ids']}
    assert all(where[a] == where[b] for a, b in pairs)  # Every original pair sits inside one component.
    assert sum(g['pair_count'] for g in groups) == len(pairs)
    assert {i for p in pairs for i in p} == set(where)
    assert all(g['date_range'] and g['explanation'] and g['statuses'] for g in groups)


def test_conflict_grouping_separates_unrelated_pairs_and_ignores_held_records():
    _, ctx, _ = synthetic_building()
    ids = [e.evidence_id for e in ctx.evidence]
    conflicts = [EvidenceConflict(category='c', evidence_ids=[ids[0], ids[1]], explanation='a'),
                 EvidenceConflict(category='c', evidence_ids=[ids[1], ids[2]], explanation='a'),
                 EvidenceConflict(category='c', evidence_ids=[ids[5], ids[6]], explanation='a'),
                 EvidenceConflict(category='c', evidence_ids=[ids[7], ids[8]], explanation='a')]
    groups = conflict_components(conflicts, ctx.evidence, held={ids[8]})
    assert sorted(g['evidence_ids'] for g in groups) == sorted([sorted(ids[:3]), sorted([ids[5], ids[6]]), [ids[7]]])
    assert ids[8] not in {i for g in groups for i in g['evidence_ids']}


@pytest.mark.parametrize('name', FIXTURES)
def test_saved_runs_fit_default_budget_and_keep_mandatory_fields(name):
    task, ctx = fixture_building(name)
    payload = agent_context(task, ctx)
    assert context_bytes(payload) < 60000
    registry = {e.evidence_id for e in ctx.evidence}
    held = set(ctx.reconciliation.rejected_ids + ctx.reconciliation.quarantined_ids)
    shown = payload['reference_domains']['evidence_ids']
    assert 0 < len(shown) <= MAX_SHOWN_RECORDS and set(shown) <= registry - held
    assert shown == [e['evidence_id'] for e in payload['evidence']]
    assert payload['identity']['verification_status'] and payload['identity']['canonical_address']
    counts = payload['reconciliation']['counts']
    assert counts['conflict_pairs'] == len(ctx.reconciliation.conflicts) and counts['quarantined'] == len(ctx.reconciliation.quarantined_ids)
    assert not {i for g in payload['reconciliation']['conflict_groups'] for i in g['evidence_ids']} & held
    assert payload['records']['total'] == len(registry - held)
    assert all('historical_coverage' not in c and 'attempts' not in c for c in payload['coverage'])
    assert {c['source']: (c['status'], c['complete_for_filter']) for c in payload['coverage']} == {c['source']: (c['status'], c['complete_for_filter']) for c in ctx.source_coverage}
    assert 'not proof of complete historical agency coverage' in payload['coverage_caveat']
    selection = payload['selection']
    assert selection['records_not_shown'] == len(registry - held) - len(shown) > 0
    assert f"{selection['records_not_shown']} more records not shown" in selection['partial_list']
    assert held.isdisjoint(shown) and held.isdisjoint(selection['omitted_evidence_ids'])


@pytest.mark.parametrize('name', FIXTURES)
def test_saved_runs_planner_and_critic_requests_fit_cap(name):
    task, ctx = fixture_building(name)
    seen = {}
    adapter = Mock()
    adapter.complete.side_effect = lambda schema, payload: seen.setdefault('payload', payload) and (_ for _ in ()).throw(ExecutionStopped('captured'))
    with pytest.raises(ExecutionStopped, match='captured'):
        ModelAgents(adapter).plan(task, ctx)
    assert request_size(ResearchPlan, seen['payload']) <= request_budget() == 60000


@pytest.mark.parametrize('scale', [1, 2])
def test_synthetic_building_and_double_stay_under_budget(scale):
    task, ctx, pairs = synthetic_building(scale)
    payload = agent_context(task, ctx)
    assert len(pairs) == 329 * scale
    assert context_bytes(payload) < 60000
    assert len(payload['evidence']) <= MAX_SHOWN_RECORDS
    # Mandatory part is bounded by conflicted IDs, not by pair count or record count.
    mandatory = context_bytes({**payload, 'evidence': [], 'reference_domains': {}})
    assert mandatory < 20000


def test_shown_ids_are_registry_subset_and_conflicted_records_rank_first():
    task, ctx, pairs = synthetic_building()
    payload = agent_context(task, ctx)
    conflicted = {i for p in pairs for i in p}
    shown = payload['reference_domains']['evidence_ids']
    assert set(shown) <= {e.evidence_id for e in ctx.evidence}
    assert set(shown) <= conflicted  # 30 rows are all taken from the conflicted records first.


def test_id_that_was_not_shown_cannot_be_cited():
    task, ctx, _ = synthetic_building()
    payload = agent_context(task, ctx)
    shown = payload['reference_domains']['evidence_ids']
    registry_only = next(e.evidence_id for e in ctx.evidence if e.evidence_id in ctx.reconciliation.accepted_ids and e.evidence_id not in shown)
    wire = selection_schema([], shown)

    def draft(eid):
        return json.dumps({'task_id': 't', 'findings': [{'finding_id': 'f1', 'issue': 'heat', 'summary': 's', 'evidence_ids': [eid]}], 'evidence_ids_used': [eid]})
    wire.model_validate_json(draft(shown[0]))
    with pytest.raises(ValidationError):
        wire.model_validate_json(draft(registry_only))
    # Server-side checks still use the full registry: the unseen ID is a real registry member, not an invented one.
    assert registry_only in {e.evidence_id for e in ctx.evidence}


def test_critic_receives_only_cited_rows():
    task, ctx, _ = synthetic_building()
    cited = [ctx.evidence[2].evidence_id, ctx.evidence[3].evidence_id]
    payload = agent_context(task, ctx, evidence_ids=cited)
    assert {e['evidence_id'] for e in payload['evidence']} <= set(cited)
    assert agent_context(task, ctx, evidence_ids=[])['evidence'] == []


def test_mandatory_budget_guard_still_stops_instead_of_truncating():
    task, ctx, _ = synthetic_building(2)
    with pytest.raises(ExecutionStopped, match='Mandatory identity, uncertainty and provenance context exceeds budget'):
        agent_context(task, ctx, max_bytes=4000)
    ctx.unresolved_questions = ['unknown ' * 9000]
    with pytest.raises(ExecutionStopped, match='Mandatory'):
        agent_context(task, ctx)
