from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

if __package__ and __package__.startswith("agents.legal_agent"):
    from .agents.critic import critique_draft
else:
    from agents.critic import critique_draft
if __package__ and __package__.startswith("agents.legal_agent"):
    from .agents.planner import make_plan
else:
    from agents.planner import make_plan
if __package__ and __package__.startswith("agents.legal_agent"):
    from .agents.researcher import research
else:
    from agents.researcher import research
if __package__ and __package__.startswith("agents.legal_agent"):
    from .models.schemas import (
        CriticOutcome,
        InvestigationContext,
        InvestigationError,
        InvestigationResult,
        InvestigationStatus,
        LegalIssueTask,
        ResearchDraft,
        ResearchPlan,
    )
else:
    from models.schemas import (
        CriticOutcome,
        InvestigationContext,
        InvestigationError,
        InvestigationResult,
        InvestigationStatus,
        LegalIssueTask,
        ResearchDraft,
        ResearchPlan,
    )
if __package__ and __package__.startswith("agents.legal_agent"):
    from .tools.legal_search import LegalSearchTool
else:
    from tools.legal_search import LegalSearchTool
if __package__ and __package__.startswith("agents.legal_agent"):
    from .tools.execution import ExecutionBudget, ExecutionLimits, ExecutionStopped, ReadOnlySearch
else:
    from tools.execution import ExecutionBudget, ExecutionLimits, ExecutionStopped, ReadOnlySearch
if __package__ and __package__.startswith("agents.legal_agent"):
    from .models.identity import IdentityResult
else:
    from models.identity import IdentityResult
if __package__ and __package__.startswith("agents.legal_agent"):
    from .identity import resolve_building_identity, match_record
else:
    from identity import resolve_building_identity, match_record
if __package__ and __package__.startswith("agents.legal_agent"):
    from .reconciliation import reconcile_evidence, invalidate_findings
else:
    from reconciliation import reconcile_evidence, invalidate_findings

MAX_REVISION_CYCLES = 2

PlannerFn = Callable[..., ResearchPlan]
ResearcherFn = Callable[..., ResearchDraft]
CriticFn = Callable[..., Any]


def _reasoning_mode() -> str:
    if __package__ and __package__.startswith("agents.legal_agent"):
        from .tools.llm import configured_provider
    else:
        from tools.llm import configured_provider
    provider=configured_provider()
    return 'demo_deterministic' if provider in {'','demo','deterministic'} else 'llm:'+provider


