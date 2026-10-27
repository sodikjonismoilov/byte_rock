"""Run the existing address pipeline and always save per-run reports and activity."""
import argparse
from datetime import datetime, UTC
import json
import os
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from agents.legal_agent.address_investigation import investigate_address, RISK_CATEGORIES
from agents.legal_agent.risk_reporting import write_risk_report, write_renter_report
from agents.legal_agent.events import ActivityTrace, JSONLEventSink, sanitize
from agents.legal_agent.tools.execution import ExecutionBudget, ExecutionLimits, ExecutionStopped
from agents.legal_agent.tools.address_data import DynamicNYCDevelopmentProvider, DynamicZetarisProvider, RecordedAddressProvider
from agents.legal_agent.verdict import compute_verdict
from agents.legal_agent.workflow import LegalResearchWorkflow


def argument_parser():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('address')
    parser.add_argument('--borough')
    parser.add_argument('--unit')
    parser.add_argument('--goals',nargs='*',default=[])
    parser.add_argument('--provider',choices=['zetaris','nyc-development-fallback','replay'],default='zetaris')
    parser.add_argument('--replay',type=Path)
    parser.add_argument('--reasoning',choices=['nvidia','nightshift','deterministic','model','configured'],
                        help='Explicit provider or deterministic mode; replay defaults to deterministic')
    parser.add_argument('--memory-dir',type=Path,help='Persistent legal-local H-MEM; also reads LEGAL_MEMORY_DIR')
    parser.add_argument('--trace-jsonl',type=Path,help='Optional additional sink; run-directory trace.jsonl is always saved')
    parser.add_argument('--page-size',type=int,default=100)
    parser.add_argument('--max-pages',type=int,default=2)
    parser.add_argument('--max-requests',type=int,default=40)
    parser.add_argument('--deadline-seconds',type=float)
    parser.add_argument('--max-tool-calls',type=int)
    parser.add_argument('--max-model-calls',type=int)
    parser.add_argument('--max-revisions',type=int)
    parser.add_argument('--model-timeout',type=float)
    parser.add_argument('--output','--output-root',dest='output',type=Path,default=ROOT/'reports'/'investigations',
                        help='Parent directory; every run creates a new timestamp/UUID child')
    return parser


def _provider(args,budget):
    options=dict(page_size=args.page_size,max_pages=args.max_pages,max_requests=args.max_requests,budget=budget)
    if args.provider=='zetaris':
        from scripts.zetaris_api import zetaris_request
        return DynamicZetarisProvider(zetaris_request,engine_id=os.environ.get('ZETARIS_ENGINE_ID'),**options)
    if args.provider=='replay':
        if not args.replay:raise ValueError('Replay requires a saved investigation_report.json')
        return RecordedAddressProvider(json.loads(args.replay.read_text()))
    return DynamicNYCDevelopmentProvider(**options)


def _failure_report(args,run_id,provider,error):
    stopped=isinstance(error,ExecutionStopped)
    message=str(error) if stopped else 'Investigation interrupted.' if isinstance(error,KeyboardInterrupt) else 'Investigation could not finish; see trace.jsonl for the failed stage and error type.'
    code='execution_stopped' if stopped else 'run_error'
    return {'schema_version':'2.0','report_type':'tenant_risk_investigation','run_id':run_id,
        'generated_at':datetime.now(UTC).isoformat(),'request':{'original_input':args.address,'borough':args.borough,'unit':args.unit},
        'provider':getattr(provider,'name',args.provider),'data_mode':getattr(provider,'data_mode','recorded_replay' if args.provider=='replay' else 'live' if args.provider=='zetaris' else 'development_fallback'),
        'identity':{'canonical_address':args.address,'verification_status':'missing','identifiers':{},'ambiguities':['No complete trusted identity was available at termination.']},
        'retrieval_status':'budget_exhausted' if stopped else 'failed','coverage':[],'categories':list(RISK_CATEGORIES),
        'factual_findings':[],'patterns':[],'legal_assessment':{'status':'inconclusive' if stopped else 'error','errors':[{'code':code,'message':message}]},
        'identity_source_records':[],'evidence_audit':[],'record_decisions':[],'root_critic_history':[],
        'activity_log':[{'action':'hard_stop','code':code}],'retrievals':[],
        'board_update':{'task_id':'address-'+run_id,'status':'inconclusive' if stopped else 'error',
                        'legal_findings':[],'record_decisions':[],'follow_up_requests':['Resolve the failed stage before relying on this investigation.'],'summary_is_evidence':False},
        'limitations':[message,'No safety or liability conclusion can be drawn from an incomplete investigation.']}


