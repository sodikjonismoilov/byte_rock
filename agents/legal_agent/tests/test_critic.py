from agents.critic import critique_draft
from agents.planner import make_plan
from agents.researcher import research
from models.schemas import (
    CriticOutcome,
    EvidenceKind,
    Finding,
    InvestigationContext,
    LegalConclusion,
    LegalIssueTask,
    ResearchDraft,
)
from tools.legal_search import LegalSearchTool


def test_critic_passes_supported_heat_draft(
    heat_task: LegalIssueTask, heat_context: InvestigationContext, search_tool: LegalSearchTool
) -> None:
    plan = make_plan(heat_task, heat_context)
    draft = research(heat_task, heat_context, plan, search_tool=search_tool)
    report = critique_draft(heat_task, heat_context, draft, search_tool=search_tool)
    assert report.outcome == CriticOutcome.PASS


def test_critic_rejects_unsupported_legal_conclusion(
    heat_task: LegalIssueTask, heat_context: InvestigationContext, search_tool: LegalSearchTool
) -> None:
    plan = make_plan(heat_task, heat_context)
    draft = research(heat_task, heat_context, plan, search_tool=search_tool)
    bad_finding = Finding(
        finding_id="bad-1",
        issue="heat",
        summary="Landlord is automatically liable under a fake statute.",
        evidence_ids=draft.evidence_ids_used,
        evidence_kinds=[EvidenceKind.COMPLAINT],
        legal_conclusions=[
            LegalConclusion(
                statement="Tenant may withhold all rent under RPL § 999-z.",
                source_ids=["invented-source"],
                identifiers=["RPL § 999-z"],
                supported=False,
            )
        ],
        confidence="high",
        treats_complaint_as_violation=True,
    )
    tainted = draft.model_copy(update={"findings": [bad_finding]})
    report = critique_draft(heat_task, heat_context, tainted, search_tool=search_tool)
    codes = {issue.code for issue in report.issues}
    assert report.outcome == CriticOutcome.REVISE
    assert "unsupported_legal_conclusion" in codes
    assert "complaint_as_violation" in codes


def test_critic_marks_complaint_only_inconclusive(
    complaint_only_task: LegalIssueTask,
    complaint_only_context: InvestigationContext,
    search_tool: LegalSearchTool,
) -> None:
    plan = make_plan(complaint_only_task, complaint_only_context)
    draft = research(complaint_only_task, complaint_only_context, plan, search_tool=search_tool)
    report = critique_draft(complaint_only_task, complaint_only_context, draft, search_tool=search_tool)
    assert report.outcome == CriticOutcome.INCONCLUSIVE
    assert any(issue.code == "insufficient_confirmed_evidence" for issue in report.issues)
