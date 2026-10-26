"""Bounded prompt projections; original evidence and authorities stay in the workflow."""
import json
import os
import re
from typing import Protocol


class MemoryAdapter(Protocol):
    """Suggestions remain untrusted and never enter the evidence registry."""
    def retrieve(self, task, context, *, budget, limit: int = 3) -> list[dict]: ...
    def store(self, task, context, result, *, budget) -> list[dict]: ...


def context_bytes(payload):
    return len(json.dumps(payload, ensure_ascii=False, default=str).encode('utf-8'))


def compact_finding(f):
    result={k: v for k, v in f.model_dump(mode='json').items() if k in {
        'finding_id','issue','summary','evidence_ids','legal_conclusions','confidence',
        'valid','memory_ids','missing_information','contradictory_evidence_ids','sufficiency','follow_up_tasks'}}
    for claim in result.get('legal_conclusions',[]):
        claim.pop('citations',None)  # Canonical metadata lives in the separately provided authority registry.
        claim.pop('grounding_errors',None)  # Independent semantic review must evaluate the text itself.
    return result


def agent_context(task, context, *, evidence_ids=None, findings=(), feedback=None, sources=(), max_bytes=None):
    if __package__ and __package__.startswith('agents.legal_agent'):
        from .tools.execution import ExecutionStopped
    else:
        from tools.execution import ExecutionStopped
    limit=int(max_bytes or os.getenv('LEGAL_CONTEXT_MAX_BYTES','40000'))
    token_limit=int(os.getenv('LEGAL_CONTEXT_MAX_TOKENS','16000'))
    if not 1024<=token_limit<=200000:raise ExecutionStopped('Invalid conservative context token ceiling')
    limit=min(limit,token_limit)  # UTF-8 bytes conservatively bound byte-tokenizer input, without guessing a model tokenizer.
    if not 1024 <= limit <= 200000:
        raise ExecutionStopped('Context budget must be between 1024 and 200000 bytes')
    wanted=set(evidence_ids if evidence_ids is not None else task.evidence_ids or [e.evidence_id for e in context.evidence])
    held=set()
    if context.reconciliation:
        held=set(context.reconciliation.rejected_ids+context.reconciliation.quarantined_ids)
    invalidated=set(context.reconciliation.invalidated_finding_ids) if context.reconciliation else set()
    valid=[f for f in findings if f.valid and f.finding_id not in invalidated and not (set(f.evidence_ids)|set(f.contradictory_evidence_ids)) & held]
    memories=[m for m in context.untrusted_memory if not m.get('invalidated') and not m.get('supersededBy')
              and not held & set(m.get('evidence_ids',[]))]
    memories=list({(m.get('summary'),tuple(m.get('evidence_ids',[])),m.get('trust_label')):m for m in memories}.values())
    identity=context.identity.model_dump(mode='json',exclude={'candidates'}) if context.identity else {
        **task.building.model_dump(mode='json'),'verification_status':'unverified'}
    result={'request':task.question,'task_id':task.task_id,'issue_types':task.issue_types,
        'identity':identity,'as_of':str(context.as_of),'data_mode':context.data_mode,'data_provider':context.data_provider,
        'untrusted_memory':memories,
        'reference_domains':{'evidence_ids':[e.evidence_id for e in context.evidence if e.evidence_id not in held],
            'authority_ids':list(dict.fromkeys(s.id for s in sources)),
            'memory_ids':[m.get('memory_id') for m in memories if m.get('memory_id')]},
        'citation_policy':'Evidence IDs support facts; retrieved authority IDs support legal conclusions; memory IDs are context only. Never interchange these registries.',
        'coverage':context.source_coverage,'unresolved_questions':context.unresolved_questions,
        'reconciliation':context.reconciliation.model_dump(mode='json') if context.reconciliation else None,
        'critic_feedback':feedback.model_dump(mode='json') if feedback else None,
        'evidence':[],'authorities':[],'prior_findings':[],
        'selection':{'omitted_evidence_ids':[],'omitted_authority_ids':[],
            'invalidated_finding_ids':[f.finding_id for f in findings if f not in valid],
            'omitted_finding_ids':[], 'max_bytes':limit,
            'note':'Only original descriptions/excerpts are included. Omitted items remain in the authoritative registry; absence is not negative evidence.'}}
    # Preserve uncertainties and omission manifests before allocating space to records.
    evidence=[e for e in context.evidence if e.evidence_id in wanted-held]
    terms=set(re.findall(r'\w+', ' '.join([task.question,*task.issue_types]).lower()))
    conflicted={eid for c in context.reconciliation.conflicts for eid in c.evidence_ids} if context.reconciliation else set()
    priority={'confirmed_violation':0,'case_filing':1,'complaint':2,'inspection':3,'permit':4,'other':5}
    evidence.sort(key=lambda e:(e.evidence_id not in conflicted,-len(terms & set(re.findall(r'\w+',e.description.lower()))),priority.get(e.kind.value,5),e.evidence_id))
    authorities=list({s.id:s for s in sources}.values())
    result['selection']['omitted_evidence_ids']=[e.evidence_id for e in evidence]
    result['selection']['omitted_authority_ids']=[s.id for s in authorities]
    result['selection']['omitted_finding_ids']=[f.finding_id for f in valid]
    if context_bytes(result)>limit:
        raise ExecutionStopped('Mandatory identity, uncertainty and provenance context exceeds budget')
    def include(collection,item,manifest,identifier):
        result[collection].append(item);result['selection'][manifest].remove(identifier)
        if context_bytes(result)>limit:
            result[collection].pop();result['selection'][manifest].append(identifier)
    # Keep exact authoritative text, never manufacture compressed legal quotations.
    for s in authorities:include('authorities',s.model_dump(mode='json'),'omitted_authority_ids',s.id)
    for e in evidence:
        row=e.model_dump(mode='json',exclude={'metadata'})
        row['metadata']={k:v for k,v in e.metadata.items() if k in {
            'source_url','record_id','original_record_id','dataset_id','retrieved_at','updated_at',
            'origin_record_id','origin_record_components','origin_source','dataset','original_event_date',
            'bin','bbl','hpd_building_id','normalized_status','scope','source_record_id'}}
        row['identity_match_status']='accepted' if context.reconciliation and e.evidence_id in context.reconciliation.accepted_ids else 'unverified'
        include('evidence',row,'omitted_evidence_ids',e.evidence_id)
    for f in valid:include('prior_findings',compact_finding(f),'omitted_finding_ids',f.finding_id)
    result['reference_domains']['authority_ids']=[s['id'] for s in result['authorities']]
    result['reference_domains']['evidence_ids']=[e['evidence_id'] for e in result['evidence']]
    return result


def original_context_items(context, sources=(), *, evidence_ids=(), authority_ids=()):
    """Trusted review lookup; originals are not converted to memory or summaries.

    The deterministic Critic already receives the complete accepted context and
    executed search hits. A Keeper/operator can use this for focused follow-up.
    Held evidence is available only in the audit registry, never this support lookup.
    """
    held=set(context.reconciliation.rejected_ids+context.reconciliation.quarantined_ids) if context.reconciliation else set()
    if set(evidence_ids)&held:raise ValueError('Held evidence cannot support a claim')
    records={e.evidence_id:e for e in context.evidence};authorities={s.id:s for s in sources}
    if not set(evidence_ids)<=records.keys() or not set(authority_ids)<=authorities.keys():
        raise ValueError('Unregistered original context reference')
    return {'evidence':[records[e].model_copy(deep=True) for e in dict.fromkeys(evidence_ids)],
            'authorities':[authorities[s].model_copy(deep=True) for s in dict.fromkeys(authority_ids)]}
