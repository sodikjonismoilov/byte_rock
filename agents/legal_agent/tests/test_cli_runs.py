"""Exercise the root CLI in fresh processes, independent of legacy test imports."""
import json
from pathlib import Path
import subprocess
import sys
import pytest

ROOT=Path(__file__).resolve().parents[3]
COMMON='''
import json,os
from pathlib import Path
from urllib.parse import parse_qs,urlparse
from scripts import investigate_address as cli
from agents.legal_agent.tools.address_data import AddressDataProvider
from agents.legal_agent.workflow import LegalResearchWorkflow
from agents.legal_agent.models.schemas import ResearchPlan,ResearchDraft,CriticReport
class FixtureProvider(AddressDataProvider):
    name='mock';data_mode='mock'
    def __init__(self,budget):super().__init__(budget=budget);self.closed=False
    def _page(self,source,url):
        if source['key']=='hpd_buildings':return [dict(buildingid='123',bin='1000001',boroid='1',boro='MANHATTAN',block='5',lot='1',housenumber='1',lowhousenumber='1',highhousenumber='1',streetname='MOCK STREET',zip='10001',recordstatus='Active')]
        if source['key']=='hpd_violations':return [dict(buildingid='123',bin='1000001',bbl='1000050001',housenumber='1',streetname='MOCK STREET',violationid='v1',inspectiondate='2026-01-01',currentstatus='OPEN',novdescription='Fixture maintenance observation',apartment='',**{'class':'B'})]
        return []
    def close(self):self.closed=True
factory=lambda args,budget:FixtureProvider(budget)
def arguments(folder,extra=()):return cli.argument_parser().parse_args(['1 Mock Street','--borough','Manhattan','--goals','habitability','--output',str(folder),*extra])
def verify(directory):
    expected={'investigation_report.md','investigation_report.json','trace.jsonl','run_summary.json'}
    assert expected<=set(p.name for p in directory.iterdir())
    events=[json.loads(line) for line in (directory/'trace.jsonl').read_text().splitlines()]
    summary=json.loads((directory/'run_summary.json').read_text())
    assert events[0]['type']=='run.started'
    assert events[-1]['type']=='run.finished'
    assert {e['run_id'] for e in events}=={summary['run_id']}
    assert {e['task_id'] for e in events}=={summary['task_id']}
    return events,summary,json.loads((directory/'investigation_report.json').read_text())
'''


def run_child(code,tmp_path):
    process=subprocess.run([sys.executable,'-B','-c',COMMON+'\nfolder=Path('+repr(str(tmp_path))+')\n'+code],
                           cwd=ROOT,capture_output=True,text=True,timeout=30)
    assert process.returncode==0,process.stdout+process.stderr


def test_mocked_model_mode_full_pipeline_and_recorded_requests(tmp_path):
    run_child('''
from agents.legal_agent.tools.llm import JSONModelAdapter
from agents.legal_agent.tools.execution import ExecutionLimits
os.environ.update(LLM_PROVIDER='nvidia',NVIDIA_MODEL='fixture-model',NVIDIA_API_KEY='private-sentinel-key')
roles=[]
def transport(body):
    payload=json.loads(body['messages'][-1]['content']);role=payload['role'];roles.append(role)
    if role=='planner':value=ResearchPlan(task_id=payload['task_id'],objective='Fixture integration',questions=[{'question_id':'q1','prompt':'Check maintenance requirements','recommended_tool':'legal_search'}])
    elif role=='researcher':value=ResearchDraft(task_id=payload['task_id'],plan_revision=0,findings=[],caveats=['Fixture response'])
    else:value=CriticReport(task_id=payload['task_id'],outcome='INCONCLUSIVE')
    return {'model':'fixture-model','choices':[{'message':{'content':value.model_dump_json()}}]}
workflow=LegalResearchWorkflow(model_adapter=JSONModelAdapter(ExecutionLimits(),transport),max_revision_cycles=0)
summary,directory=cli.run_investigation(arguments(folder,['--reasoning','nvidia','--unit','4B']),provider_factory=factory,workflow=workflow,load_configuration=False)
events,summary,report=verify(directory)
assert roles==['planner','researcher','independent_critic']
assert summary['status']=='inconclusive' and not summary['errors']
assert summary['execution']['model_calls']==3
assert report['request']['unit']=='4B'
assert {e['data']['schema'] for e in events if e['type']=='model.completed'}=={'ResearchPlan','ResearchDraft','CriticReport'}
assert any(e['type']=='root_critic.decision' for e in events)
assert any(e['type']=='context.built' for e in events)
assert all('private-sentinel-key' not in p.read_text() for p in directory.iterdir())
''',tmp_path)


