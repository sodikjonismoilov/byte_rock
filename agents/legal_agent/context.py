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


MAX_SHOWN_RECORDS=30  # Rows shown to a model; the full registry stays authoritative and server-side checks use it.
MAX_STATUS_BUCKETS=12
MAX_DUPLICATE_GROUPS=25
COVERAGE_KEYS=('source','status','complete_for_filter','records_returned','reason','limitations')
HISTORICAL_CAVEAT='Dataset historical coverage was not independently audited; a completed filtered query is not proof of complete historical agency coverage. Per-dataset descriptions and retrieval attempts are in the report, not this context.'


def conflict_components(conflicts, evidence=(), held=()):
    """Collapse pairwise conflicts into connected components; every pair's records land in one component."""
    parent={}
    def find(x):
        parent.setdefault(x,x)
        while parent[x]!=x:
            parent[x]=parent[parent[x]];x=parent[x]
        return x
    kept=[]
    for c in conflicts:
        ids=[i for i in dict.fromkeys(c.evidence_ids) if i not in held]
        if not ids:continue
        kept.append((c,ids))
        for i in ids[1:]:parent[find(i)]=find(ids[0])
        find(ids[0])
    by_id={e.evidence_id:e for e in evidence}
    groups={}
    for c,ids in kept:
        groups.setdefault(find(ids[0]),[]).append((c,ids))
    components=[]
    for items in groups.values():
        members=sorted({i for _,ids in items for i in ids})
        records=[by_id[i] for i in members if i in by_id]
        dates=sorted(e.date.isoformat() for e in records if e.date)
        statuses=sorted({e.status or 'unknown' for e in records})[:8]
        text=items[0][0].explanation
        components.append({'category':sorted({c.category for c,_ in items})[0] if len({c.category for c,_ in items})==1 else 'mixed',
            'evidence_ids':members,'pair_count':len(items),'date_range':[dates[0],dates[-1]] if dates else None,'statuses':statuses,
            'resolved':all(c.resolved for c,_ in items),
            'explanation':'Records in this group disagree in pairs on date or status; not every listed pair conflicts. '+(text.split('). ',1)[1] if '). ' in text else text)})
    return sorted(components,key=lambda c:(-c['pair_count'],c['evidence_ids']))


def compact_reconciliation(context, held):
    rec=context.reconciliation
    if not rec:return None
    groups=[[i for i in g if i not in held] for g in rec.duplicate_groups]
    groups=[g for g in groups if len(g)>1]
    return {'counts':{'accepted':len(rec.accepted_ids),'rejected':len(rec.rejected_ids),'quarantined':len(rec.quarantined_ids),
            'older_than_90_days':len(rec.historical_ids),'duplicate_groups':len(rec.duplicate_groups),'conflict_pairs':len(rec.conflicts),
            'invalidated_findings':len(rec.invalidated_finding_ids)},
        'conflict_groups':conflict_components(rec.conflicts,context.evidence,held),
        'duplicate_groups':groups[:MAX_DUPLICATE_GROUPS],'duplicate_groups_not_listed':max(0,len(groups)-MAX_DUPLICATE_GROUPS),
        'limitations':rec.limitations,
        'held_records':'Rejected and quarantined records are excluded: not shown, not citable, never evidence.'}


def compact_coverage(coverage):
    rows=[{k:c[k] for k in COVERAGE_KEYS if k in c and c[k] not in (None,[],'')} for c in coverage]
    return rows


def record_totals(records):
    def count(key,limit=None):
        counts={}
        for e in records:
            k=key(e);counts[k]=counts.get(k,0)+1
        ordered=sorted(counts.items(),key=lambda kv:(-kv[1],kv[0]))
        if limit and len(ordered)>limit:
            rest=sum(n for _,n in ordered[limit:]);ordered=ordered[:limit]+[('(other statuses)',rest)]
        return dict(ordered)
    return {'total':len(records),'by_source':count(lambda e:e.source),'by_kind':count(lambda e:e.kind.value),
        'by_status':count(lambda e:e.status or 'unknown',MAX_STATUS_BUCKETS)}


