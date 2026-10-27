"""Renter facts, retrieval coverage, and legal uncertainty are separate layers."""
import json
from pathlib import Path


def write_risk_report(report,output_dir):
    output=Path(output_dir);output.mkdir(parents=True,exist_ok=True)
    (output/'investigation_report.json').write_text(json.dumps(report,indent=2)+'\n')
    identity=report['identity'];legal=report['legal_assessment']
    lines=['# NYC tenant-risk investigation','',report['request']['original_input'],'',
           f'Provider: {report["provider"]}; mode: {report["data_mode"]}.',
           f'Data retrieval: {report["retrieval_status"]}. Legal assessment: {legal.get("status")}.',
           '', 'These are separate assessments. Legal uncertainty does not suppress accepted official-record facts.',
           '', '## Property identity', '',f'{identity["canonical_address"]}; {identity["verification_status"]}.','']
    if report.get('run_id'):
        lines[2:2]=[f'Run ID: {report["run_id"]}',f'Trace: trace.jsonl; run summary: run_summary.json. Elapsed: {report.get("execution",{}).get("elapsed_seconds",0):.2f} seconds.','']
    lines.extend(f'- {k}: {v}' for k,v in identity['identifiers'].items())
    lines.extend('- '+text for text in identity['ambiguities'])
    if report.get('lot_context'):
        lot=report['lot_context']
        lines+=['',f'Tax-lot cross-check: {len(lot["building_ids"])} HPD building IDs returned; complete for filter={lot["complete_for_filter"]}. '+lot['limitation']]
    for category in report['categories']:
        lines+=['','## '+category.replace('_',' ').title(),'']
        findings=[f for f in report['factual_findings'] if category in f['categories']]
        if not findings:
            lines+=['No accepted finding is available for this category. See source coverage; this is not proof that no issue exists.']
        for fact in findings:
            lines+=[f'- [{fact["dataset"]}:{fact["record_id"]}]({fact["source_url"]}): {fact["description"]}',
                    f'  Agency: {fact["agency"]}; date: {fact["event_date"] or "not supplied/parsed"}; recorded status: {fact["recorded_status"] or "not supplied"}; class/severity: {fact["severity"] or "not supplied"}.',
                    f'  Match: {fact["match_method"]}; scope: {fact["scope"]}; retrieved: {fact["retrieved_at"]}.',
                    '  Why it may matter: '+fact['why_it_matters']]
            lines.extend('  Unknown: '+s for s in fact['unknowns'])
    lines+=['','## Patterns within the retrieved slice','']
    lines.extend(f'- {p["source_dataset"]}: {p["record_count"]} accepted records. {p["explanation"]} Evidence: {", ".join(p["evidence_ids"])}' for p in report['patterns'])
    lines+=['','## Source-by-source coverage','']
    for c in report['coverage']:
        lines += [f'- {c["title"]}: {c["status"]}; rows={c.get("records_returned",0)}; complete for exact filter={c["complete_for_filter"]}. {c.get("reason","")}',
                  f'  Source: {c.get("source_url","")}; update frequency: {c.get("update_frequency") or "see source reference"}.']
    lines+=['','## Legal background and unresolved questions','']
    for source in legal.get('legal_sources',[]):
        lines.append(f'- [{source["title"]}]({source["url"]}): {source["temporal_limitations"]}')
    lines.extend('- '+i['message'] for i in legal.get('critic_issues',[]))
    if legal.get('citation_metrics'):
        metrics=legal['citation_metrics']
        lines+=['','## Citation grounding checks','',f'Cited claims: {metrics.get("cited_claims",0)}; valid source identity: {metrics.get("claims_with_valid_source_identity",0)}; independently verified source-text support: {metrics.get("claims_with_verified_support",0)}; published legal findings: {metrics.get("published_legal_findings",0)}.', 'Source-text support is distinct from historical applicability or a property liability finding.']
    lines+=['','## Reviewed legal findings','']
    published=report.get('board_update',{}).get('legal_findings',[])
    if not published:lines.append('No legal findings cleared the publication gate. Draft interpretations in the JSON audit are not approved conclusions.')
    for finding in published:
        lines.append('- '+finding['summary'])
        lines.append('  Evidence: '+', '.join(finding.get('evidence_ids',[])))
        for conclusion in finding.get('legal_conclusions',[]):
            lines.append('  '+conclusion['statement']+' Authorities: '+', '.join(conclusion.get('source_ids',[])))
    if legal.get('errors'):
        lines+=['','## Termination errors','']
        lines.extend('- '+error['code']+': '+error['message'] for error in legal['errors'])
    lines+=['','## Critic review history','']
    for index,review in enumerate(legal.get('review_history',[])):
        lines.append(f'- Legal review {index+1}: {review["outcome"]}; {review.get("reasoning_mode","unspecified")}.')
    for entry in report.get('root_critic_history',[]):
        lines.append(f'- Root attribution round {entry["review_round"]}: {len(entry["decisions"])} decisions retained in JSON and trace.')
    lines+=['','## Held and quarantined evidence','']
    for d in report['record_decisions']:
        if d['decision']!='accept':lines.append(f'- {d["record_id"]}: {d["decision"]}, {d["rule"]}; {d["reason"]}')
    # Legal scope can be stricter than the root's attribution review.
    for m in report.get('board_update',{}).get('legal_record_matches',[]):
        if m['decision']!='accepted':lines.append(f'- Legal scope review {m["evidence_id"]}: {m["decision"]}; {m["reason"]}')
    lines+=['','## Follow-up verification','']
    lines.extend('- '+x for x in [*report['limitations'],*legal.get('research_requests',[])])
    for c in report['coverage']:
        if c['status'] in {'manual_only','unavailable','bounded','budget_exhausted','unsupported_property_linkage'}:
            lines.append(f'- Verify {c["title"]}: {c.get("reason") or c["status"]}.')
    lines+=['','## Agent activity and retrieval audit','']
    lines.extend('- '+json.dumps(e,ensure_ascii=False) for e in report['activity_log'])
    lines+=['','Complete original records, query URLs, page timestamps, source decisions, legal review and Keeper board update are in investigation_report.json.']
    (output/'investigation_report.md').write_text('\n'.join(lines)+'\n')
    return output/'investigation_report.md'


