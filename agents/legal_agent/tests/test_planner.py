from agents.planner import make_plan
from models.schemas import CriticIssue, CriticOutcome, CriticReport, InvestigationContext, LegalIssueTask


def test_planner_includes_classification_and_citation_constraints(
    heat_task: LegalIssueTask, heat_context: InvestigationContext
) -> None:
    plan = make_plan(heat_task, heat_context)
    question_ids = {question.question_id for question in plan.questions}
    assert "q-classify-evidence" in question_ids
    assert "q-retrieve-sources" in question_ids
    assert plan.reasoning_mode == "demo_deterministic"
    assert any("complaint" in constraint.lower() for constraint in plan.constraints)
    assert any("heat" in topic for question in plan.questions for topic in question.focus_topics)


def test_planner_uses_critic_feedback(
    heat_task: LegalIssueTask, heat_context: InvestigationContext
) -> None:
    feedback = CriticReport(
        task_id=heat_task.task_id,
        outcome=CriticOutcome.REVISE,
        issues=[CriticIssue(code="unsupported_legal_conclusion", message="drop invented statute")],
        revision_instructions=["Remove invented citations."],
    )
    plan = make_plan(heat_task, heat_context, prior_feedback=feedback, revision=1)
    assert plan.revision == 1
    assert plan.questions[0].question_id == "q-address-critique"
    assert "Remove invented citations." in plan.constraints