def test_revisions_and_all_review_decisions_retained(tmp_path):
    run_child('''
calls=[]
def critic(task,*args,**kwargs):
    calls.append(task.task_id)
    return CriticReport(task_id=task.task_id,outcome='REVISE' if len(calls)==1 else 'INCONCLUSIVE',revision_instructions=['Review another authority'])
def incomplete(task,context,plan,**kwargs):return ResearchDraft(task_id=task.task_id,plan_revision=plan.revision,findings=[])
workflow=LegalResearchWorkflow(reasoning_mode='demo_deterministic',critic=critic,researcher=incomplete,max_revision_cycles=1)
summary,directory=cli.run_investigation(arguments(folder,['--reasoning','deterministic']),provider_factory=factory,workflow=workflow,load_configuration=False)
events,summary,report=verify(directory)
assert any(e['type']=='plan.revised' for e in events)
assert len(report['legal_assessment']['review_history'])==6
assert len([e for e in events if e['type']=='critic.decision'])==6
assert report['root_critic_history']
''',tmp_path)


def test_hmem_events_and_unique_consecutive_output_directories(tmp_path):
    run_child('''
from agents.legal_agent.memory import LegalMemory
paths=[]
for _ in range(2):
    workflow=LegalResearchWorkflow(reasoning_mode='demo_deterministic',memory=LegalMemory(folder/'memory',allow_sample=True))
    summary,directory=cli.run_investigation(arguments(folder/'runs',['--reasoning','deterministic']),provider_factory=factory,workflow=workflow,load_configuration=False)
    events,summary,report=verify(directory);paths.append(directory)
    assert any(e['type']=='memory.retrieved' for e in events)
    assert any(e['type']=='memory.stored' for e in events)
assert paths[0]!=paths[1] and paths[0].exists()
assert any(e['type']=='memory.retrieved' and e['data']['count']>0 for e in events)
''',tmp_path)


def test_hard_stop_emits_reports_and_reason(tmp_path):
    run_child('''
summary,directory=cli.run_investigation(arguments(folder,['--reasoning','deterministic','--max-tool-calls','0']),provider_factory=factory,load_configuration=False)
events,summary,report=verify(directory)
assert summary['status']=='inconclusive'
assert 'budget exhausted' in summary['termination_reason']
assert any(e['type']=='budget.exhausted' for e in events)
assert report['legal_assessment']['errors']
''',tmp_path)


def test_provider_failure_still_emits_four_useful_files_without_secret(tmp_path):
    run_child('''
os.environ['NVIDIA_API_KEY']='provider-secret-sentinel'
def failed(args,budget):raise RuntimeError('provider-secret-sentinel')
summary,directory=cli.run_investigation(arguments(folder,['--reasoning','nvidia']),provider_factory=failed,load_configuration=False)
events,summary,report=verify(directory)
assert summary['status']=='error' and summary['exit_code']==1
assert any(e['type']=='run.error' and e['data']['stage']=='provider_setup' for e in events)
assert report['legal_assessment']['errors']
assert all('provider-secret-sentinel' not in p.read_text() for p in directory.iterdir())
''',tmp_path)


