from __future__ import annotations

if __package__ and __package__.startswith("agents.legal_agent"):
    from ..agents.scope import categories, QUERIES
else:
    from agents.scope import categories, QUERIES
if __package__ and __package__.startswith("agents.legal_agent"):
    from ..models.schemas import (
        CriticReport,
        InvestigationContext,
        LegalIssueTask,
        ResearchPlan,
        ResearchQuestion,
    )
else:
    from models.schemas import (
        CriticReport,
        InvestigationContext,
        LegalIssueTask,
        ResearchPlan,
        ResearchQuestion,
    )

ISSUE_TOPICS = {
    "heat": ["heat", "temperature", "habitability"],
    "hot water": ["hot water", "water", "habitability"],
    "water": ["water", "plumbing"],
    "pest": ["pests", "mice", "rats", "cockroaches"],
    "mice": ["pests", "mice"],
    "roach": ["pests", "cockroaches"],
    "lead": ["lead", "lead-based paint"],
    "rent": ["rent stabilization", "rent reduction", "overcharge"],
    "habitability": ["habitability", "repairs"],
}


RISK_CATEGORIES = ('habitability','building_safety','fire_safety','housing_enforcement',
                   'eviction_litigation','property_identity','tenant_protections')


def plan_sources(registry, goals=()):
    """Provider-neutral source selection for the Conductor; not another agent.

    Identity is always first. Full diligence selects all families; focused goals
    can skip irrelevant sources, which remain visible as not selected in reports.
    """
    selected=set(goals or RISK_CATEGORIES)
    if not selected <= set(RISK_CATEGORIES):
        raise ValueError('Unknown investigation goal')
    selected.add('property_identity')
    if not registry.get('hpd_buildings',{}).get('enabled',True):
        raise ValueError('Official identity source is disabled')
    keys=[k for k in ('hpd_buildings','hpd_registrations','registration_contacts') if k in registry and registry[k].get('enabled',True)]
    keys += [k for k,s in registry.items() if k not in keys and s.get('enabled',True) and selected.intersection(s['categories'])]
    return {'selected_sources':keys,'goals':sorted(selected),
            'reason':'Official identity first; strongest available property identifier per source. Manual sources become coverage gaps, never fabricated cases.'}


def _detect_topics(task: LegalIssueTask) -> list[str]:
    blob = " ".join([task.question, *task.issue_types]).lower()
    topics: list[str] = []
    for keyword, mapped in ISSUE_TOPICS.items():
        if keyword in blob:
            topics.extend(mapped)
    if task.issue_types:
        topics.extend(item.lower() for item in task.issue_types)
    deduped: list[str] = []
    for topic in topics:
        if topic not in deduped:
            deduped.append(topic)
    if not deduped:
        deduped = ["habitability", "repairs", "complaints", "violations"]
    if "complaints" not in deduped:
        deduped.append("complaints")
    if "violations" not in deduped:
        deduped.append("violations")
    return deduped


def make_plan(
    task: LegalIssueTask,
    context: InvestigationContext,
    prior_feedback: CriticReport | None = None,
    revision: int = 0,
    reasoning_mode: str = "demo_deterministic",
) -> ResearchPlan:
    """Build a research plan. Labeled demo mode unless an LLM provider is injected later."""
    topics = _detect_topics(task)
    evidence_ids = task.evidence_ids or [item.evidence_id for item in context.evidence]
    questions = [
        ResearchQuestion(
            question_id="q-classify-evidence",
            prompt=(
                "Classify each evidence item as a 311/HPD complaint, a confirmed HPD violation, "
                "a tenant report, or other. Never treat a complaint as a confirmed violation."
            ),
            recommended_tool="evidence_review",
            focus_topics=["complaints", "violations"],
            evidence_ids=evidence_ids,
        ),
        ResearchQuestion(
            question_id="q-retrieve-sources",
            prompt=(
                f"Retrieve curated NYC/NY housing sources related to: {', '.join(topics)}. "
                "Only cite identifiers returned by the local legal search tool."
            ),
            focus_topics=topics,
            evidence_ids=evidence_ids,
        ),
        ResearchQuestion(
            question_id="q-map-findings",
            recommended_tool="evidence_review",
            prompt=(
                f"Map building evidence at {task.building.address} to retrieved legal duties. "
                "Do not invent statutes, quotations, or liability conclusions."
            ),
            focus_topics=topics,
            evidence_ids=evidence_ids,
        ),
    ]

    for category in categories(task):
        questions.append(ResearchQuestion(question_id=f"issue-{category}", prompt=f"Investigate {category}; identify evidence gaps without assuming a problem.", focus_topics=[QUERIES[category]], evidence_ids=evidence_ids, dependencies=["q-classify-evidence"]))

    constraints = [
        "Cite only sources returned by local legal search.",
        "Distinguish complaints from confirmed violations.",
        "Do not invent statutes, quotations, or case citations.",
        "This output is due-diligence research, not legal advice.",
    ]
    notes = [f"[DEMO_DETERMINISTIC] Planner produced a keyword plan for topics: {', '.join(topics)}."]
    if prior_feedback is not None:
        notes.append("Revising plan using critic feedback.")
        questions.insert(
            0,
            ResearchQuestion(
                question_id="q-address-critique",
                prompt="Address critic issues: " + " ".join(prior_feedback.revision_instructions),
                focus_topics=[issue.message for issue in prior_feedback.issues] or topics,
                evidence_ids=evidence_ids,
            ),
        )
        constraints.extend(prior_feedback.revision_instructions)

    return ResearchPlan(
        task_id=task.task_id,
        revision=revision,
        objective=task.question,
        questions=questions,
        constraints=constraints,
        reasoning_mode=reasoning_mode,
        notes=notes,
    )
