from unittest.mock import Mock

from agents.planner import make_plan
from agents.researcher import research
from models.schemas import EvidenceKind, InvestigationContext, LegalIssueTask, LegalSourceHit
from tools.legal_search import LegalSearchTool


def test_researcher_distinguishes_complaints_and_violations(
    heat_task: LegalIssueTask, heat_context: InvestigationContext, search_tool: LegalSearchTool
) -> None:
    plan = make_plan(heat_task, heat_context)
    draft = research(heat_task, heat_context, plan, search_tool=search_tool)
    kinds = set(draft.findings[0].evidence_kinds)
    assert EvidenceKind.COMPLAINT in kinds
    assert EvidenceKind.CONFIRMED_VIOLATION in kinds
    assert draft.findings[0].treats_complaint_as_violation is False
    assert "not confirmed" in draft.findings[0].summary.lower() or "Complaint record" in draft.findings[0].summary
    assert draft.reasoning_mode == "demo_deterministic"
    assert any("DEMO_DETERMINISTIC" in note for note in draft.findings[0].notes)


def test_researcher_cites_only_retrieved_sources(
    heat_task: LegalIssueTask, heat_context: InvestigationContext, search_tool: LegalSearchTool
) -> None:
    plan = make_plan(heat_task, heat_context)
    draft = research(heat_task, heat_context, plan, search_tool=search_tool)
    retrieved = {hit.source.id for hit in draft.retrieved_sources}
    for finding in draft.findings:
        for conclusion in finding.legal_conclusions:
            assert set(conclusion.source_ids) <= retrieved


def test_researcher_uses_mocked_search_tool(
    heat_task: LegalIssueTask, heat_context: InvestigationContext, search_tool: LegalSearchTool
) -> None:
    source = search_tool.sources[0]
    fake_tool = Mock()
    fake_tool.search.return_value = [
        LegalSourceHit(source=source, score=9, matched_terms=["heat"]),
    ]
    plan = make_plan(heat_task, heat_context)
    draft = research(heat_task, heat_context, plan, search_tool=fake_tool)
    assert fake_tool.search.called
    assert draft.retrieved_sources[0].source.id == source.id