def test_explicit_nvidia_never_falls_back_to_demo_on_bad_model_config(tmp_path):
    run_child('''
for key in list(os.environ):
    if key.startswith(('LLM_','NVIDIA_','NIGHTSHIFT_')):os.environ.pop(key)
summary,directory=cli.run_investigation(arguments(folder,['--reasoning','nvidia']),provider_factory=factory,load_configuration=False)
events,summary,report=verify(directory)
assert report['legal_assessment']['reasoning_mode']=='llm:nvidia'
assert report['legal_assessment']['status']=='inconclusive'
assert not any(e['type']=='plan.selected' for e in events)
assert report['legal_assessment']['errors']
''',tmp_path)


def test_offline_replay_needs_no_configuration_and_preserves_report_contract(tmp_path):
    process=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/investigate_address.py'),'1 Mock Street','--borough','Manhattan',
        '--provider','replay','--replay',str(ROOT/'agents/legal_agent/tests/fixtures/address_replay.synthetic.json'),
        '--reasoning','deterministic','--output',str(tmp_path)],cwd=ROOT,capture_output=True,text=True,timeout=30)
    assert process.returncode==2,process.stdout+process.stderr
    directories=list(tmp_path.iterdir());assert len(directories)==1
    summary=json.loads((directories[0]/'run_summary.json').read_text())
    report=json.loads((directories[0]/'investigation_report.json').read_text())
    assert summary['data_mode']=='recorded_replay' and summary['execution']['model_calls']==0
    assert report['schema_version']=='2.0' and report['board_update']['summary_is_evidence'] is False


def test_renderer_failure_still_has_diagnostic_report_and_terminal_trace(tmp_path):
    run_child('''
def broken_renderer(*args,**kwargs):raise RuntimeError('private renderer detail')
cli.write_risk_report=broken_renderer
summary,directory=cli.run_investigation(arguments(folder,['--reasoning','deterministic']),provider_factory=factory,load_configuration=False)
events,summary,report=verify(directory)
assert summary['status']=='error' and summary['termination_reason']=='report_render_failed'
assert any(e['type']=='report.write_failed' for e in events)
assert 'Normal rendering failed' in (directory/'investigation_report.md').read_text()
assert all('private renderer detail' not in p.read_text() for p in directory.iterdir())
''',tmp_path)


def test_root_rechecks_retain_first_and_later_decisions(tmp_path):
    run_child('''
class CorrectionProvider(FixtureProvider):
    def _page(self,source,url):
        rows=super()._page(source,url)
        if source['key']=='hpd_violations' and rows:
            query=parse_qs(urlparse(url).query).get('$where',[''])[0]
            if ' AND ' in query:rows[0]['violationid']='v2'
            else:rows[0]['bbl']='1000050002'
        return rows
summary,directory=cli.run_investigation(arguments(folder,['--reasoning','deterministic']),provider_factory=lambda args,budget:CorrectionProvider(budget),load_configuration=False)
events,summary,report=verify(directory)
assert len(report['root_critic_history'])==2
first=report['root_critic_history'][0]['decisions']
assert first[0]['decision']=='reject' and first[0]['rule']=='R1'
assert len(report['root_critic_history'][1]['decisions'])==2
attribution=[e for e in events if e['type']=='root_critic.decision' and e['data']['phase']=='record_attribution']
assert len(attribution)==3
''',tmp_path)


