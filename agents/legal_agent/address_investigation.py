"""Conductor-facing address investigation, no competing agent or memory store."""
from collections import Counter
from datetime import UTC, datetime
import json
from itertools import product
import re

if __package__ and __package__.startswith("agents.legal_agent"):
    from .agents.planner import RISK_CATEGORIES, plan_sources
else:
    from agents.planner import RISK_CATEGORIES, plan_sources
if __package__ and __package__.startswith("agents.legal_agent"):
    from .identity import match_record, normalize_address, resolve_building_identity
else:
    from identity import match_record, normalize_address, resolve_building_identity
if __package__ and __package__.startswith("agents.legal_agent"):
    from .integration import board_update, review_records, root_critic, validate_reviewed_matches
else:
    from integration import board_update, review_records, root_critic, validate_reviewed_matches
if __package__ and __package__.startswith("agents.legal_agent"):
    from .models.identity import IdentityResult
else:
    from models.identity import IdentityResult
if __package__ and __package__.startswith("agents.legal_agent"):
    from .models.schemas import InvestigationContext, LegalIssueTask
else:
    from models.schemas import InvestigationContext, LegalIssueTask
if __package__ and __package__.startswith("agents.legal_agent"):
    from .tools.address_data import SourceRetrieval, equals, literal
else:
    from tools.address_data import SourceRetrieval, equals, literal
if __package__ and __package__.startswith("agents.legal_agent"):
    from .tools.risk_mapping import BOROUGHS, identifier_where, map_source_rows
else:
    from tools.risk_mapping import BOROUGHS, identifier_where, map_source_rows
if __package__ and __package__.startswith("agents.legal_agent"):
    from .tools.source_registry import load_registry
else:
    from tools.source_registry import load_registry
if __package__ and __package__.startswith("agents.legal_agent"):
    from .tools.zetaris import map_hpd_building
else:
    from tools.zetaris import map_hpd_building
if __package__ and __package__.startswith("agents.legal_agent"):
    from .workflow import LegalResearchWorkflow
else:
    from workflow import LegalResearchWorkflow

if __package__ and __package__.startswith("agents.legal_agent"):
    from .tools.execution import ExecutionBudget, ExecutionStopped
else:
    from tools.execution import ExecutionBudget, ExecutionStopped

BOROUGH_ALIASES={'MANHATTAN':'1','NEW YORK':'1','BRONX':'2','THE BRONX':'2','BROOKLYN':'3','QUEENS':'4','STATEN ISLAND':'5'}


def parse_address(address, borough=None, unit=None):
    if not isinstance(address,str) or not address.strip() or len(address)>300:
        raise ValueError('Supply a NYC street address')
    original=address
    named=[v for k,v in BOROUGH_ALIASES.items() if k!='NEW YORK' and re.search(r'(?:,|\s)'+re.escape(k)+r'(?:,|\s|$)',address.upper())]
    inferred=named or (['1'] if re.search(r',\s*NEW YORK(?:,|\s|$)',address.upper()) else [])
    if borough:
        code=BOROUGH_ALIASES.get(str(borough).upper(),str(borough))
        if code not in BOROUGHS:raise ValueError('Unknown NYC borough')
        if named and code not in named:raise ValueError('Address and supplied borough conflict')
    else:code=inferred[0] if len(set(inferred))==1 else None
    unit_match=re.search(r'\b(?:APT\.?|UNIT|APARTMENT)\s+([^,\s]+)',address,re.I)
    canonical,inline_unit=normalize_address(address)
    parts=canonical.split(maxsplit=1)
    supplied_unit=unit_match.group(1) if unit_match else inline_unit
    if unit and supplied_unit and str(unit).upper()!=supplied_unit.upper():
        raise ValueError('Address and supplied unit conflict')
    if len(parts)!=2 or not re.fullmatch(r'\d+[A-Z]?(?:-\d+[A-Z]?)?',parts[0]):
        raise ValueError('Supply a house number and street; PO boxes and intersections require manual resolution')
    return {'original_input':original,'normalized_address':canonical,'house_number':parts[0],
            'street':parts[1],'borough_code':code,'borough':BOROUGHS.get(code),
            'unit':unit or (unit_match.group(1) if unit_match else inline_unit)}


