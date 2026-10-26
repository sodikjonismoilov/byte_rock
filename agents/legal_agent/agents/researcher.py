from __future__ import annotations

if __package__ and __package__.startswith("agents.legal_agent"):
    from ..models.schemas import (
        EvidenceItem,
        EvidenceKind,
        Finding,
        InvestigationContext,
        LegalConclusion,
        LegalIssueTask,
        LegalSourceHit,
        ResearchDraft,
        ResearchPlan,
    )
else:
    from models.schemas import (
        EvidenceItem,
        EvidenceKind,
        Finding,
        InvestigationContext,
        LegalConclusion,
        LegalIssueTask,
        LegalSourceHit,
        ResearchDraft,
        ResearchPlan,
    )
if __package__ and __package__.startswith("agents.legal_agent"):
    from ..tools.legal_search import LegalSearchTool
else:
    from tools.legal_search import LegalSearchTool


def _issue_label(task: LegalIssueTask) -> str:
    if task.issue_types:
        return ", ".join(task.issue_types)
    return task.question


def _select_evidence(task: LegalIssueTask, context: InvestigationContext) -> list[EvidenceItem]:
    if __package__ and __package__.startswith("agents.legal_agent"):
        from ..identity import normalize_address
    else:
        from identity import normalize_address
    wanted = set(task.evidence_ids)
    evidence = [e for e in context.evidence if not wanted or e.evidence_id in wanted]
    if context.record_matches:
        accepted = {m.evidence_id for m in context.record_matches if m.decision == 'accepted'}
        return [e for e in evidence if e.evidence_id in accepted]
    return [e for e in evidence if normalize_address(e.building_address or '')[0] == normalize_address(task.building.address)[0]]


def _query_from_plan(plan: ResearchPlan, task: LegalIssueTask) -> str:
    topics = []
    for question in plan.questions:
        topics.extend(question.focus_topics)
    return " ".join([task.question, *task.issue_types, *topics])


def _allowed_source_ids(hits: list[LegalSourceHit]) -> set[str]:
    return {hit.source.id for hit in hits}


def _conclusions_for_issue(
    task: LegalIssueTask,
    hits: list[LegalSourceHit],
    kinds: list[EvidenceKind],
) -> list[LegalConclusion]:
    conclusions: list[LegalConclusion] = []
    has_violation = EvidenceKind.CONFIRMED_VIOLATION in kinds
    blob = " ".join([task.question, *task.issue_types]).lower()

    def add_if_present(source_id: str, statement: str) -> None:
        match = next((hit.source for hit in hits if hit.source.id == source_id), None)
        if match is None:
            return
        conclusions.append(
            LegalConclusion(
                statement=statement,
                source_ids=[match.id],
                identifiers=[match.identifier],
                supported=True,
            )
        )

    add_if_present(
        "hpd-complaints-violations",
        "A 311/HPD complaint reports a condition and is not itself a confirmed code violation; a violation is issued only if an inspector writes one.",
    )
    if "heat" in blob:
        add_if_present(
            "nyc-admin-27-2029",
            "NYC heat-season indoor temperature minima are stated in NYC Admin. Code § 27-2029.",
        )
        add_if_present(
            "hpd-heat-hot-water",
            "HPD guidance restates owner heat and hot-water duties and the 311/inspection path.",
        )
    if "hot water" in blob or "water" in blob:
        add_if_present(
            "nyc-admin-27-2031",
            "NYC Admin. Code § 27-2031 states hot-water supply requirements for covered dwellings.",
        )
    if any(term in blob for term in ("pest", "mice", "roach", "rat")):
        add_if_present(
            "nyc-admin-27-2017-4",
            "NYC Admin. Code § 27-2017.4 addresses pest violations and department-ordered eradication.",
        )
        add_if_present(
            "nyc-admin-27-2017-8",
            "NYC Admin. Code § 27-2017.8 requires integrated pest management rather than pesticides alone.",
        )
    if "lead" in blob:
        add_if_present(
            "hpd-lead-local-law-1",
            "Local Law 1 of 2004 and NYC Admin. Code § 27-2056 et seq. address lead-based paint duties in covered buildings.",
        )
    if "rent" in blob:
        add_if_present(
            "hcr-rent-regulation",
            "DHCR/HCR guidance describes rent-regulated tenants' ability to seek relief for decrease in required services.",
        )
    add_if_present(
        "rpl-235-b",
        "N.Y. Real Prop. Law § 235-b implies a warranty of habitability in residential leases.",
    )
    add_if_present(
        "mdw-78",
        "N.Y. Mult. Dwell. Law § 78 requires multiple dwellings to be kept in good repair.",
    )
    if not has_violation:
        for conclusion in conclusions:
            conclusion.statement += " Available evidence does not include a confirmed HPD violation, so no enforcement finding is asserted."
    return conclusions


