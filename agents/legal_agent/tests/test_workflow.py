from unittest.mock import Mock

from agents.planner import make_plan
from agents.researcher import research
from models.schemas import (
    CriticIssue,
    CriticOutcome,
    CriticReport,
    EvidenceKind,
    Finding,
    InvestigationContext,
    InvestigationStatus,
    LegalConclusion,
    LegalIssueTask,
    ResearchDraft,
)
from tools.legal_search import LegalSearchTool
from workflow import LegalResearchWorkflow, investigate_legal_issue


def test_workflow_completes_when_confirmed_violation_exists(
    heat_task: LegalIssueTask, heat_context: InvestigationContext
) -> None:
    result = LegalResearchWorkflow().run(heat_task, heat_context)
    assert result.status == InvestigationStatus.COMPLETED
    assert result.critic_outcome == CriticOutcome.PASS
    assert result.revision_cycles == 0
    assert result.task_id == heat_task.task_id
    assert result.evidence_ids
    assert result.findings
    assert result.reasoning_mode == "demo_deterministic"


def test_public_function_returns_json_dict(
    pest_violation_task: LegalIssueTask, pest_violation_context: InvestigationContext
) -> None:
    payload = investigate_legal_issue(
        pest_violation_task.model_dump(mode="json"),
        pest_violation_context.model_dump(mode="json"),
    )
    assert payload["task_id"] == pest_violation_task.task_id
    assert payload["status"] == "completed"
    assert isinstance(payload["findings"], list)


def test_workflow_inconclusive_when_only_complaints(
    complaint_only_task: LegalIssueTask, complaint_only_context: InvestigationContext
) -> None:
    result = LegalResearchWorkflow().run(complaint_only_task, complaint_only_context)
    assert result.status == InvestigationStatus.INCONCLUSIVE
    assert result.critic_outcome == CriticOutcome.INCONCLUSIVE
    assert result.revision_cycles == 0
    assert any(issue.code == "insufficient_confirmed_evidence" for issue in result.critic_issues)


def _unsupported_draft(task: LegalIssueTask, context: InvestigationContext, search_tool: LegalSearchTool) -> ResearchDraft:
    plan = make_plan(task, context)
    good = research(task, context, plan, search_tool=search_tool)
    bad = Finding(
        finding_id="unsupported-1",
        issue="heat",
        summary="Invented legal rule.",
        evidence_ids=good.evidence_ids_used,
        evidence_kinds=[EvidenceKind.CONFIRMED_VIOLATION],
        legal_conclusions=[
            LegalConclusion(
                statement="Automatic eviction defense under RPL § 999-z.",
                source_ids=["not-a-real-source"],
                identifiers=["RPL § 999-z"],
            )
        ],
        confidence="high",
    )
    return good.model_copy(update={"findings": [bad]})


def test_critique_triggers_revision_then_pass(
    heat_task: LegalIssueTask, heat_context: InvestigationContext, search_tool: LegalSearchTool
) -> None:
    good_plan = make_plan(heat_task, heat_context)
    good_draft = research(heat_task, heat_context, good_plan, search_tool=search_tool)
    bad_draft = _unsupported_draft(heat_task, heat_context, search_tool)

    researcher = Mock(side_effect=[bad_draft, good_draft])
    workflow = LegalResearchWorkflow(researcher=researcher, search_tool=search_tool)
    result = workflow.run(heat_task, heat_context)

    assert researcher.call_count == 2
    assert result.revision_cycles == 1
    assert result.status == InvestigationStatus.COMPLETED
    assert result.critic_outcome == CriticOutcome.PASS
    assert any("revision" in note.lower() for note in result.notes)


def test_retry_limit_enforced(
    heat_task: LegalIssueTask, heat_context: InvestigationContext, search_tool: LegalSearchTool
) -> None:
    always_revise = Mock(
        return_value=CriticReport(
            task_id=heat_task.task_id,
            outcome=CriticOutcome.REVISE,
            issues=[CriticIssue(code="unsupported_legal_conclusion", message="still unsupported")],
            revision_instructions=["Remove unsupported conclusions."],
        )
    )
    workflow = LegalResearchWorkflow(critic=always_revise, search_tool=search_tool, max_revision_cycles=2)
    result = workflow.run(heat_task, heat_context)
    assert always_revise.call_count == 3
    assert result.revision_cycles == 2
    assert result.status == InvestigationStatus.INCONCLUSIVE
    assert result.critic_outcome == CriticOutcome.REVISE
    assert any(error.code == "retry_limit_reached" for error in result.errors)


def test_workflow_mocked_llm_never_called(
    heat_task: LegalIssueTask, heat_context: InvestigationContext
) -> None:
    fake_llm = Mock()
    result = LegalResearchWorkflow().run(heat_task, heat_context)
    fake_llm.assert_not_called()
    assert "DEMO_DETERMINISTIC" in " ".join(result.notes)