def building_where(source,request):
    street=request['street']
    full=street
    for short,long in [('ST','STREET'),('AVE','AVENUE'),('BLVD','BOULEVARD'),('RD','ROAD'),('PL','PLACE'),('E','EAST'),('W','WEST'),('N','NORTH'),('S','SOUTH')]:
        full=re.sub(r'\b'+short+r'\b',long,full)
    variants={street,full}
    expansions={'ST':('ST','STREET','SAINT'),'AVE':('AVE','AVENUE'),'BLVD':('BLVD','BOULEVARD'),
        'RD':('RD','ROAD'),'PL':('PL','PLACE'),'E':('E','EAST'),'W':('W','WEST'),'N':('N','NORTH'),'S':('S','SOUTH')}
    for tokens in product(*(expansions.get(token,(token,)) for token in street.split())):
        variants.add(' '.join(tokens))
        if len(variants)>=32:break
    number=request['house_number']
    clause='('+' OR '.join(equals(source,f,number) for f in ('housenumber','lowhousenumber','highhousenumber'))+')'
    clause+=' AND ('+' OR '.join('upper(streetname) = '+literal(s) for s in sorted(variants))+')'
    if request['borough_code']:clause+=' AND '+equals(source,'boroid',request['borough_code'])
    return clause


def _factual_finding(record,match,source):
    descriptions={
        'complaint':'An agency received a reported problem. This does not establish a verified condition.',
        'confirmed_violation':'An agency violation is recorded. Its date and status do not independently establish present conditions.',
        'permit':'Recorded permitted activity may affect access or construction conditions; a permit is not evidence of unsafe work.',
        'case_filing':'A filing/proceeding is recorded. It is not automatically a judgment or finding of wrongdoing.',
        'executed_eviction':'A marshal-executed action is recorded for the stated scope/date; it does not predict another tenancy outcome.',
        'other':'This official administrative/registration record may guide further verification; its stated status must be read in context.'}
    meanings={'hpd_registrations':'Identifies the recorded registration and its dates; it does not independently establish current ownership or compliance.',
              'registration_contacts':'Identifies a contact listed in the linked property registration, which may help direct verification; it is not independent proof of ownership or liability.',
              'hpd_aep':'Records selection/status in an HPD enforcement program; check dates and current status rather than assuming ongoing conditions.',
              'conh':'Records inclusion in a special HPD reference list; verify protections and any separately reported findings without inferring apartment rent status.'}
    return {'finding_id':'fact-'+record.evidence_id,'evidence_ids':[record.evidence_id],
            'categories':source['categories'],'description':record.description,'agency':source['publisher'],
            'record_id':record.metadata['origin_record_id'],'dataset':source['dataset'],
            'kind':record.kind.value,'severity':record.violation_class,'event_date':str(record.date) if record.date else None,
            'recorded_status':record.status,'scope':match.scope,'match_method':record.metadata.get('match_method',match.method),
            'attribution_review':match.method,
            'match_reason':match.reason,'source_url':record.metadata['source_url'],
            'retrieved_at':record.metadata['retrieved_at'],'why_it_matters':meanings.get(source['key'],descriptions.get(record.kind.value,'Consult the agency event and its original status; no legal outcome is inferred.')),
            'unknowns':['Current conditions and unit-specific applicability are not independently verified.',*source.get('limitations',[])]}