def run_investigation(args,*,provider_factory=None,workflow=None,load_configuration=True):
    """CLI lifecycle/artifacts only. Agent orchestration stays in investigate_address."""
    started=time.monotonic();run_id=str(uuid4())
    directory=args.output.resolve()/(datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')+'_'+run_id)
    directory.mkdir(parents=True,exist_ok=False,mode=0o700)
    trace=ActivityTrace(JSONLEventSink(directory/'trace.jsonl'),run_id=run_id,task_id='address-'+run_id)
    trace.emit('run.started',requested_provider=args.provider,mode=args.reasoning or ('deterministic' if args.provider=='replay' else 'model'))
    provider=None;budget=None;report=None;stage='configuration'
    try:
        requested=args.reasoning or ('deterministic' if args.provider=='replay' else 'model')
        # Replay needs no credential files, network configuration or provider imports.
        if load_configuration and not (args.provider=='replay' and requested=='deterministic'):
            from scripts.zetaris_sql import load_env
            load_env()
        if args.trace_jsonl and args.trace_jsonl.resolve()!=(directory/'trace.jsonl'):
            primary=trace.sink;extra=JSONLEventSink(args.trace_jsonl.resolve())
            class Both:
                def append(self,event):primary.append(event);extra.append(event)
            trace.sink=Both()
        values={k:getattr(args,arg) for k,arg in {
            'investigation_timeout_seconds':'deadline_seconds','max_total_tool_calls':'max_tool_calls',
            'max_model_calls':'max_model_calls','max_revision_cycles':'max_revisions','model_timeout_seconds':'model_timeout'}.items()
            if getattr(args,arg) is not None}
        limits=ExecutionLimits.model_validate({**ExecutionLimits.from_env().model_dump(),**values})
        budget=ExecutionBudget(limits,trace=trace)
        trace.emit('run.configured',limits=limits.model_dump(),memory_enabled=bool(args.memory_dir or os.getenv('LEGAL_MEMORY_DIR')),
                   mode=requested,live_credentials_required=args.provider!='replay' or requested!='deterministic')
        stage='provider_setup'
        provider=(provider_factory or _provider)(args,budget)
        provider.budget=budget
        mode='demo_deterministic' if requested=='deterministic' else 'llm:'+requested if requested in {'nvidia','nightshift'} else 'llm:configured' if requested=='model' else None
        if workflow is None:
            memory=None;memory_dir=args.memory_dir or os.getenv('LEGAL_MEMORY_DIR')
            if memory_dir:
                from agents.legal_agent.memory import LegalMemory
                memory=LegalMemory(memory_dir)
            workflow=LegalResearchWorkflow(reasoning_mode=mode,limits=limits,memory=memory,
                model_provider=requested if requested in {'nvidia','nightshift'} else None)
        stage='investigation'
        report=investigate_address(provider,args.address,borough=args.borough,unit=args.unit,goals=args.goals,
                                   workflow=workflow,budget=budget,reasoning_mode=mode)
    except (Exception,KeyboardInterrupt) as error:
        trace.emit('run.error',stage=stage,error_type=type(error).__name__,stop_reason=str(error) if isinstance(error,ExecutionStopped) else 'Stage failed; private exception details withheld')
        report=_failure_report(args,run_id,provider,error)
    finally:
        if provider is not None:
            try:provider.close()
            except Exception as error:
                trace.emit('cleanup.failed',error_type=type(error).__name__)
                if report:report.setdefault('limitations',[]).append('Provider cleanup failed; inspect the trace before another live run.')
    # Deterministic verdict from accepted records and coverage; no model involved.
    investigation_day=str(report.get('generated_at') or datetime.now(UTC).isoformat())[:10]
    report['verdict']=compute_verdict(report,investigation_day,(report.get('request') or {}).get('unit'))
    for rule in report['verdict']['rules_fired']:
        trace.emit('verdict.rule_fired',rule_id=rule['rule_id'],level=rule['level'],evidence_ids=rule['evidence_ids'])
    trace.emit('verdict.decided',verdict=report['verdict']['verdict'],rule_ids=[r['rule_id'] for r in report['verdict']['rules_fired']])
    from agents.legal_agent.integration import SharedInvestigationState
    shared=SharedInvestigationState(trace)
    board={**report['board_update'],'source_coverage':report.get('coverage',[])}
    try:
        shared.update(board['task_id'],actor='legal',expected_version=0,board=board,status=report['legal_assessment'].get('status','inconclusive'))
        report['shared_context']=shared.read(board['task_id']).model_dump(mode='json')
    except ValueError:
        trace.emit('shared_state.rejected',reason='invalid_board_projection')
    legal=report['legal_assessment'];errors=list(legal.get('errors',[]))
    exhausted=[e for e in trace.events if e['type']=='budget.exhausted']
    if exhausted and not any(e.get('code')=='execution_stopped' for e in errors):
        stopped={'code':'execution_stopped','message':'Aggregate '+exhausted[-1]['data'].get('resource','execution')+' budget exhausted'}
        errors.insert(0,stopped)
        legal.setdefault('errors',[]).append(stopped)
        report['limitations'].append(stopped['message'])
    for source in report['coverage']:
        if source['status'] in {'unavailable','budget_exhausted'}:
            errors.append({'code':'source_unavailable','source':source['source'],'message':source.get('reason') or source['status']})
    status=legal.get('status','inconclusive')
    if status not in {'completed','error','inconclusive'}:status='inconclusive'
    if legal.get('critic_outcome')=='BLOCKED':reason='critic_blocked'
    elif errors:reason=errors[0].get('message') or errors[0]['code']
    elif report['identity']['verification_status'] not in {'verified','sample'}:reason='identity_unresolved'
    else:reason='legal_'+status
    execution=budget.snapshot() if budget else {'run_id':run_id,'tool_calls':0,'model_calls':0,'elapsed_seconds':time.monotonic()-started}
    models=[e['data'] for e in trace.events if e['type'] in {'model.started','model.completed','model.failed'}]
    files={name:str(directory/name) for name in ['investigation_report.md','investigation_report.json','renter_report.md','trace.jsonl','run_summary.json']}
    summary=sanitize({'schema_version':'legal.run.v1','run_id':run_id,'task_id':trace.task_id,'status':status,
        'exit_code':0 if status=='completed' else 1 if status=='error' else 2,'termination_reason':reason,
        'provider':report['provider'],'data_mode':report['data_mode'],'mode':requested,'citation_metrics':legal.get('citation_metrics',{}),
        'identity_status':report['identity']['verification_status'],'execution':execution,
        'total_duration_seconds':time.monotonic()-started,'model_activity':models,
        'source_coverage':[{k:v for k,v in item.items() if k in {'source','title','source_url','status','complete_for_filter','records_returned','reason'}} for item in report['coverage']],'errors':errors,'files':files})
    report['run_id']=run_id;report['execution']=execution
    report['run_summary_ref']='run_summary.json'
    report['activity_events']=trace.events
    try:
        write_risk_report(report,directory)
    except Exception as error:
        # Keep a structurally valid diagnostic report even if normal rendering fails.
        trace.emit('report.write_failed',error_type=type(error).__name__)
        report['activity_events']=trace.events
        (directory/'investigation_report.json').write_text(json.dumps(report,indent=2,default=str)+'\n')
        (directory/'investigation_report.md').write_text('# Investigation report\n\nThe investigation ended with '+status+'.\n\nNormal rendering failed. Inspect investigation_report.json, trace.jsonl and run_summary.json.\n')
        summary['rendering_error']='normal_report_render_failed'
        summary['errors'].append({'code':'report_render_failed','message':'Normal report rendering failed; diagnostic reports were saved.'})
        summary.update(status='error',exit_code=1,termination_reason='report_render_failed')
    write_renter_report(report,directory)
    trace.emit('report.renter_generated',factual_findings=len(report.get('factual_findings',[])),factual_only=status!='completed' or not report.get('board_update',{}).get('legal_findings'))
    trace.emit('artifacts.report_written',diagnostic_fallback=bool(summary.get('rendering_error')))
    summary['total_duration_seconds']=time.monotonic()-started
    trace.emit('run.finished',status=summary['status'],termination_reason=summary['termination_reason'],errors=summary['errors'],duration_seconds=summary['total_duration_seconds'])
    report['activity_events']=trace.events
    (directory/'investigation_report.json').write_text(json.dumps(report,indent=2,default=str)+'\n')
    (directory/'run_summary.json').write_text(json.dumps(summary,indent=2,default=str)+'\n')
    for name in files:os.chmod(directory/name,0o600)
    return summary,directory


def main(argv=None):
    args=argument_parser().parse_args(argv)
    summary,directory=run_investigation(args)
    print(f'Run: {summary["run_id"]}; status: {summary["status"]}; provider: {summary["provider"]}; data: {summary["data_mode"]}')
    print(f'Termination: {summary["termination_reason"]}')
    for name,path in summary['files'].items():print(f'{name}: {path}')
    return summary['exit_code']


if __name__=='__main__':
    raise SystemExit(main())
