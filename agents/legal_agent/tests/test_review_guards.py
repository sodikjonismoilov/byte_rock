import pytest
from agents.planner import make_plan
from agents.researcher import research
from agents.critic import critique_draft


@pytest.mark.parametrize('claim,code',[
    ('The landlord is automatically liable.','unsupported_interpretation'),
    ('The apartment is rent stabilized.','unsupported_unit_status'),
    ('The tenant was evicted.','unsupported_eviction_stage'),
])
def test_unsupported_interpretations(heat_task,heat_context,claim,code):
    draft=research(heat_task,heat_context,make_plan(heat_task,heat_context))
    draft.findings[0].summary=claim
    report=critique_draft(heat_task,heat_context,draft)
    assert report.outcome.value=='REVISE'
    assert code in {i.code for i in report.issues}


def test_source_identifier_mismatch(heat_task,heat_context):
    draft=research(heat_task,heat_context,make_plan(heat_task,heat_context))
    draft.findings[0].legal_conclusions[0].identifiers=['N.Y. Real Prop. Law § 235-b']
    report=critique_draft(heat_task,heat_context,draft)
    assert 'citation_identifier_mismatch' in {i.code for i in report.issues}


def test_effective_dates_checked_at_incident(heat_task,heat_context):
    from datetime import date
    draft=research(heat_task,heat_context,make_plan(heat_task,heat_context))
    source_id=draft.findings[0].legal_conclusions[0].source_ids[0]
    next(h.source for h in draft.retrieved_sources if h.source.id==source_id).effective_from=date(2026,7,1)
    report=critique_draft(heat_task,heat_context,draft)
    assert 'inapplicable_authority' in {i.code for i in report.issues}


def test_duplicate_evidence_ids_rejected(heat_context):
    from models.schemas import InvestigationContext
    with pytest.raises(ValueError):
        InvestigationContext(evidence=[heat_context.evidence[0],heat_context.evidence[0]])