def authority_view(source):
    """Exact excerpt, temporal limits and provenance stay; URL and topics are runtime-owned. Summary only when there is no excerpt."""
    d=source.model_dump(mode='json',exclude={'url','topics','summary','effective_from','effective_to'})
    d.update({k:v for k,v in source.model_dump(mode='json').items() if k in {'effective_from','effective_to'} and v})
    if not source.excerpt:d['summary']=source.summary
    return d


def agent_context(task, context, *, evidence_ids=None, findings=(), feedback=None, sources=(), max_bytes=None, max_records=MAX_SHOWN_RECORDS):
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
        'reference_domains':{'evidence_ids':[],  # Filled with the IDs of the rows actually shown.
            'authority_ids':list(dict.fromkeys(s.id for s in sources)),
            'memory_ids':[m.get('memory_id') for m in memories if m.get('memory_id')]},
        'citation_policy':'Evidence IDs support facts; retrieved authority IDs support legal conclusions; memory IDs are context only. Never interchange these registries.',
        'coverage':compact_coverage(context.source_coverage),'unresolved_questions':context.unresolved_questions,
        'reconciliation':compact_reconciliation(context,held),
        'records':record_totals([e for e in context.evidence if e.evidence_id not in held]),
        'critic_feedback':feedback.model_dump(mode='json') if feedback else None,
        'evidence':[],'authorities':[],'prior_findings':[],
        'selection':{'omitted_evidence_ids':[],'omitted_authority_ids':[],
            'invalidated_finding_ids':[f.finding_id for f in findings if f not in valid],
            'omitted_finding_ids':[], 'max_bytes':limit,
            'records_shown':0,'records_not_shown':0,
            'note':'Only original descriptions/excerpts are included. Omitted items remain in the authoritative registry; absence is not negative evidence.'}}
    if any(c.get('historical_extent_verification') for c in context.source_coverage):result['coverage_caveat']=HISTORICAL_CAVEAT
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
    for s in authorities:include('authorities',authority_view(s),'omitted_authority_ids',s.id)
    historical=set(context.reconciliation.historical_ids) if context.reconciliation else set()
    for e in evidence:
        if len(result['evidence'])>=max_records:break
        row=e.model_dump(mode='json',exclude={'metadata'})
        row['metadata']={k:v for k,v in e.metadata.items() if k in {
            'source_url','record_id','original_record_id','dataset_id','retrieved_at','updated_at',
            'origin_record_id','origin_record_components','origin_source','dataset','original_event_date',
            'bin','bbl','hpd_building_id','normalized_status','scope','source_record_id'}}
        row['identity_match_status']='accepted' if context.reconciliation and e.evidence_id in context.reconciliation.accepted_ids else 'unverified'
        if e.evidence_id in historical:row['older_than_90_days']=True
        include('evidence',row,'omitted_evidence_ids',e.evidence_id)
    for f in valid:include('prior_findings',compact_finding(f),'omitted_finding_ids',f.finding_id)
    result['reference_domains']['authority_ids']=[s['id'] for s in result['authorities']]
    result['reference_domains']['evidence_ids']=[e['evidence_id'] for e in result['evidence']]
    # The list is partial whenever any accepted record is not shown, so say so explicitly.
    registry=[e for e in context.evidence if e.evidence_id not in held]
    selection=result['selection']
    selection['records_shown']=len(result['evidence']);selection['records_not_shown']=len(registry)-len(result['evidence'])
    selection['partial_list']=(f"{selection['records_not_shown']} more records not shown ({len(result['evidence'])} of {len(registry)} accepted records included). "
        'This list is partial: a record missing here may exist in the registry and is not negative evidence; only listed evidence IDs can be cited.') if selection['records_not_shown'] else 'All accepted records are shown.'
    while context_bytes(result)>limit and result['evidence']:  # Final counters can add a few bytes; drop rows, never mandatory fields.
        row=result['evidence'].pop();selection['omitted_evidence_ids'].append(row['evidence_id'])
        result['reference_domains']['evidence_ids'].pop()
        selection['records_shown']-=1;selection['records_not_shown']+=1
        selection['partial_list']=f"{selection['records_not_shown']} more records not shown ({selection['records_shown']} of {len(registry)} accepted records included). This list is partial: a record missing here may exist in the registry and is not negative evidence; only listed evidence IDs can be cited."
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