def _research_one(
    task: LegalIssueTask,
    context: InvestigationContext,
    plan: ResearchPlan,
    search_tool: LegalSearchTool | None = None,
    reasoning_mode: str = "demo_deterministic",
) -> ResearchDraft:
    """Produce findings from local evidence plus curated legal retrieval."""
    tool = search_tool or LegalSearchTool()
    evidence = _select_evidence(task, context)
    hits_by_id = {
        hit.source.id: hit
        for hit in tool.search(_query_from_plan(plan, task), limit=8)
        + tool.search("hpd complaints violations inspection", limit=4)
    }
    hits = sorted(hits_by_id.values(), key=lambda hit: -hit.score)
    kinds = [item.kind for item in evidence]
    has_violation = EvidenceKind.CONFIRMED_VIOLATION in kinds
    has_complaint = EvidenceKind.COMPLAINT in kinds
    treat_as_violation = False
    confidence: str
    if has_violation:
        confidence = "medium"
    elif has_complaint or evidence:
        confidence = "low"
    else:
        confidence = "low"

    summary_parts = []
    if evidence:
        summary_parts.append(
            f"Reviewed {len(evidence)} evidence item(s) for {task.building.address}."
        )
        complaint_ids = [item.evidence_id for item in evidence if item.kind == EvidenceKind.COMPLAINT]
        violation_ids = [
            item.evidence_id for item in evidence if item.kind == EvidenceKind.CONFIRMED_VIOLATION
        ]
        if complaint_ids:
            summary_parts.append(
                f"Complaint record(s): {', '.join(complaint_ids)}. These are not confirmed violations."
            )
        if violation_ids:
            summary_parts.append(
                f"Confirmed violation record(s): {', '.join(violation_ids)}."
            )
        if not violation_ids:
            summary_parts.append("No confirmed HPD violation is present in the provided evidence.")
    else:
        summary_parts.append("No building evidence was provided.")

    if hits:
        identifiers = ", ".join(hit.source.identifier for hit in hits[:4])
        summary_parts.append(f"Retrieved legal sources include: {identifiers}.")
    else:
        summary_parts.append("Legal search returned no matching curated sources.")

    notes = [
        "[DEMO_DETERMINISTIC] Researcher mapped keywords to the local catalog; no LLM reasoning was used.",
        "Findings are due-diligence research, not a determination of legal liability.",
    ]
    if plan.revision:
        notes.append("Draft incorporates critic revision instructions by limiting citations to retrieved sources.")

    finding = Finding(
        finding_id=f"{task.task_id}-F1",
        issue=_issue_label(task),
        summary=" ".join(summary_parts),
        evidence_ids=[item.evidence_id for item in evidence],
        evidence_kinds=kinds,
        legal_conclusions=_conclusions_for_issue(task, hits, kinds),
        confidence=confidence,  # type: ignore[arg-type]
        treats_complaint_as_violation=treat_as_violation,
        notes=notes,
    )

    caveats = [
        "Zetaris and live NYC Open Data are not connected; evidence is the local fictional sample set.",
        "Only curated sources in data/legal_sources.json may be cited.",
    ]
    if not has_violation:
        caveats.append("Without a confirmed violation, legal conclusions remain limited and non-dispositive.")

    return ResearchDraft(
        task_id=task.task_id,
        plan_revision=plan.revision,
        findings=[finding],
        retrieved_sources=hits,
        evidence_ids_used=[item.evidence_id for item in evidence],
        reasoning_mode=reasoning_mode,
        caveats=caveats,
    )