class LegalResearchWorkflow:
    def __init__(
        self,
        planner: PlannerFn = make_plan,
        researcher: ResearcherFn = research,
        critic: CriticFn = critique_draft,
        search_tool: LegalSearchTool | None = None,
        max_revision_cycles: int = MAX_REVISION_CYCLES,
        reasoning_mode: str | None = None,
        limits: ExecutionLimits | None = None,
        model_adapter=None,
        memory=None,
        model_provider=None,
    ) -> None:
        self.planner = planner
        self.researcher = researcher
        self.critic = critic
        self.search_tool = search_tool or LegalSearchTool()
        self.limits = limits or ExecutionLimits.from_env()
        if not 0 <= max_revision_cycles <= 2:
            raise ValueError("Revision cycles must be between zero and two")
        self.max_revision_cycles = min(max_revision_cycles, self.limits.max_revision_cycles)
        self.model_adapter = model_adapter
        self.memory = memory
        self.model_provider = model_provider
        self.reasoning_mode = reasoning_mode or ("llm:injected" if model_adapter else _reasoning_mode())

    def run(self, task: LegalIssueTask, context: InvestigationContext, *, budget=None) -> InvestigationResult:
        budget = budget or ExecutionBudget(self.limits)
        budget.trace.task_id=task.task_id
        budget.trace.emit("legal.started",data_mode=context.data_mode,provider=context.data_provider)
        notes = []
        if self.reasoning_mode == "demo_deterministic":
            notes.append(
                "[DEMO_DETERMINISTIC] Deterministic mode selected. Planner, researcher, and critic used labeled heuristic logic."
            )
        else:
            notes.append(
                "Model mode selected; successful model calls are required for planning, analysis and critique. Deterministic validation always applies."
            )

        feedback = None
        draft: ResearchDraft | None = None
        report = None
        revision_cycles = 0
        errors: list[InvestigationError] = []

        plans = []
        review_history = []
        bounded_search = ReadOnlySearch(self.search_tool, self.limits, budget)
        original_context = context.model_copy(deep=True)
        identity = None
        matches = []
        reconciliation = None
        planner, researcher, critic = self.planner, self.researcher, self.critic
        agents = None

        def finish(*args, **kwargs):
            result = self._result(*args, **kwargs)
            result.data_mode = original_context.data_mode
            result.data_provider = original_context.data_provider
            result.review_history = review_history
            result.execution = budget.snapshot()
            result.caveats = list(draft.caveats) if draft else []
            result.identity = identity
            result.record_matches = matches
            result.reconciliation = reconciliation
            result.plans = plans
            result.tool_calls = bounded_search.calls
            executed={h.source.id:h.source for hits in bounded_search.cache.values() for h in hits}
            result.legal_sources = list(executed.values())
            result.retrieved_source_ids = list(executed)
            accepted_ids=set(reconciliation.accepted_ids) if reconciliation else set()
            if __package__ and __package__.startswith('agents.legal_agent'):
                from .citations import audit_claims
            else:
                from citations import audit_claims
            result.citation_audit,result.citation_metrics=audit_claims(result.findings,executed,accepted_ids,as_of=context.as_of)
            budget.trace.emit('citations.audited',**result.citation_metrics)
            result.research_requests = list(dict.fromkeys(x for f in result.findings for x in f.follow_up_tasks))
            if agents:result.research_requests.extend(agents.external_limits)
            result.research_requests.extend(dict.fromkeys(i.required_correction for i in result.critic_issues if i.code == 'applicability_unresolved'))
            if reconciliation and (reconciliation.rejected_ids or reconciliation.quarantined_ids):
                result.research_requests.append('Matcher: revisit attribution or scope for held records: ' + ', '.join(reconciliation.rejected_ids + reconciliation.quarantined_ids))
            if identity and identity.verification_status in {'missing','ambiguous'}:
                result.research_requests.append('Resolve building identity with authoritative NYC identifiers before legal analysis.')
            if reconciliation:
                result.findings = invalidate_findings(result.findings, reconciliation)
            if self.memory and identity and identity.verification_status in {'verified','sample'}:
                try:
                    memory_context=original_context.model_copy(deep=True,update={'identity':identity,'reconciliation':reconciliation})
                    self.memory.store(task,memory_context,result,budget=budget)
                except (ExecutionStopped,ValueError):
                    result.notes.append('Persistent legal memory was unavailable; this result was not stored in memory.')
                    budget.trace.emit('memory.failed',operation='store')
            result.execution=budget.snapshot()
            budget.trace.emit('report.generated' ,status=result.status.value,findings=len(result.findings))
            budget.trace.emit('legal.finished',status=result.status.value,critic_outcome=result.critic_outcome)
            result.activity_events=budget.trace.events
            return result

        try:
            budget.check()
            if context.root_critic_outcome == CriticOutcome.BLOCKED:
                budget.trace.emit("critic.veto",origin="trusted_upstream",outcome="BLOCKED")
                if __package__ and __package__.startswith("agents.legal_agent"):
                    from .models.schemas import CriticReport
                else:
                    from models.schemas import CriticReport
                report=CriticReport(task_id=task.task_id,outcome=CriticOutcome.BLOCKED,revision_instructions=['Upstream investigation veto must be resolved by its owner.'])
                review_history.append(report)
                return finish(task,None,report,InvestigationStatus.INCONCLUSIVE,0,notes=notes)
            identity_context = {"unit":task.building.unit,"borough":task.building.borough}
            if context.data_mode != 'sample':
                identity_context['candidates'] = []
            if context.identity_candidates is not None:
                identity_context['candidates'] = [c.model_dump(mode='json') for c in context.identity_candidates]
            if context.identity:
                identity_context['candidates'] = [c.model_dump(mode='json') for c in context.identity.candidates]
                # A trusted canonical snapshot need not retain the whole candidate search.
                # Revalidate original authoritative identifier provenance, never its label alone.
                if not context.identity.candidates and context.identity.verification_status=='verified':
                    verified=context.identity.verified_identifiers
                    if verified and all(i.authoritative and not i.fictional and context.identity.identifiers.get(i.kind)==i.value for i in verified):
                        identity_context['candidates']=[{'candidate_id':'trusted-canonical-snapshot',
                            'address':context.identity.canonical_address,'borough':context.identity.borough,
                            'identifiers':[i.model_dump(mode='json') for i in verified]}]
            identity = IdentityResult.model_validate(resolve_building_identity(task.building.address, identity_context))
            if context.data_mode != 'sample' and identity.verification_status == 'sample':
                raise ExecutionStopped('Fictional identity candidates are prohibited outside sample mode')
            if __package__ and __package__.startswith("agents.legal_agent"):
                from .identity import normalize_address
            else:
                from identity import normalize_address
            allowed_addresses = {identity.canonical_address}
            for c in identity.candidates:
                allowed_addresses.update(normalize_address(a)[0] for a in [c.address,*c.aliases])
            if normalize_address(task.building.address)[0] not in allowed_addresses:
                raise ExecutionStopped('Supplied identity does not match requested address')
            for kind in ('bin','bbl'):
                supplied = getattr(task.building,kind)
                if supplied and identity.identifiers.get(kind) and supplied != identity.identifiers[kind]:
                    identity.verification_status = 'ambiguous'
                    identity.ambiguities.append(f'Requested {kind} conflicts with resolved identity.')
            if context.record_matches:
                if __package__ and __package__.startswith("agents.legal_agent"):
                    from .integration import validate_reviewed_matches
                else:
                    from integration import validate_reviewed_matches
                matches = validate_reviewed_matches(context.evidence, identity, context.record_matches,budget=budget)
            else:
                matches = [match_record(e,identity) for e in context.evidence]
            reconciliation = reconcile_evidence(context.evidence,matches,as_of=context.as_of,budget=budget)
            budget.trace.emit("evidence.reconciled",accepted=len(reconciliation.accepted_ids),rejected=len(reconciliation.rejected_ids),quarantined=len(reconciliation.quarantined_ids),conflicts=[c.category for c in reconciliation.conflicts])
            context = context.model_copy(deep=True,update={"identity":identity,"record_matches":matches,"reconciliation":reconciliation})
            if identity.verification_status in {'missing','ambiguous'}:
                budget.trace.emit('critic.veto',origin='identity_gate',status=identity.verification_status)
                if __package__ and __package__.startswith("agents.legal_agent"):
                    from .models.schemas import CriticReport
                else:
                    from models.schemas import CriticReport
                report = CriticReport(task_id=task.task_id,outcome=CriticOutcome.BLOCKED)
                review_history.append(report.model_copy(deep=True))
                return finish(task,None,report,InvestigationStatus.INCONCLUSIVE,0,notes=notes+identity.ambiguities)
            # Agents see only accepted, requested evidence; the untouched registry stays local.
            budget.trace.emit('identity.decided',status=identity.verification_status,identifiers=identity.identifiers)
            for match in matches:budget.trace.emit('evidence.'+match.decision,evidence_id=match.evidence_id,method=match.method)
            accepted = set(reconciliation.accepted_ids)
            wanted = set(task.evidence_ids) if task.evidence_ids else accepted
            context.evidence = [e for e in context.evidence if e.evidence_id in accepted & wanted]
            if self.memory:
                try:
                    hints=self.memory.retrieve(task,context,budget=budget)
                    context=context.model_copy(update={'untrusted_memory':[*context.untrusted_memory,*hints][:3]})
                except (ExecutionStopped,ValueError):
                    notes.append('Persistent legal memory unavailable; no prior memory was used.')
                    budget.trace.emit('memory.failed',operation='retrieve')
                budget.check()
            if self.reasoning_mode != 'demo_deterministic' or self.model_adapter:
                if __package__ and __package__.startswith("agents.legal_agent"):
                    from .tools.llm import JSONModelAdapter, BoundedModelAdapter
                else:
                    from tools.llm import JSONModelAdapter, BoundedModelAdapter
                if __package__ and __package__.startswith("agents.legal_agent"):
                    from .agents.model_agents import ModelAgents
                else:
                    from agents.model_agents import ModelAgents
                agents = ModelAgents(BoundedModelAdapter(self.model_adapter or JSONModelAdapter(self.limits, budget=budget, provider=self.model_provider), self.limits, budget=budget))
                planner, researcher, critic = agents.plan, agents.research, agents.critique
            for attempt in range(self.max_revision_cycles + 1):
                budget.check()
                budget.trace.emit("agent.started",role="planner",revision=attempt)
                plan = budget.invoke(planner,
                    task,
                    context,
                    ceiling=self.limits.investigation_timeout_seconds,
                    prior_feedback=feedback,
                    revision=attempt,
                    reasoning_mode=self.reasoning_mode,
                )
                plan = ResearchPlan.model_validate(plan).model_copy(deep=True)
                budget.trace.emit("agent.completed",role="planner",revision=attempt)
                plans.append(plan)
                budget.trace.emit("plan.selected",revision=attempt,questions=len(plan.questions),tools=[q.recommended_tool for q in plan.questions])
                budget.trace.emit("agent.started",role="researcher",revision=attempt)
                draft = budget.invoke(researcher,
                    task,
                    context,
                    plan,
                    ceiling=self.limits.investigation_timeout_seconds,
                    search_tool=bounded_search,
                    reasoning_mode=self.reasoning_mode,
                )
                draft = ResearchDraft.model_validate(draft).model_copy(deep=True)
                budget.trace.emit("agent.completed",role="researcher",revision=attempt)
                reconciliation = reconcile_evidence(original_context.evidence,matches,draft.findings,as_of=context.as_of,budget=budget)
                draft.findings = invalidate_findings(draft.findings,reconciliation)
                context = context.model_copy(
                    update={"reconciliation":reconciliation,"retrieved_source_ids": [hit.source.id for hit in draft.retrieved_sources]}
                )
                budget.trace.emit("agent.started",role="local_critic",revision=attempt)
                report = budget.invoke(critic,
                    task,
                    context,
                    draft,
                    ceiling=self.limits.investigation_timeout_seconds,
                    search_tool=bounded_search,
                    reasoning_mode=self.reasoning_mode,
                )
                if __package__ and __package__.startswith("agents.legal_agent"):
                    from .agents.critic import critique_draft as deterministic_review
                else:
                    from agents.critic import critique_draft as deterministic_review
                if __package__ and __package__.startswith("agents.legal_agent"):
                    from .models.schemas import CriticReport
                else:
                    from models.schemas import CriticReport
                report = CriticReport.model_validate(report)
                budget.trace.emit("agent.completed",role="local_critic",revision=attempt)
                gate = deterministic_review(task,context,draft,search_tool=bounded_search,reasoning_mode='deterministic_gate')
                if __package__ and __package__.startswith("agents.legal_agent"):
                    from .integration import merge_critic_reports
                else:
                    from integration import merge_critic_reports
                review_history.extend([report.model_copy(deep=True),gate.model_copy(deep=True)])
                report = merge_critic_reports(report,gate)
                review_history.append(report.model_copy(deep=True))
                for review in review_history[-3:]:
                    budget.trace.emit("critic.decision",outcome=review.outcome.value,mode=review.reasoning_mode,issue_codes=[i.code for i in review.issues])
                if report.outcome == CriticOutcome.BLOCKED:
                    return finish(task,draft,report,InvestigationStatus.INCONCLUSIVE,revision_cycles,notes=notes)
                if report.outcome == CriticOutcome.PASS:
                    return finish(
                        task,
                        draft,
                        report,
                        InvestigationStatus.COMPLETED,
                        revision_cycles=revision_cycles,
                        notes=notes,
                    )
                actionable_followup=False
                if agents and attempt < self.max_revision_cycles:
                    actionable_followup=agents.queue_followups(task,context,report,bounded_search,attempt+1)
                    draft.caveats=list(dict.fromkeys([*draft.caveats,*agents.external_limits]))
                if not actionable_followup and (report.outcome == CriticOutcome.INCONCLUSIVE or agents and agents.external_limits):
                    budget.trace.emit('research.follow_up_stopped',reason='revision_limit' if attempt>=self.max_revision_cycles else 'no_new_recoverable_action')
                    return finish(
                        task,
                        draft,
                        report,
                        InvestigationStatus.INCONCLUSIVE,
                        revision_cycles=revision_cycles,
                        notes=notes,
                    )
                if attempt >= self.max_revision_cycles:
                    errors.append(
                        InvestigationError(
                            code="retry_limit_reached",
                            message=(
                                f"Critic still returned REVISE after {self.max_revision_cycles} revision cycle(s)."
                            ),
                        )
                    )
                    notes.append("Stopped because the maximum number of revision cycles was reached.")
                    return finish(
                        task,
                        draft,
                        report,
                        InvestigationStatus.INCONCLUSIVE,
                        revision_cycles=revision_cycles,
                        errors=errors,
                        notes=notes,
                    )
                feedback = report
                revision_cycles += 1
                budget.trace.emit("plan.revised",revision=revision_cycles)
                notes.append(f"Critic requested revision {revision_cycles}: {report.revision_instructions}")
        except Exception as exc:  # noqa: BLE001 - surface as structured JSON for the orchestrator
            budget.trace.emit("legal.stopped",error_type=type(exc).__name__)
            errors.append(InvestigationError(code="execution_stopped" if isinstance(exc, ExecutionStopped) else "workflow_error", message=str(exc) if isinstance(exc, ExecutionStopped) else "Investigation failed input/output validation or tool execution."))
            return finish(task,draft,report,
                InvestigationStatus.INCONCLUSIVE if isinstance(exc, ExecutionStopped) else InvestigationStatus.ERROR,
                revision_cycles,errors=errors,notes=notes)

        return finish(
            task,
            draft,
            report,
            InvestigationStatus.INCONCLUSIVE,
            revision_cycles=revision_cycles,
            errors=errors,
            notes=notes,
        )

    def _result(
        self,
        task: LegalIssueTask,
        draft: ResearchDraft | None,
        report: Any,
        status: InvestigationStatus,
        revision_cycles: int,
        errors: list[InvestigationError] | None = None,
        notes: list[str] | None = None,
    ) -> InvestigationResult:
        findings = draft.findings if draft else []
        evidence_ids = draft.evidence_ids_used if draft else task.evidence_ids
        retrieved = [hit.source.id for hit in draft.retrieved_sources] if draft else []
        return InvestigationResult(
            task_id=task.task_id,
            building=task.building,
            evidence_ids=evidence_ids,
            findings=findings,
            status=status,
            critic_outcome=report.outcome if report is not None else None,
            revision_cycles=revision_cycles,
            reasoning_mode=self.reasoning_mode,
            retrieved_source_ids=retrieved,
            errors=errors or [],
            critic_issues=list(report.issues) if report is not None else [],
            notes=notes or [],
        )


def investigate_legal_issue(task: dict[str, Any] | LegalIssueTask, context: dict[str, Any] | InvestigationContext) -> dict[str, Any]:
    """Public integration point for the team's Flask orchestrator."""
    task_model = task if isinstance(task, LegalIssueTask) else LegalIssueTask.model_validate(task)
    context_model = (
        context if isinstance(context, InvestigationContext) else InvestigationContext.model_validate(context)
    )
    result = LegalResearchWorkflow().run(task_model, context_model)
    return result.model_dump(mode="json")
