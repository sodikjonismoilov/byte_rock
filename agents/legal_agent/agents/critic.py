from __future__ import annotations

if __package__ and __package__.startswith("agents.legal_agent"):
    from ..models.schemas import (
        CriticIssue,
        CriticOutcome,
        CriticReport,
        EvidenceKind,
        InvestigationContext,
        LegalIssueTask,
        ResearchDraft,
    )
else:
    from models.schemas import (
        CriticIssue,
        CriticOutcome,
        CriticReport,
        EvidenceKind,
        InvestigationContext,
        LegalIssueTask,
        ResearchDraft,
    )
if __package__ and __package__.startswith("agents.legal_agent"):
    from ..tools.legal_search import LegalSearchTool
else:
    from tools.legal_search import LegalSearchTool


def _catalog_identifiers(search_tool: LegalSearchTool) -> set[str]:
    return {source.identifier.lower() for source in search_tool.sources}


def _catalog_ids(search_tool: LegalSearchTool) -> set[str]:
    return {source.id for source in search_tool.sources}


def critique_draft(
    task: LegalIssueTask,
    context: InvestigationContext,
    draft: ResearchDraft,
    search_tool: LegalSearchTool | None = None,
    reasoning_mode: str = "demo_deterministic",
) -> CriticReport:
    """Rule-based critic. Always runs, even after an LLM researcher is added later."""
    tool = search_tool or LegalSearchTool()
    known_ids = _catalog_ids(tool)
    known_identifiers = _catalog_identifiers(tool)
    retrieved_ids = {hit.source.id for hit in draft.retrieved_sources} or set(context.retrieved_source_ids)

    issues: list[CriticIssue] = []
    unresolved: list[CriticIssue] = []
    instructions: list[str] = []

    if not draft.findings:
        issues.append(
            CriticIssue(code="no_findings", message="Researcher returned no findings.", finding_ids=[])
        )
        instructions.append("Produce at least one finding that classifies the available evidence.")

    all_kinds: list[EvidenceKind] = []
    for finding in draft.findings:
        all_kinds.extend(finding.evidence_kinds)
        if finding.treats_complaint_as_violation:
            issues.append(
                CriticIssue(
                    code="complaint_as_violation",
                    message="Finding treats a complaint as a confirmed violation.",
                    finding_ids=[finding.finding_id],
                )
            )
            instructions.append(
                "Separate 311/HPD complaints from inspector-issued violations. Do not equate them."
            )

        complaint_only = (
            EvidenceKind.COMPLAINT in finding.evidence_kinds
            and EvidenceKind.CONFIRMED_VIOLATION not in finding.evidence_kinds
            and finding.confidence == "high"
        )
        if complaint_only:
            issues.append(
                CriticIssue(
                    code="overconfident_complaint",
                    message="High confidence is not justified when evidence is limited to complaints.",
                    finding_ids=[finding.finding_id],
                )
            )
            instructions.append("Lower confidence and state that complaints are unconfirmed.")

        for conclusion in finding.legal_conclusions:
            unknown_sources = [source_id for source_id in conclusion.source_ids if source_id not in known_ids]
            unknown_identifiers = [
                identifier
                for identifier in conclusion.identifiers
                if identifier.lower() not in known_identifiers
            ]
            not_retrieved = [
                source_id for source_id in conclusion.source_ids if retrieved_ids and source_id not in retrieved_ids
            ]
            unsupported = bool(unknown_sources or unknown_identifiers or not_retrieved) or not conclusion.supported
            if unsupported:
                issues.append(
                    CriticIssue(
                        code="unsupported_legal_conclusion",
                        message=(
                            "Legal conclusion is unsupported by the curated catalog or retrieved sources: "
                            f"{conclusion.statement}"
                        ),
                        finding_ids=[finding.finding_id],
                        recommended_agent_or_tool='request_external' if conclusion.grounding_version and conclusion.claim_scope=='historical_application' else 'legal_search',
                    )
                )
                instructions.append(
                    "Remove or rewrite legal conclusions so every identifier and source_id comes from retrieved curated sources."
                )

            if not conclusion.source_ids and not conclusion.identifiers:
                issues.append(
                    CriticIssue(
                        code="uncited_legal_conclusion",
                        message="Legal conclusion has no source citation.",
                        finding_ids=[finding.finding_id],
                    )
                )
                instructions.append("Cite a retrieved source or drop the legal conclusion.")

    if __package__ and __package__.startswith("agents.legal_agent"):
        from ..agents.scope import categories
    else:
        from agents.scope import categories
    if len(categories(task)) == 7:
        missing = set(categories(task)) - {f.issue for f in draft.findings}
        if missing:
            # Global coverage belongs to the team Planner. Keep the legal result
            # inconclusive without spending legal-search revisions on scheduling gaps.
            unresolved.append(CriticIssue(code='incomplete_scope',message='Global due-diligence coverage deferred: '+', '.join(sorted(missing)),recommended_agent_or_tool='global_planner'))
            instructions.append('Research the missing categories or explicitly identify unavailable records for each.')
    registry = {e.evidence_id:e for e in context.evidence}
    available = {h.source.id:h.source for h in draft.retrieved_sources}
    if set(draft.evidence_ids_used) - registry.keys():
        issues.append(CriticIssue(code='unknown_evidence',message='Draft cites evidence outside the accepted registry.'))
    for finding in draft.findings:
        def flag(code, message):
            issues.append(CriticIssue(code=code,message=message,finding_ids=[finding.finding_id],evidence_ids=[eid for eid in finding.evidence_ids if not eid.lower().startswith('mem-')]))
            instructions.append(message)
        if not finding.valid or set(finding.evidence_ids) - registry.keys():
            flag('invalid_property_dependency','Remove findings dependent on rejected, quarantined or unknown property evidence.')
        if any(e.startswith('mem-') for e in finding.evidence_ids) or any(s.startswith('mem-') for c in finding.legal_conclusions for s in c.source_ids):
            flag('memory_as_authority','Memory is context only; retrieve official evidence and legal authorities.')
        text = ' '.join([finding.summary,*[c.statement for c in finding.legal_conclusions]]).lower()
        import re
        if re.search(r'\b(automatically liable|definitely liable|proves wrongdoing)\b',text):
            flag('unsupported_interpretation','Remove definitive wrongdoing or liability assertions.')
        if re.search(r'\b(unit|apartment) is rent[- ](?:stabilized|regulated)\b',text):
            flag('unsupported_unit_status','Request unit-specific rent history and orders; do not infer status from building records.')
        if 'was evicted' in text and not any(registry[e].kind == EvidenceKind.EXECUTED_EVICTION for e in finding.evidence_ids if e in registry):
            flag('unsupported_eviction_stage','A filing or warrant is not an executed eviction.')
        actual_kinds = [registry[e].kind for e in finding.evidence_ids if e in registry]
        records = [registry[e] for e in finding.evidence_ids if e in registry]
        if re.search(r'\b(landlord|owner|tenant) (?:has |is |did )?(?:violated the law|liable|owes damages)\b', text):
            flag('unsupported_liability', 'Replace a liability assertion with what the cited record reports; liability is not established by these records.')
        scopes = {e.metadata.get('scope', 'building') for e in records}
        if scopes and scopes <= {'property'} and re.search(r'\b(?:this|the) (?:building|unit|apartment) (?:has|is|was)\b', text):
            flag('unsupported_property_scope', 'Lot-level records cannot establish a condition in this building or apartment; qualify the claim or request building linkage.')
        if set(finding.evidence_kinds) != set(actual_kinds):
            flag('false_evidence_classification','Derive evidence classifications from accepted records, not the draft.')
        for conclusion in finding.legal_conclusions:
            assessment=None
            historical=not conclusion.grounding_version or conclusion.claim_scope=='historical_application'
            if conclusion.grounding_version:
                if __package__ and __package__.startswith('agents.legal_agent'):
                    from ..citations import assess_claim,canonical_metadata
                else:
                    from citations import assess_claim,canonical_metadata
                assessment=assess_claim(conclusion,available,as_of=context.as_of)
                if conclusion.citations!=canonical_metadata(conclusion,available):
                    flag('citation_metadata_mismatch','Canonical metadata must match the retrieved registry.')
                if 'wrong_topic_source' in assessment['errors']:
                    flag('wrong_topic_source','The cited excerpt addresses a different subject from the claim.')
                if not assessment['claim_support_verified']:
                    issues.append(CriticIssue(code='claim_support_unverified',message='Source identity is not claim support: '+', '.join(assessment['errors']),
                        finding_ids=[finding.finding_id],recommended_agent_or_tool='request_external' if historical else 'legal_search'))
            if not conclusion.source_ids or any(id not in available for id in conclusion.source_ids):
                flag('unsupported_legal_conclusion','Every legal conclusion needs an actually retrieved source.')
            linked = {available[id].identifier.lower() for id in conclusion.source_ids if id in available}
            if any(id.lower() not in linked for id in conclusion.identifiers):
                flag('citation_identifier_mismatch','Identifiers must correspond to the cited retrieved source.')
            for id in conclusion.source_ids:
                source = available.get(id)
                if source and historical and context.data_mode != 'sample' and (not source.effective_from or not source.checked_on or any(e.date is None for e in records)):
                    unresolved.append(CriticIssue(code='applicability_unresolved', message=f'{id}: operative source version or incident date is unverified; this authority is background research only.', finding_ids=[finding.finding_id], evidence_ids=finding.evidence_ids, recommended_agent_or_tool='legal_search', required_correction='Verify the operative authority for the incident date before applying it to this property.'))
                if source and (source.jurisdiction not in {'NY','NYC'} or
                    source.effective_from and any(d < source.effective_from for d in ([context.as_of,*[registry[e].date for e in finding.evidence_ids if e in registry and registry[e].date]] if historical else [context.as_of])) or
                    source.effective_to and any(d > source.effective_to for d in ([context.as_of,*[registry[e].date for e in finding.evidence_ids if e in registry and registry[e].date]] if historical else [context.as_of]))):
                    flag('inapplicable_authority','Recheck jurisdiction and effective date of the cited authority.')
            import re
            if re.search(r'\b(automatically liable|definitely liable|guaranteed|proves wrongdoing)\b',conclusion.statement.lower()):
                flag('unsupported_interpretation','Remove definitive liability or wrongdoing conclusions from incomplete public records.')
            if ('"' in conclusion.statement or '“' in conclusion.statement) and not (assessment and assessment['claim_support_verified']) and not any(available[id].excerpt and available[id].excerpt in conclusion.statement for id in conclusion.source_ids if id in available):
                flag('unverified_quotation','Remove quotations without exact retrieved text support.')

    unique_kinds = set(all_kinds)
    has_violation = EvidenceKind.CONFIRMED_VIOLATION in unique_kinds
    has_any_evidence = bool(draft.evidence_ids_used or context.evidence)
    unsupported = any(issue.code == "unsupported_legal_conclusion" for issue in issues)

    if issues:
        outcome = CriticOutcome.REVISE
    elif not has_any_evidence or (not has_violation and unique_kinds <= {EvidenceKind.COMPLAINT, EvidenceKind.TENANT_REPORT, EvidenceKind.OTHER, EvidenceKind.COMPLAINT}):
        if not has_violation:
            outcome = CriticOutcome.INCONCLUSIVE
            issues.append(
                CriticIssue(
                    code="insufficient_confirmed_evidence",
                    message="Evidence does not include a confirmed violation, so the legal issue cannot be resolved from the record.",
                    finding_ids=[finding.finding_id for finding in draft.findings],
                )
            )
        else:
            outcome = CriticOutcome.PASS
    else:
        outcome = CriticOutcome.PASS

    if outcome == CriticOutcome.PASS and any(f.sufficiency == "insufficient" or f.contradictory_evidence_ids for f in draft.findings):
        outcome = CriticOutcome.INCONCLUSIVE

    if context.identity and context.identity.verification_status == 'unverified' and outcome == CriticOutcome.PASS:
        outcome = CriticOutcome.INCONCLUSIVE
        issues.append(CriticIssue(code='identity_unverified',message='Address lacks authoritative identifiers; verify building identity.'))

    if outcome == CriticOutcome.INCONCLUSIVE and unsupported:
        outcome = CriticOutcome.REVISE

    if unresolved:
        if outcome == CriticOutcome.PASS:
            outcome = CriticOutcome.INCONCLUSIVE
        issues.extend(unresolved)

    notes_mode = reasoning_mode
    return CriticReport(
        task_id=task.task_id,
        outcome=outcome,
        issues=issues,
        revision_instructions=list(dict.fromkeys(instructions)),
        reasoning_mode=notes_mode,
    )
