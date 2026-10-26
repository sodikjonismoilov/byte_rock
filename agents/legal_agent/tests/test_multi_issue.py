import pytest
from agents.planner import make_plan
from agents.researcher import research
from models.schemas import LegalIssueTask, InvestigationContext, EvidenceItem
from workflow import LegalResearchWorkflow


@pytest.mark.parametrize('issue,kind,source_id', [
    ('mold pests leaks','complaint','hpd-allergens'),
    ('DOB construction occupancy','permit','dob-occupancy'),
    ('eviction warrant','warrant','courts-eviction'),
    ('housing court litigation NYSCEF','case_filing','courts-records'),
    ('rent regulation','other','hcr-rent-regulation'),
])
def test_issue_sources(heat_task, issue, kind, source_id):
    task = heat_task.model_copy(update={'question':issue,'issue_types':[issue],'evidence_ids':[]})
    context = InvestigationContext(evidence=[EvidenceItem(evidence_id='e',kind=kind,source='fictional',description=issue,building_address=task.building.address,metadata={'issue':issue})])
    plan = make_plan(task,context)
    draft = research(task,context,plan)
    assert source_id in {h.source.id for h in draft.retrieved_sources}
    assert all(f.confidence != 'high' for f in draft.findings)
    if 'rent' in issue:
        assert any('unit' in n or 'apartment' in n for f in draft.findings for n in f.notes)


def test_address_first_covers_categories_without_inventing_problems(heat_task,heat_context):
    task = heat_task.model_copy(update={'question':'Due diligence before signing a lease','issue_types':[]})
    result = LegalResearchWorkflow().run(task,heat_context)
    assert len(result.findings) == 7
    assert result.status.value == 'inconclusive'
    assert result.tool_calls <= 10
    assert any(f.sufficiency == 'insufficient' for f in result.findings)


def test_missing_evidence_ids_do_not_select_unrelated_records(heat_task,heat_context):
    task = heat_task.model_copy(update={'evidence_ids':['absent']})
    result = LegalResearchWorkflow().run(task,heat_context)
    assert not result.evidence_ids
    assert result.status.value == 'inconclusive'


def test_query_and_plan_differ(heat_task,heat_context):
    from unittest.mock import Mock
    from tools.legal_search import LegalSearchTool
    spy = Mock(wraps=LegalSearchTool())
    first = make_plan(heat_task,heat_context)
    research(heat_task,heat_context,first,spy)
    queries = [c.args[0] for c in spy.search.call_args_list]
    spy.reset_mock()
    other = heat_task.model_copy(update={'question':'DOB permits','issue_types':['construction']})
    second = make_plan(other,heat_context)
    research(other,heat_context,second,spy)
    assert first.model_dump() != second.model_dump()
    assert queries != [c.args[0] for c in spy.search.call_args_list]