def verdict_section(report,text,link):
    """Top-of-report verdict block; empty when the report predates the verdict layer."""
    verdict=report.get('verdict')
    if not verdict:return []
    lines=['## Verdict','','**'+text(verdict.get('verdict'))+'**','']
    for rule in verdict.get('rules_fired') or []:
        urls=rule.get('source_urls') or []
        refs=', '.join(link(e,urls[i] if i<len(urls) else None) for i,e in enumerate(rule.get('evidence_ids') or []))
        lines.append('- **'+text(rule.get('level'))+'** ('+text(rule.get('rule_id'))+'): '+text(rule.get('summary'))+' Records: '+refs+'.')
    if not verdict.get('rules_fired'):
        reasons=(verdict.get('basis') or {}).get('not_enough_data_reasons') or []
        lines.extend('- '+text(r) for r in reasons) if reasons else lines.append('- No verdict rule fired for the records and sources checked.')
    unavailable=(verdict.get('basis') or {}).get('sources_unavailable') or []
    disclaimer=verdict.get('disclaimer') or ''
    # The disclaimer already names unavailable sources; add the note only if it does not.
    if not unavailable or 'Sources not checked' not in disclaimer:
        lines+=['','Sources not checked or incomplete: '+(', '.join(text(u) for u in unavailable) if unavailable else 'none reported')+'.']
    lines+=['',text(disclaimer),'']
    return lines