def investigate_address(provider,address,*,borough=None,unit=None,goals=(),registry=None,max_corrections=2,workflow=None,budget=None,reasoning_mode=None):
    budget=budget or getattr(provider,"budget",None) or ExecutionBudget()
    provider.budget=budget
    if budget.trace.task_id=="address-investigation":budget.trace.task_id="address-"+budget.trace.run_id
    budget.trace.emit("investigation.started",provider=provider.name)
    registry=registry or load_registry()
    request=parse_address(address,borough,unit)
    plan=plan_sources(registry,goals)
    activity=[{'action':'plan_sources',**plan}]
    retrievals=[];coverage={};evidence=[];identity_records=[];trace=[];root_history=[];facts=[];legal_result=None;board={};lot_context=None
    def get(source,where,field,**kw):
        budget.check()
        budget.trace.emit("source.selected",source=source["key"],match_field=field)
        result=provider.fetch_where(source,where,match_field=field,**kw)
        budget.trace.emit("source.retrieved",source=source["key"],status=result.status,count=len(result.rows))
        retrievals.append(result.as_dict())
        prior=coverage.get(source['key'])
        coverage[source['key']]={'source':source['key'],'title':source['title'],'publisher':source['publisher'],
            'source_url':source['source_url'],'status':result.status,'complete_for_filter':result.complete,
            'records_returned':len(result.rows),'pages':len(result.pages),'reason':result.reason,
            'match_field':field,'update_frequency':source.get('update_frequency'),
            'historical_coverage':source.get('coverage_description','Not specified'),
            'historical_extent_verification':source.get('historical_extent_verification'),
            'limitations':source.get('limitations',[])}
        attempt={'filter':where,'status':result.status,'rows':len(result.rows),'complete_for_filter':result.complete}
        coverage[source['key']]['attempts']=[*prior.get('attempts',[]),attempt] if prior else [attempt]
        if prior:
            coverage[source['key']]['records_returned']+=prior.get('records_returned',0)
            coverage[source['key']]['complete_for_filter']=bool(result.complete and prior.get('complete_for_filter'))
            coverage[source['key']]['count_note']='Rows across retrieval attempts; repeated origin IDs are not independent evidence.'
        activity.append({'action':'retrieve','source':source['key'],'status':result.status,'records':len(result.rows),'reason':result.reason})
        return result
    try:
        budget.check()
        source=registry['hpd_buildings']
        identity_query=get(source,building_where(source,request),'address_and_borough')
        candidates=[]
        if identity_query.status in {'retrieved','bounded','no_records'}:
            for row in identity_query.rows:
                candidate,record=map_hpd_building(row,retrieved_at=datetime.fromisoformat(identity_query.pages[-1]['retrieved_at']),provider=provider.name)
                # Only source-supplied range endpoints become aliases, not every
                # number between them. Preserve their provenance in the audit.
                if normalize_address(candidate.address)[0]!=request['normalized_address'] and request['house_number'] in {str(row.get('lowhousenumber')),str(row.get('highhousenumber'))}:
                    candidate.aliases.append(request['normalized_address'])
                    record.metadata['alias_provenance']={k:row.get(k) for k in ('lowhousenumber','highhousenumber','streetname')}
                candidates.append(candidate);identity_records.append(record)
        identity=IdentityResult.model_validate(resolve_building_identity(request['normalized_address'],{'candidates':[c.model_dump(mode='json') for c in candidates],'borough':request['borough'],'unit':request['unit']}))
        if not identity_query.complete:
            identity.verification_status='ambiguous' if candidates else 'missing'
            identity.ambiguities.append('Identity source query was unavailable or bounded; uniqueness cannot be established.')
        budget.trace.emit('identity.decided',status=identity.verification_status,candidate_count=len(candidates))
        activity.append({'action':'resolve_identity','status':identity.verification_status,'candidate_count':len(candidates),'ambiguities':identity.ambiguities})
        registration_records=[]
        if identity.verification_status=='verified':
            bbl=identity.identifiers.get('bbl')
            if bbl:
                source=registry['hpd_buildings']
                lot_where=' AND '.join(equals(source,k,v) for k,v in [('boroid',bbl[0]),('block',str(int(bbl[1:6]))),('lot',str(int(bbl[6:])))])
                budget.trace.emit('source.selected',source=source['key'],match_field='lot_context')
                lot=provider.fetch_where(source,lot_where,match_field='lot_context',max_pages=1)
                budget.trace.emit('source.retrieved',source=source['key'],status=lot.status,count=len(lot.rows))
                retrievals.append(lot.as_dict())
                lot_context={'bbl':bbl,'status':lot.status,'complete_for_filter':lot.complete,
                    'building_ids':[str(r['buildingid']) for r in lot.rows],
                    'limitation':'Tax-lot evidence remains property-scoped. A unique target HPD building ID is not permission to attribute every lot record to that building.'}
                activity.append({'action':'cross_check_lot','status':lot.status,'buildings_returned':len(lot.rows)})
            for key in plan['selected_sources']:
                budget.check()
                if key=='hpd_buildings':continue
                source=registry[key]
                if source.get('capability')=='manual_only':
                    get(source,'','manual');continue
                parents=registration_records[:3] if key=='registration_contacts' else [None]
                if not parents:
                    coverage[key]={'source':key,'title':source['title'],'status':'not_queried_missing_registration','complete_for_filter':False,'reason':'No verified registration parent available'}
                for parent in parents:
                    where,field=identifier_where(source,identity,registration_id=parent.metadata['origin_record_id'] if parent else None)
                    if where is None:
                        coverage[key]={'source':key,'title':source['title'],'status':'unsupported_property_linkage','complete_for_filter':False,'reason':'No reliable identifier or audited address strategy available'}
                        continue
                    result=get(source,where,field)
                    if result.status not in {'retrieved','bounded','no_records'}:continue
                    mapped=map_source_rows(source,result,linked_registration=parent)
                    if key=='hpd_registrations':registration_records.extend(mapped)
                    evidence.extend(mapped)
            # Prevent ambiguous source identities instead of silently collapsing
            # contradictory rows or interpreting same-day records as duplicates.
            unique={}
            for record in evidence:
                budget.check()
                if record.evidence_id in unique:
                    raise ValueError('Source record identity repeated across retrievals')
                unique[record.evidence_id]=record
                match=match_record(record,identity)
                record.metadata.update(matcher_confidence=match.confidence,match_method=match.method)
            card={'address_raw':identity_records[0].building_address,**identity.identifiers}
            matches,trace=review_records(evidence,card,budget=budget)
            root_history.append({"review_round":len(root_history),"decisions":list(trace)})
            # Clear attribution conflicts can request one stricter identifier
            # query per affected source, bounded globally. Never force a retry
            # for R5: its false-duplicate risk belongs to the Critic owner.
            remaining=max(0,min(max_corrections,2))
            for key in dict.fromkeys(r.metadata['source_key'] for r,d in zip(evidence,trace) if d['rule'] in {'R1','R2'}):
                if not remaining:break
                source=registry[key]
                clauses=[equals(source,f,identity.identifiers[k]) for k,f in source['identifiers'].items() if k in identity.identifiers]
                if len(clauses)<2:continue
                remaining-=1
                follow=get(source,' AND '.join(clauses),'correction_cross_identifiers',max_pages=1)
                original={json.dumps(r.metadata['raw_record'],sort_keys=True) for r in evidence if r.metadata['source_key']==key}
                returned={json.dumps(r,sort_keys=True) for r in follow.rows}
                unchanged=returned==original
                activity.append({'action':'matcher_follow_up','source':key,'reason':'Critic rejected identifier attribution; requested cross-identifier verification','status':follow.status,'unchanged_results_stop':unchanged})
                if follow.status in {'retrieved','bounded'} and not unchanged:
                    for record in map_source_rows(source,follow):
                        if record.evidence_id not in unique:
                            match=match_record(record,identity)
                            record.metadata.update(matcher_confidence=match.confidence,match_method=match.method)
                            unique[record.evidence_id]=record;evidence.append(record)
                    matches,trace=review_records(evidence,card,budget=budget)
                    root_history.append({"review_round":len(root_history),"decisions":list(trace)})
                # Existing held records are never silently replaced or promoted.
            matches=validate_reviewed_matches(evidence,identity,matches,budget=budget)
            for match in matches:budget.trace.emit('evidence.'+match.decision,evidence_id=match.evidence_id,method=match.method)
            accepted={m.evidence_id for m in matches if m.decision=='accepted'}
            activity.append({'action':'critic_attribution','accepted':len(accepted),
                'held':len(matches)-len(accepted),'root_rules':dict(Counter(d['rule'] or d['decision'] for d in trace))})
            critic=root_critic()
            for record,match in zip(evidence,matches):
                budget.check()
                if record.evidence_id not in accepted:continue
                finding_decision=critic.review_finding({'record_ids':[record.evidence_id]},accepted)
                budget.trace.emit('root_critic.decision',phase='factual_finding',record_id=record.evidence_id,decision=finding_decision['decision'],rule=finding_decision['rule'])
                if finding_decision['decision']=='accept':
                    facts.append(_factual_finding(record,match,registry[record.metadata['source_key']]))
            mode=getattr(provider,'data_mode','live' if provider.name=='zetaris' else 'development_fallback')
            task=LegalIssueTask(task_id=budget.trace.task_id,
                question='Due diligence before signing: interpret accepted property records with explicit coverage and legal applicability limits.',
                building=dict(address=identity_records[0].building_address,borough=identity.borough,unit=request['unit'],bin=identity.identifiers.get('bin'),bbl=identity.identifiers.get('bbl')),
                evidence_ids=[r.evidence_id for r in evidence])
            context=InvestigationContext(data_mode=mode,data_provider=provider.name,identity=identity,record_matches=matches,evidence=evidence,source_coverage=list(coverage.values()),as_of=datetime.now(UTC).date())
            legal_result=(workflow or LegalResearchWorkflow(reasoning_mode=reasoning_mode)).run(task,context,budget=budget)
            activity.append({'action':'legal_investigation','status':legal_result.status.value,
                'revision_cycles':legal_result.revision_cycles,'tool_calls':legal_result.tool_calls,'reasoning_mode':legal_result.reasoning_mode})
            board=board_update(legal_result,evidence,trace,budget=budget)
            legal_result.citation_metrics["published_legal_findings"]=len(board["legal_findings"])
            # Factual membership is independent of legal certainty. No held
            # record supports a fact, even if the final legal review is REVISE.
            board['factual_findings']=facts
            board['source_coverage']=list(coverage.values())
            board['identity_source_records']=[r.model_dump(mode='json') for r in identity_records]
        for key,source in registry.items():
            if key not in coverage:
                status='disabled_by_config' if not source.get('enabled',True) else 'manual_only' if source.get('capability')=='manual_only' else 'not_selected' if key not in plan['selected_sources'] else 'not_queried_identity_unresolved'
                coverage[key]={'source':key,'title':source['title'],'source_url':source['source_url'],'status':status,'complete_for_filter':False,'reason':' '.join(source.get('limitations',[])) if status=='manual_only' else 'No reliable property identity' if status=='not_queried_identity_unresolved' else 'Not selected for these goals'}
        counts=Counter(f['dataset'] for f in facts)
        patterns=[{'source_dataset':dataset,'record_count':count,'evidence_ids':[f['evidence_ids'][0] for f in facts if f['dataset']==dataset],
                   'explanation':'Multiple accepted records in the retrieved slice; this count alone does not prove recurrence of the same condition or current hazard.'} for dataset,count in counts.items() if count>1]
        groups={}
        for fact in facts:
            record=next(r for r in evidence if r.evidence_id==fact['evidence_ids'][0])
            raw=record.metadata['raw_record']
            code=raw.get('ordernumber') or raw.get('major_category') or raw.get('complaint_category') or raw.get('violation_type')
            if code:groups.setdefault((fact['dataset'],str(code)),[]).append(fact)
        for (dataset,code),items in groups.items():
            dates={f['event_date'] for f in items if f['event_date']}
            if len(dates)>1:
                patterns.append({'source_dataset':dataset,'record_count':len(items),'evidence_ids':[f['evidence_ids'][0] for f in items],
                    'explanation':f'Agency category/code {code} appears on {len(dates)} distinct recorded dates in this slice. This documents repeated records, not continuous present conditions.'})
        report={'schema_version':'2.0','report_type':'tenant_risk_investigation','generated_at':datetime.now(UTC).isoformat(),'request':request,
            'data_mode':getattr(provider,'data_mode','live' if provider.name=='zetaris' else 'development_fallback'),
            'provider':provider.name,'identity':identity.model_dump(mode='json'),'lot_context':lot_context,
            'retrieval_status':'identity_unresolved' if identity.verification_status!='verified' else 'bounded_or_partial' if any(not c.get('complete_for_filter') for c in coverage.values()) else 'complete_for_selected_filters',
            'coverage':list(coverage.values()),'categories':list(RISK_CATEGORIES),'factual_findings':facts,'patterns':patterns,
            'legal_assessment':legal_result.model_dump(mode='json') if legal_result else {'status':'not_performed_identity_unresolved'},
            'identity_source_records':[r.model_dump(mode='json') for r in identity_records],
            'evidence_audit':[r.model_dump(mode='json') for r in evidence],'record_decisions':trace,'root_critic_history':root_history,
            'activity_log':activity,'retrievals':retrievals,'board_update':board,
            'limitations':['Data coverage applies to exact queried filters and retrieval time, not a complete history or independent inspection.',
                'Paginated live datasets may change during a run; no transactional snapshot is promised.',
                'R5 may hold distinct same-day records as collisions; held records cannot support published findings. No Critic rule was bypassed.',
                'No safety, liability, apartment rent status or litigation-free certification is made. Court sources require manual verification.']}
    except (Exception,KeyboardInterrupt) as error:
        stopped=isinstance(error,ExecutionStopped)
        failure_message=str(error) if stopped else 'Investigation interrupted.' if isinstance(error,KeyboardInterrupt) else 'Investigation failed during source processing or review; inspect the structured trace.'
        budget.trace.emit('investigation.stopped',status='execution_stopped' if stopped else 'pipeline_error',error_type=type(error).__name__,stop_reason=failure_message)
        activity.append({'action':'hard_stop','reason':failure_message,'budget':budget.snapshot()})
        stopped_identity=locals().get('identity') or IdentityResult(canonical_address=request['normalized_address'])
        report={'schema_version':'2.0','report_type':'tenant_risk_investigation','generated_at':datetime.now(UTC).isoformat(),
            'request':request,'provider':provider.name,'data_mode':getattr(provider,'data_mode','live' if provider.name=='zetaris' else 'development_fallback'),
            'identity':stopped_identity.model_dump(mode='json'),'lot_context':lot_context,'retrieval_status':'budget_exhausted' if stopped else 'failed',
            'coverage':list(coverage.values()),'categories':list(RISK_CATEGORIES),'factual_findings':facts,'patterns':[],
            'legal_assessment':{'status':'inconclusive' if stopped else 'error','errors':[{'code':'execution_stopped' if stopped else 'pipeline_error','message':failure_message}]},
            'identity_source_records':[r.model_dump(mode='json') for r in identity_records],
            'evidence_audit':[r.model_dump(mode='json') for r in evidence],'record_decisions':trace,'root_critic_history':root_history,
            'activity_log':activity,'retrievals':retrievals,'board_update':board,
            'limitations':[failure_message,'Unqueried sources and legal applicability remain unknown.']}
    finally:
        provider.close()
    report['execution']=budget.snapshot()
    report['provider_activity']=provider.events
    if any(e.get('action')=='cleanup' and e.get('status')=='failed' for e in provider.events):
        report['limitations'].append('Temporary namespace cleanup failed. Its name is in provider_activity; operator cleanup is required before further runs accumulate.')
    if not board:
        board.update(task_id='unresolved-address',request=request,identity=report['identity'],
            factual_findings=[],source_evidence=[],identity_source_records=report['identity_source_records'],
            follow_up_requests=['Resolve official building identity and any address ambiguity before attributing records.'],summary_is_evidence=False)
    board['source_coverage']=report['coverage'];board['activity_log']=activity;board['provider_activity']=provider.events
    requests=board.setdefault('follow_up_requests',[])
    for coverage_item in report['coverage']:
        if coverage_item['status'] in {'unavailable','bounded','budget_exhausted','unsupported_property_linkage'}:
            requests.append(f'Data investigator: verify {coverage_item["title"]}; {coverage_item.get("reason") or coverage_item["status"]}. Do not infer clean history from this gap.')
    budget.trace.emit("investigation.finished",retrieval_status=report["retrieval_status"])
    report["activity_events"]=budget.trace.events
    return report