def test_double_truncation_still_emits_factual_only_renter_report(tmp_path):
    run_child('''
from agents.legal_agent.tools.llm import JSONModelAdapter
from agents.legal_agent.tools.execution import ExecutionLimits
os.environ.update(LLM_PROVIDER='nvidia',NVIDIA_MODEL='fixture-model',NVIDIA_API_KEY='private-sentinel-key',LEGAL_CONTEXT_MAX_BYTES='60000',LEGAL_CONTEXT_MAX_TOKENS='60000',LEGAL_MODEL_MAX_TOKENS='100000')
roles=[]
def transport(body):
    payload=json.loads(body['messages'][-1]['content']);role=payload['role'];roles.append(role)
    if role=='planner':
        value=ResearchPlan(task_id=payload['task_id'],objective='Fixture integration',questions=[{'question_id':'q1','prompt':'maintenance authority','recommended_tool':'legal_search'}])
        return {'choices':[{'finish_reason':'stop','message':{'content':value.model_dump_json()}}]}
    return {'choices':[{'finish_reason':'length','message':{'content':'{"findings":['}}]}
workflow=LegalResearchWorkflow(model_adapter=JSONModelAdapter(ExecutionLimits(),transport))
summary,directory=cli.run_investigation(arguments(folder,['--reasoning','nvidia']),provider_factory=factory,workflow=workflow,load_configuration=False)
events,summary,report=verify(directory)
assert roles==['planner','researcher','researcher']
assert report['factual_findings'] and not report['board_update']['legal_findings']
text=(directory/'renter_report.md').read_text()
assert 'PARTIAL — FACTUAL-ONLY' in text and 'Fixture maintenance observation' in text
assert 'private-sentinel-key' not in text
assert summary['status']=='inconclusive' and 'truncated' in summary['termination_reason']
assert len([e for e in events if e['type']=='research.truncation_retry'])==1
assert report['shared_context']['schema_version']=='signsafe.investigation_context.v1'
assert any(e['type']=='shared_state.updated' for e in events)
''',tmp_path)


def test_all_invalid_observations_keep_root_facts_and_factual_report(tmp_path):
    run_child('''
from agents.legal_agent.tools.llm import JSONModelAdapter
from agents.legal_agent.tools.execution import ExecutionLimits
os.environ.update(LLM_PROVIDER='nvidia',NVIDIA_MODEL='fixture-model',NVIDIA_API_KEY='private-sentinel-key',LEGAL_CONTEXT_MAX_BYTES='60000',LEGAL_CONTEXT_MAX_TOKENS='60000',LEGAL_MODEL_MAX_TOKENS='100000')
roles=[]
def transport(body):
    payload=json.loads(body['messages'][-1]['content']);role=payload['role'];roles.append(role)
    if role=='planner':
        content=ResearchPlan(task_id=payload['task_id'],objective='Fixture',questions=[{'question_id':'q1','prompt':'maintenance authority','recommended_tool':'legal_search'}]).model_dump_json()
    else:
        content=json.dumps({'task_id':payload['task_id'],'findings':[{'finding_id':'bad','issue':'maintenance','summary':'Must be rejected',
            'legal_conclusions':[{'claim_scope':'current_guidance','citations':[{'authority_id':'not-retrieved','supporting_quote':'This invented source must never be accepted as legal authority.'}]}]}]})
    return {'choices':[{'finish_reason':'stop','message':{'content':content}}]}
workflow=LegalResearchWorkflow(model_adapter=JSONModelAdapter(ExecutionLimits(),transport))
summary,directory=cli.run_investigation(arguments(folder,['--reasoning','nvidia']),provider_factory=factory,workflow=workflow,load_configuration=False)
events,summary,report=verify(directory)
assert roles==['planner','researcher']
assert report['factual_findings'] and not report['board_update']['legal_findings']
assert 'PARTIAL — FACTUAL-ONLY' in (directory/'renter_report.md').read_text()
assert 'Fixture maintenance observation' in (directory/'renter_report.md').read_text()
assert summary['status']=='inconclusive' and 'Legal review unavailable' in summary['termination_reason']
assert any(e['type']=='legal.review_unavailable' for e in events)
assert any(e['type']=='research.observation_rejected' for e in events)
assert not any(e['type']=='agent.started' and e['data'].get('role')=='local_critic' for e in events)
''',tmp_path)