def write_renter_report(report,output_dir):
    """Presentation only: render accepted facts and already publishable legal findings."""
    import html
    import re
    from urllib.parse import quote,urlsplit
    def text(value,default='Not supplied'):
        value=default if value is None or value=='' else str(value)
        value=html.escape(' '.join(value.split()),quote=False)
        return re.sub(r'([\\`*_[\]{}<>#|])',r'\\\1',value)
    def link(label,url):
        label=text(label)
        try:
            parsed=urlsplit(str(url or ''))
            if parsed.scheme not in {'https','http'} or not parsed.netloc or parsed.username or parsed.password:return label+' (source link not supplied)'
            return '['+label+']('+quote(str(url),safe=':/?&=%#+;,-._~')+')'
        except ValueError:return label+' (source link not supplied)'
    def unique(values):return list(dict.fromkeys(str(v) for v in values if v))
    identity=report.get('identity') or {};legal=report.get('legal_assessment') or {};board=report.get('board_update') or {}
    facts=report.get('factual_findings') or [];coverage=report.get('coverage') or []
    # board_update owns the gate. Extra checks fail closed on malformed report input.
    reviewed=legal.get('status')=='completed' and legal.get('critic_outcome')=='PASS' and board.get('critic_outcome')=='PASS'
    published=board.get('legal_findings',[]) if reviewed else []
    gaps=[c for c in coverage if not c.get('complete_for_filter') or c.get('status') in {'unavailable','manual_only','budget_exhausted','failed'}]
    status='INCONCLUSIVE' if not facts or legal.get('critic_outcome')=='BLOCKED' else 'COMPLETE' if reviewed and coverage and not gaps and identity.get('verification_status') in {'verified','sample'} else 'PARTIAL'
    factual_only=not published
    address=(report.get('request') or {}).get('original_input') or identity.get('canonical_address') or 'Address not supplied'
    lines=['# Renter assessment','', '**'+status+(' — FACTUAL-ONLY ASSESSMENT' if factual_only else ' — REVIEWED RECORD ASSESSMENT')+'**','',
        *verdict_section(report,text,link),
        '## Property overview','',text(address),
        '- Investigation date: '+text(report.get('generated_at')),
        '- Identity: '+text(identity.get('verification_status')),
        '- Coverage: **'+status+'**. Data: '+text(report.get('provider'))+'; '+text(report.get('data_mode'))+'.']
    if identity.get('canonical_address') and identity['canonical_address']!=address:
        lines.append('- Agency-normalized address: '+text(identity['canonical_address'])+'.')
    identifiers=identity.get('identifiers') or {}
    if identity.get('verification_status')=='verified' and identifiers:
        lines.append('- Verified building identifiers: '+', '.join(text(k).upper()+': '+text(v) for k,v in identifiers.items())+'.')
    lines+=['','## Executive summary','']
    if facts:
        summary=f'This investigation retained {len(facts)} accepted agency '+('record.' if len(facts)==1 else 'records.')
        violations=sum(f.get('kind')=='confirmed_violation' for f in facts)
        if violations:summary+=f' These include {violations} recorded '+('violation' if violations==1 else 'violations')+'; original dates and statuses are shown below, including dismissed or closed records where present.'
        else:summary+=' The observations below describe administrative records and reported activity, rather than independently verified current conditions.'
        summary+=' These records do not establish current safety, unit status or legal liability.'
    else:summary='No accepted factual findings were available at termination. This does not establish that the property has no problems.'
    summary+=' Legal assessment remains incomplete.' if not published else 'The legal context below contains only findings cleared for publication.'
    lines.append(summary)
    topics=['Building maintenance and housing violations','Building safety and DOB violations','Permits and construction activity','Litigation and administrative proceedings','Other relevant records']
    groups={topic:[] for topic in topics}
    for fact in facts:
        dataset=fact.get('dataset');categories=fact.get('categories') or [];kind=fact.get('kind')
        if dataset in {'ipu4-2q9a','ic3t-wcy2','rbx6-tga4','w9ak-ipjd'} or kind=='permit':topic=topics[2]
        elif dataset in {'59kj-x8nc','jz4z-kudi','6z8x-wfk4'} or kind in {'case_filing','executed_eviction'} or any(c in categories for c in ('litigation','eviction')):topic=topics[3]
        elif dataset in {'3h2n-5cm9','eabe-havv'}:topic=topics[1]
        elif dataset in {'wvxf-dwi5','ygpa-z7cr','erm2-nwe9'} or any(c in categories for c in ('heat','maintenance','habitability')):topic=topics[0]
        else:topic=topics[4]
        groups[topic].append(fact)
    kinds={'confirmed_violation':'Agency violation record','complaint':'Reported problem (not a confirmed violation)',
        'permit':'Permit record (not proof of unsafe work)','case_filing':'Filing or administrative proceeding (not automatically a judgment)',
        'executed_eviction':'Recorded executed eviction for the stated scope','other':'Administrative or property record'}
    caveats=[]
    for topic,items in groups.items():
        if not items:continue
        lines+=['','## '+topic,'']
        for fact in items:
            label=str(fact.get('dataset') or 'Dataset not supplied')+':'+str(fact.get('record_id') or fact.get('finding_id') or 'ID not supplied')
            lines+=['- **'+kinds.get(fact.get('kind'),'Agency record')+'** — '+link(label,fact.get('source_url')),
                '  - Date: '+text(fact.get('event_date'))+'. Original status: **'+text(fact.get('recorded_status'),'Unknown')+'**.',
                '  - Recorded detail: '+text(fact.get('description')),
                '  - Scope: '+text(fact.get('scope'))+'.']
            caveats.extend(fact.get('unknowns') or [])
    lines+=['','## Legal context','']
    if not published:lines.append('Legal assessment remains incomplete. No legal conclusions are published in this factual-only report. Draft interpretations and failed reviews remain in the investigation audit.')
    for finding in published:
        lines.append('- '+text(finding.get('summary')))
        for claim in finding.get('legal_conclusions',[]):
            lines.append('  - '+text(claim.get('statement')))
            lines.extend('    - '+link(c.get('title') or c.get('authority_id'),c.get('source_url'))+' (authority '+text(c.get('authority_id'))+').' for c in claim.get('citations',[]))
    lines+=['','## Coverage gaps and next steps','']
    no_records=[c for c in coverage if c.get('status')=='no_records' and c.get('complete_for_filter')]
    if no_records:
        lines.append('- **No records returned for the queried filters:** '+', '.join(text(c.get('title') or c.get('source')) for c in no_records)+'. This is a query result, not proof of no problems.')
    labels={'bounded':'Pagination limited','manual_only':'Manual verification required','unavailable':'Unavailable','budget_exhausted':'Execution limit reached','failed':'Retrieval failed','not_selected':'Not selected','not_queried_identity_unresolved':'Identity unresolved','unsupported_property_linkage':'Property linkage unavailable','no_records':'Incomplete query; no rows in retrieved slice'}
    grouped_gaps={}
    for c in gaps:grouped_gaps.setdefault((c.get('status'),c.get('reason')),[]).append(c.get('title') or c.get('source') or 'Source not supplied')
    for (state,reason),titles in grouped_gaps.items():
        lines.append('- **'+labels.get(state,'Incomplete coverage')+':** '+', '.join(text(title) for title in titles)+'. '+text(reason,'The source was not fully checked.'))
    if not coverage:lines.append('- Source coverage was not supplied; completeness cannot be established.')
    caveats.extend(report.get('limitations') or [])
    for caveat in unique(caveats):
        if caveat.startswith('Exact issuing_agency value '):continue  # Probe implementation detail remains in JSON.
        if caveat.startswith('Socrata internal :id '):caveat='Some permit queries used alternate pagination after a timeout; citations retain the original agency record IDs.'
        if caveat.startswith('R5 holds '):caveat='Records that looked like exact duplicates of another record were held and not counted.'
        lines.append('- '+text(caveat))
    lines+=['- Next steps: check updated agency records and the status of listed items; obtain an independent inspection for current conditions. Use the agency or court references above for unavailable records and unit-specific questions.',
        '', '## Sources','',
        'Official record links and original IDs appear beside each finding. Complete source records, retrieval timestamps, contradictory/held evidence, legal review history and provenance remain in investigation_report.json. Execution events remain in trace.jsonl.']
    output=Path(output_dir);output.mkdir(parents=True,exist_ok=True)
    path=output/'renter_report.md';path.write_text('\n'.join(lines)+'\n');return path