def research(task, context, plan, search_tool=None, reasoning_mode="demo_deterministic"):
    if __package__ and __package__.startswith("agents.legal_agent"):
        from ..agents.scope import categories, evidence_category, QUERIES
    else:
        from agents.scope import categories, evidence_category, QUERIES
    evidence = _select_evidence(task, context)
    findings, sources = [], {}
    for category in categories(task):
        selected = [e for e in evidence if category in evidence_category(e)]
        # Unclassified evidence stays in the only issue, never silently crosses issues.
        if len(categories(task)) == 1:
            selected = evidence
        subcontext = context.model_copy(update={"evidence": selected})
        subtask = task.model_copy(update={"issue_types": [category, *task.issue_types] if len(categories(task)) == 1 else [category], "question": task.question if len(categories(task)) == 1 else QUERIES[category], "evidence_ids": [e.evidence_id for e in selected]})
        subplan = plan.model_copy(update={"questions": [q for q in plan.questions if category in q.question_id or q.question_id == 'q-address-critique']})
        draft = _research_one(subtask, subcontext, subplan, search_tool, reasoning_mode)
        finding = draft.findings[0]
        finding.finding_id = f"{task.task_id}-{category}"
        finding.issue = category
        finding.supported_facts = [f"{e.evidence_id}: {e.kind.value}, date={e.date}, status={e.status}; {e.description}" for e in selected]
        for match in context.record_matches:
            if match.evidence_id in finding.evidence_ids:
                finding.notes.append(f"{match.evidence_id}: {match.scope} scope; {match.reason}")
        finding.missing_information = ['Current conditions and complete source coverage have not been verified.']
        finding.sufficiency = 'partial' if selected else 'insufficient'
        finding.follow_up_tasks = [f"Request current {category} records for the resolved building from the data investigator."]
        if category in {'eviction', 'litigation'}:
            finding.notes.append('A filing is an allegation; decision, judgment, warrant and executed eviction are distinct stages. Entity litigation alone does not establish property linkage or wrongdoing.')
        if category == 'rent_regulation':
            finding.notes.append('Building-level data cannot establish apartment rent-regulated status; request unit rent history and applicable orders.')
        if context.reconciliation:
            for conflict in context.reconciliation.conflicts:
                if set(conflict.evidence_ids) & set(finding.evidence_ids):
                    finding.contradictory_evidence_ids.extend(conflict.evidence_ids)
                    finding.notes.append(conflict.explanation)
        # Add narrowly scoped guidance as guidance, never a legal liability conclusion.
        extra = {'construction':'dob-occupancy', 'maintenance':'hpd-allergens', 'eviction':'courts-eviction', 'litigation':'courts-records', 'rent_regulation':'hcr-rent-regulation'}.get(category)
        hit = next((h for h in draft.retrieved_sources if h.source.id == extra), None)
        if hit:
            finding.legal_conclusions.append(LegalConclusion(statement=hit.source.summary,source_ids=[hit.source.id],identifiers=[hit.source.identifier]))
        findings.append(finding)
        sources.update({h.source.id:h for h in draft.retrieved_sources})
    return ResearchDraft(task_id=task.task_id,plan_revision=plan.revision,findings=findings,retrieved_sources=list(sources.values()),evidence_ids_used=list(dict.fromkeys(e for f in findings for e in f.evidence_ids)),reasoning_mode=reasoning_mode,caveats=['Offline curated catalog; source versions and current records require verification.'])
