"""Stateless boundary to the team Critic and World Model; no storage or transport."""
import importlib.util
from pathlib import Path

if __package__ and __package__.startswith("agents.legal_agent"):
    from .models.identity import RecordMatch
else:
    from models.identity import RecordMatch


def root_critic():
    spec = importlib.util.spec_from_file_location('signsafe_team_critic', Path(__file__).resolve().parents[2] / 'critic.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def merge_critic_reports(*reports):
    """Conservative legal gate policy; BLOCKED is terminal and never downgraded.

    Root record-level reject/quarantine rules are unchanged. A trusted upstream
    investigation veto is handled before research in LegalResearchWorkflow.
    """
    if __package__ and __package__.startswith('agents.legal_agent'):
        from .models.schemas import CriticReport
    else:
        from models.schemas import CriticReport
    reports=[CriticReport.model_validate(r) for r in reports if r is not None]
    if not reports or len({r.task_id for r in reports})!=1:
        raise ValueError('Critic reports must refer to one task')
    rank={'PASS':0,'REVISE':1,'INCONCLUSIVE':2,'BLOCKED':3}
    strongest=max(reports,key=lambda r:rank[r.outcome.value])
    issues={i.model_dump_json():i for r in reports for i in r.issues}
    return CriticReport(task_id=strongest.task_id,outcome=strongest.outcome,
        issues=list(issues.values()),revision_instructions=list(dict.fromkeys(x for r in reports for x in r.revision_instructions)),
        reasoning_mode='merged_review')


def validate_reviewed_matches(evidence, identity, reviewed, *, budget=None):
    """Consume upstream attribution; retain local identifier and legal scope vetoes.

    An explicit review must cover the whole snapshot. Never accept an incomplete
    batch or use a supplied decision to upgrade lot/unit/entity evidence.
    """
    by_id = {m.evidence_id: m for m in reviewed}
    if len(by_id) != len(reviewed) or set(by_id) != {e.evidence_id for e in evidence}:
        raise ValueError('Reviewed matches must uniquely cover the evidence snapshot')
    result = []
    for record in evidence:
        if budget:budget.check()
        match = by_id[record.evidence_id].model_copy(deep=True)
        scope = record.metadata.get('scope', 'building')
        if match.scope != scope:
            raise ValueError('Reviewed scope conflicts with source metadata')
        conflict = any(record.metadata.get(k) and identity.identifiers.get(k) and str(record.metadata[k]) != identity.identifiers[k] for k in ('bin', 'bbl', 'hpd_building_id'))
        building_key = any(record.metadata.get(k) and str(record.metadata[k]) == identity.identifiers.get(k) for k in ('bin', 'hpd_building_id'))
        scope_unresolved = (scope == 'entity' or
            scope == 'unit' and (not identity.unit or str(record.metadata.get('unit', '')).upper() != identity.unit.upper()) or
            scope == 'building' and record.metadata.get('bbl') and not building_key)
        if match.decision == 'accepted' and (conflict or scope_unresolved):
            match.decision = 'rejected' if conflict else 'quarantined'
            match.reason = 'Identifier conflict.' if conflict else 'Legal scope remains unresolved despite upstream attribution.'
        result.append(match)
    # A registration contact cannot survive a held/missing property-link parent.
    # Only downgrade dependencies; this never promotes an upstream decision.
    changed=True
    while changed:
        if budget:budget.check()
        changed=False
        accepted={m.evidence_id for m in result if m.decision=='accepted'}
        for record,match in zip(evidence,result):
            parents=record.metadata.get('linkage_parent_evidence_ids',[])
            if match.decision=='accepted' and any(parent not in accepted for parent in parents):
                match.decision='quarantined';match.reason='Property-link parent is missing, rejected or quarantined.'
                changed=True
    return result


def review_records(evidence, building_card, *, budget=None):
    """Call unchanged root rules. Quarantine stays held; Matcher handles retries."""
    critic = root_critic()
    datasets = {'wvxf-dwi5': 'violations', 'erm2-nwe9': 'complaints311', 'ipu4-2q9a': 'permits', '6z8x-wfk4': 'evictions'}
    pinned, decisions, matches = [], [], []
    for e in evidence:
        if budget:budget.check()
        meta = e.metadata
        row = {k: meta[k] for k in ('bin', 'bbl', 'lat', 'lon', 'building_class', 'year_built', 'bridging_permit', 'corroborated', 'matcher_confidence') if k in meta}
        row.update(record_id=e.evidence_id, dataset=datasets.get(meta.get('dataset'), meta.get('dataset', e.source)), address_raw=e.building_address or '', record_date=str(e.date) if e.date else '')
        # A missing Matcher confidence is unresolved, never implicitly trusted.
        row.setdefault('matcher_confidence', 0.0)
        entry = critic.review_link(row, building_card, pinned)
        decisions.append(entry)
        if budget:budget.trace.emit("root_critic.decision",phase="record_attribution",record_id=e.evidence_id,decision=entry["decision"],rule=entry["rule"])
        if entry['decision'] == 'accept':
            pinned.append(row)
        matches.append(RecordMatch(evidence_id=e.evidence_id, decision={'accept': 'accepted', 'reject': 'rejected', 'quarantine': 'quarantined'}[entry['decision']], method='team_critic', scope=meta.get('scope', 'building'), confidence=row['matcher_confidence'], reason=entry['reason']))
    return matches, decisions


def board_update(result, evidence, root_decisions=(), *, budget=None):
    """JSON payload for Keeper-owned persistence, not an invented Meterless API."""
    accepted = set(result.reconciliation.accepted_ids) if result.reconciliation else set()
    critic = root_critic()
    findings, gaps, decisions, withheld = [], [], [], []
    publishable_review = result.status.value == 'completed' and result.critic_outcome is not None and result.critic_outcome.value == 'PASS'
    for finding in result.findings:
        if not finding.evidence_ids:
            gaps.append(finding.model_dump(mode='json'))
            continue
        decision = critic.review_finding({'record_ids': finding.evidence_ids}, accepted)
        decisions.append(dict(decision, finding_id=finding.finding_id))
        if budget:budget.trace.emit("root_critic.decision",phase="legal_finding",finding_id=finding.finding_id,decision=decision["decision"],rule=decision["rule"])
        if decision['decision'] == 'accept' and finding.valid and publishable_review:
            findings.append(finding.model_dump(mode='json'))
        else:
            withheld.append(finding.finding_id)
    return {'task_id': result.task_id, 'data_mode': result.data_mode, 'data_provider':result.data_provider, 'identity': result.identity.model_dump(mode='json') if result.identity else None,
            'source_evidence': [e.model_dump(mode='json') for e in evidence],
            'legal_findings': findings, 'coverage_gaps': gaps,
            'authority_refs':{s.id:s.url for s in result.legal_sources},
            'record_decisions': list(root_decisions), 'finding_decisions': decisions,
            'legal_record_matches': [m.model_dump(mode='json') for m in result.record_matches],
            'reconciliation': result.reconciliation.model_dump(mode='json') if result.reconciliation else None,
            'withheld_finding_ids': withheld,
            'status': result.status.value, 'critic_outcome': result.critic_outcome.value if result.critic_outcome else None,
            'legal_issues': [i.model_dump(mode='json') for i in result.critic_issues],
            'legal_reviews': [r.model_dump(mode='json') for r in result.review_history],
            'follow_up_requests': result.research_requests,
            'limitations': result.caveats, 'summary_is_evidence': False}


# Legal-side proposal only. The Keeper owns transport, transactions and storage.
from datetime import datetime, UTC
import hashlib
import json
from typing import Protocol
from pydantic import BaseModel, Field
if __package__ and __package__.startswith('agents.legal_agent'):
    from .models.schemas import LegalIssueTask, InvestigationContext, InvestigationResult
    from .tools.execution import ExecutionBudget
else:
    from models.schemas import LegalIssueTask, InvestigationContext, InvestigationResult
    from tools.execution import ExecutionBudget


class LegalSnapshot(BaseModel):
    """Trusted Keeper projection reuses existing contracts and evidence registry."""
    version: int = Field(ge=0)
    task: LegalIssueTask
    context: InvestigationContext
    # Registry references, not another copy of the raw record store.
    evidence_refs: dict[str, str] = Field(default_factory=dict)
    task_status: str = 'pending'
    follow_up_requests: list[str] = Field(default_factory=list)


class KeeperPort(Protocol):
    """Proposed team boundary; not a claim about an upstream Meterless API.

    publish_legal must atomically check expected_version and idempotency_key.
    Memory mutations must honor the same idempotency key and invalidations.
    """
    def load_snapshot(self, task_id: str) -> dict: ...
    def publish_legal(self, update: dict) -> dict: ...
    def retrieve_context(self, task_id: str, query: str, limit: int) -> list[dict]: ...
    def persist_memory(self, request: dict) -> dict: ...
    def invalidate_memory(self, request: dict) -> dict: ...
    def read_events(self, task_id: str, after: str | None) -> list[dict]: ...


def legal_update(snapshot, result):
    """No raw-record mutation and no promotion of held evidence or blocked claims."""
    if snapshot.task.task_id != result.task_id:
        raise ValueError('Task mismatch')
    accepted=set(result.reconciliation.accepted_ids) if result.reconciliation else set()
    publishable=result.status.value=='completed' and result.critic_outcome and result.critic_outcome.value=='PASS'
    findings=[f.model_dump(mode='json') for f in result.findings if publishable and f.valid and f.evidence_ids
              and set(f.evidence_ids)<=accepted and set(f.evidence_ids)<=set(snapshot.evidence_refs)]
    payload={'schema_version':'legal.keeper.proposal.v1','task_id':result.task_id,
        'expected_version':snapshot.version,'canonical_identity_ref':snapshot.context.identity.identifiers if snapshot.context.identity else {},
        'evidence_refs':{eid:snapshot.evidence_refs[eid] for eid in sorted(accepted & set(snapshot.evidence_refs))},
        'legal_findings':findings,'source_coverage':snapshot.context.source_coverage,
        'limitations':result.caveats,'critic_outcome':result.critic_outcome.value if result.critic_outcome else None,
        'critic_reviews':[r.model_dump(mode='json') for r in result.review_history],
        'status':result.status.value,'follow_up_requests':[
            {'kind':'evidence_or_applicability','requested_by':'legal','task_id':result.task_id,'question':q}
            for q in dict.fromkeys(result.research_requests)],
        'authority_refs':{s.id:s.url for s in result.legal_sources},'summary_is_evidence':False}
    payload['idempotency_key']=hashlib.sha256(json.dumps(payload,sort_keys=True,default=str).encode()).hexdigest()
    return payload


def world_model_fact(update, *, at, run_id):
    """Actual WorldModel.assertFact input, applied by the Keeper, never here.

    Domain names below are proposed legal attributes, not upstream built-ins.
    Stable observation time is required for replay idempotency.
    """
    datetime.fromisoformat(at.replace('Z','+00:00'))
    return {'about':'task:signsafe:'+update['task_id'],'predicate':'legal_assessment',
        'value':update,'source':{'kind':'agent','by':'legal','at':at,'runId':run_id,
                              'checksum':update['idempotency_key']}}


def hmem_add_input(update, *, at_ms, run_id):
    """Actual HMEM.add input; Keeper must deduplicate before HMEM.add (sequential IDs)."""
    if update['critic_outcome']!='PASS' or not update['legal_findings'] or not update['evidence_refs']:
        raise ValueError('Only validated, cited findings may become durable legal memory')
    refs=list(update['evidence_refs'].values())+list(update['authority_refs'].values())
    return {'content':json.dumps({'task_id':update['task_id'],'findings':update['legal_findings'],
                                'limitations':update['limitations']},sort_keys=True),
        'type':'factual','layer':'long_term','confidence':0.7,'source':'legal:'+update['task_id'],
        'provenance':{'origin':'plan_completion','learnedAt':at_ms,'label':'Critic-validated legal research; not official evidence','refs':refs},
        'chatId':update['task_id'],'goalRunId':run_id,'tags':['project:signsafe','legal',update['idempotency_key']],
        'derivedFrom':list(update['evidence_refs'])}


class LegalSharedAdapter:
    """Opt-in Keeper bridge. There is no local database, cache or global planner."""
    def __init__(self, keeper: KeeperPort, workflow, *, budget=None):
        self.keeper=keeper;self.workflow=workflow;self.budget=budget or ExecutionBudget(workflow.limits)

    def _call(self, operation, *args):
        self.budget.consume('tool','keeper.'+operation)
        return self.budget.invoke(getattr(self.keeper,operation),*args,ceiling=self.budget.limits.tool_timeout_seconds)

    def run(self, task_id, *, publish=False, persist_memory=False):
        snapshot=LegalSnapshot.model_validate(self._call('load_snapshot',task_id))
        if snapshot.task.task_id!=task_id:raise ValueError('Keeper returned another task')
        self.budget.trace.task_id=task_id
        identity=snapshot.context.identity
        if snapshot.context.data_mode=='live' and (not identity or identity.verification_status!='verified'):
            raise ValueError('Live shared snapshot requires canonical verified identity')
        # Memory is optional, untrusted, scoped and never copied into the registry.
        self.budget.trace.emit('memory.retrieval_started')
        hints=self._call('retrieve_context',task_id,snapshot.task.question,3)
        held=set(snapshot.context.reconciliation.rejected_ids+snapshot.context.reconciliation.quarantined_ids) if snapshot.context.reconciliation else set()
        hints=[h for h in hints[:3] if h.get('task_id')==task_id and h.get('provenance')
               and not h.get('invalidated') and not h.get('supersededBy') and not held & set(h.get('evidence_ids',[]))]
        context=snapshot.context.model_copy(deep=True,update={'untrusted_memory':hints})
        self.budget.trace.emit('memory.retrieved',count=len(hints),trusted_as_evidence=False)
        result=self.workflow.run(snapshot.task,context,budget=self.budget)
        update=legal_update(snapshot,result)
        if publish:
            receipt=self._call('publish_legal',update)
            if receipt.get('status') not in {'applied','duplicate'}:raise ValueError('Keeper rejected stale or conflicting update')
            self.budget.trace.emit('keeper.update',status=receipt['status'],version=receipt.get('version'))
            if persist_memory and update['legal_findings']:
                now=datetime.now(UTC)
                request={'idempotency_key':update['idempotency_key'],'expected_version':receipt.get('version'),
                         'input':hmem_add_input(update,at_ms=int(now.timestamp()*1000),run_id=self.budget.trace.run_id)}
                self._call('persist_memory',request)
                self.budget.trace.emit('memory.updated',finding_count=len(update['legal_findings']))
        elif persist_memory:raise ValueError('Memory requires a successful Keeper publish')
        result.activity_events=self.budget.trace.events
        return result,update

    def invalidate(self, task_id, memory_ids, *, evidence_ids, expected_version, superseded_by=None):
        if not memory_ids or not evidence_ids:raise ValueError('Invalidation requires memory and evidence provenance')
        request={'task_id':task_id,'memory_ids':list(memory_ids),'evidence_ids':list(evidence_ids),
                 'expected_version':expected_version,'superseded_by':superseded_by}
        request['idempotency_key']=hashlib.sha256(json.dumps(request,sort_keys=True).encode()).hexdigest()
        result=self._call('invalidate_memory',request)
        self.budget.trace.emit('memory.invalidated',count=len(memory_ids),status=result.get('status'))
        return result

    def events(self,task_id,after=None):return self._call('read_events',task_id,after)


class SharedInvestigationContext(BaseModel):
    """Versioned current-run handoff; never a persistent memory or evidence store."""
    schema_version: str = 'signsafe.investigation_context.v1'
    task_id: str
    version: int = 0
    evidence_refs: dict[str, dict] = Field(default_factory=dict)
    authority_refs: dict[str, str] = Field(default_factory=dict)
    accepted_findings: dict[str, dict] = Field(default_factory=dict)
    coverage_gaps: list[dict] = Field(default_factory=list)
    critic_decisions: list[dict] = Field(default_factory=list)
    task_status: dict[str, str] = Field(default_factory=dict)
    root_blocked: bool = False


class SharedInvestigationState:
    """Small in-process adapter around board_update, ready for Keeper ownership.

    Share one instance between agents. Optimistic versions reject stale writes;
    callers reread/reapply their own patch. No upstream World Model is assumed.
    H-MEM methods intentionally do not exist here. Transport/persistence belongs
    to the team orchestrator, which is not present in this repository.
    """
    def __init__(self, trace):
        from threading import RLock
        self.trace=trace;self._lock=RLock();self._contexts={}

    def read(self,task_id):
        with self._lock:
            context=self._contexts.get(task_id,SharedInvestigationContext(task_id=task_id))
            self.trace.emit('shared_state.read',version=context.version,context_task_id=task_id)
            return context.model_copy(deep=True)

    def update(self,task_id,*,actor,expected_version,board=None,coverage_gaps=(),critic_decisions=(),status=None):
        if actor not in {'planner','conductor','legal','root_critic'}:raise ValueError('Unknown shared-context actor')
        if status and status not in {'pending','running','completed','inconclusive','error','blocked'}:raise ValueError('Unknown task status')
        with self._lock:
            current=self._contexts.get(task_id,SharedInvestigationContext(task_id=task_id))
            if current.version!=expected_version:
                self.trace.emit('shared_state.conflict',actor=actor,expected_version=expected_version,actual_version=current.version)
                raise ValueError('Stale shared-context version; reread before updating')
            context=current.model_copy(deep=True)
            decisions=list(critic_decisions);gaps=list(coverage_gaps)
            if board is not None:
                if board['task_id']!=task_id:raise ValueError('Board task mismatch')
                if __package__ and __package__.startswith('agents.legal_agent'):
                    from .models.schemas import EvidenceItem,Finding,AuthorityId
                else:
                    from models.schemas import EvidenceItem,Finding,AuthorityId
                from pydantic import TypeAdapter
                records={e.evidence_id:e for e in [EvidenceItem.model_validate(e) for e in board.get('source_evidence',[])]}
                accepted=set((board.get('reconciliation') or {}).get('accepted_ids',[]))
                root_accepted={d['record_id'] for d in board.get('record_decisions',[]) if d['decision']=='accept'}
                if not (accepted|root_accepted)<=records.keys():raise ValueError('Unknown evidence reference in board')
                for eid in accepted|root_accepted:
                    record=records[eid]
                    reference={'source_url':record.metadata.get('source_url'),'record_id':record.metadata.get('original_record_id') or record.metadata.get('record_id') or eid,
                        'root_accepted':eid in root_accepted,'legal_accepted':eid in accepted}
                    old=context.evidence_refs.get(eid)
                    if old and old['record_id']!=reference['record_id']:raise ValueError('Conflicting evidence identity')
                    context.evidence_refs[eid]=reference
                for aid,url in board.get('authority_refs',{}).items():
                    TypeAdapter(AuthorityId).validate_python(aid)
                    if aid in context.evidence_refs:raise ValueError('Evidence/authority category conflict')
                    if aid in context.authority_refs and context.authority_refs[aid]!=url:raise ValueError('Conflicting authority identity')
                    context.authority_refs[aid]=url
                for finding in board.get('legal_findings',[]):
                    finding=Finding.model_validate(finding)
                    if board.get('status')!='completed' or board.get('critic_outcome')!='PASS' or not finding.valid or not finding.evidence_ids or not set(finding.evidence_ids)<=accepted:
                        raise ValueError('Unvalidated finding in shared board')
                    if any(not set(c.source_ids)<=context.authority_refs.keys() or not c.supported for c in finding.legal_conclusions):raise ValueError('Unvalidated legal authority in board')
                    context.accepted_findings[actor+':'+finding.finding_id]=finding.model_dump(mode='json')
                decisions.extend(board.get('record_decisions',[]));decisions.extend(board.get('finding_decisions',[]))
                decisions.extend(board.get('legal_reviews',[]))
                if board.get('critic_outcome')=='BLOCKED':context.root_blocked=True
                gaps.extend(board.get('coverage_gaps',[]))
                gaps.extend({'source':c.get('source'),'status':c.get('status'),'reason':c.get('reason','')} for c in board.get('source_coverage',[]) if not c.get('complete_for_filter'))
            # Append-only decisions; patches from other actors are never replaced.
            for decision in decisions:
                context.critic_decisions.append({'actor':actor,'decision':decision})
                if actor=='root_critic' and decision.get('outcome')=='BLOCKED':context.root_blocked=True
            for gap in gaps:
                item={'actor':actor,'gap':gap}
                if item not in context.coverage_gaps:context.coverage_gaps.append(item)
            if status:context.task_status[actor]=status
            if context.root_blocked:
                context.accepted_findings={}
                context.task_status['investigation']='blocked'
            context.version+=1
            self._contexts[task_id]=context
            self.trace.emit('shared_state.updated',actor=actor,version=context.version,accepted_evidence_count=len(context.evidence_refs),
                authority_count=len(context.authority_refs),accepted_finding_count=len(context.accepted_findings),root_blocked=context.root_blocked)
            return context.model_copy(deep=True)
