"""Phase-one runtime regressions. No real services or credentials are used."""
import json
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import Mock

import pytest
from agents.researcher import research
from integration import merge_critic_reports
from main import create_app,sample_task
from models.schemas import CriticReport,InvestigationContext,LegalIssueTask
from tools.execution import ExecutionBudget,ExecutionLimits,ExecutionStopped
from tools.address_data import DynamicZetarisProvider
from tools.source_registry import load_registry
from tools.risk_mapping import normalize_agency_status
from reconciliation import reconcile_evidence
from workflow import LegalResearchWorkflow


@pytest.mark.parametrize('other',['PASS','REVISE','INCONCLUSIVE'])
def test_blocked_review_cannot_be_downgraded(other):
    blocked=CriticReport(task_id='t',outcome='BLOCKED')
    assert merge_critic_reports(blocked,CriticReport(task_id='t',outcome=other)).outcome.value=='BLOCKED'


def test_actual_workflow_preserves_blocked_and_does_not_retry(heat_task,heat_context):
    def invalid(*args,**kwargs):
        draft=research(*args,**kwargs)
        draft.findings[0].legal_conclusions[0].source_ids=['unretrieved']
        return draft
    critic=Mock(return_value=CriticReport(task_id=heat_task.task_id,outcome='BLOCKED'))
    result=LegalResearchWorkflow(researcher=invalid,critic=critic).run(heat_task,heat_context)
    assert result.critic_outcome.value=='BLOCKED'
    assert critic.call_count==1 and result.revision_cycles==0
    assert {r.outcome.value for r in result.review_history} >= {'BLOCKED','REVISE'}


def test_trusted_upstream_veto_stops_all_research(heat_task,heat_context):
    heat_context.root_critic_outcome='BLOCKED'
    planner=Mock(side_effect=AssertionError('should not run'))
    result=LegalResearchWorkflow(planner=planner).run(heat_task,heat_context)
    assert result.critic_outcome.value=='BLOCKED'
    assert not result.findings and result.tool_calls==0
    planner.assert_not_called()


def test_inconclusive_does_not_repeat_ineffective_research(heat_task,heat_context):
    critic=Mock(return_value=CriticReport(task_id=heat_task.task_id,outcome='INCONCLUSIVE'))
    result=LegalResearchWorkflow(critic=critic).run(heat_task,heat_context)
    assert result.status.value=='inconclusive' and result.revision_cycles==0
    assert critic.call_count==1


def test_aggregate_tool_budget_includes_prior_data_calls(heat_task,heat_context):
    budget=ExecutionBudget(ExecutionLimits(max_total_tool_calls=1))
    budget.consume('tool','prior_zetaris_query')
    result=LegalResearchWorkflow().run(heat_task,heat_context,budget=budget)
    assert result.status.value=='inconclusive'
    assert result.errors[0].code=='execution_stopped'
    assert budget.tool_calls==1


def test_aggregate_model_attempt_limit_and_deadline():
    now=[0.]
    budget=ExecutionBudget(ExecutionLimits(max_model_calls=1,investigation_timeout_seconds=1),clock=lambda:now[0])
    budget.consume('model','one')
    with pytest.raises(ExecutionStopped):budget.consume('model','two')
    now[0]=2
    with pytest.raises(ExecutionStopped):budget.check()


def test_http_clients_cannot_override_trusted_context():
    client=create_app().test_client();task,context=sample_task()
    for field,value in [('identity',{}),('identity_candidates',[]),('record_matches',[]),('reconciliation',{}),('root_critic_outcome','PASS'),('data_mode','live')]:
        response=client.post('/investigate',json={'task':task,'context':{**context,field:value}})
        assert response.status_code==400
    assert client.post('/resolve-identity',json={'address':'1 Mock St','context':{'candidates':[]}}).status_code==400


def test_server_snapshot_retains_upstream_veto():
    task,context=sample_task();context['root_critic_outcome']='BLOCKED'
    client=create_app(snapshot_loader=lambda _:context).test_client()
    response=client.post('/investigate',json={'task':task})
    assert response.status_code==200 and response.json['critic_outcome']=='BLOCKED'
    assert client.post('/investigate',json={'task':task,'context':{'root_critic_outcome':'PASS'}}).status_code==400


def test_package_imports_do_not_depend_on_cli_path_hacks():
    root=Path(__file__).resolve().parents[3]
    code='from agents.legal_agent import LegalResearchWorkflow; from agents.legal_agent.address_investigation import investigate_address; import agents; assert not hasattr(agents,"critique_draft"); print("ok")'
    result=subprocess.run([sys.executable,'-B','-c',code],cwd=root,capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_status_normalization_preserves_certification_uncertainty(heat_context):
    assert normalize_agency_status('INVALID CERTIFICATION',raw={'violationstatus':'Open'})=='open'
    assert normalize_agency_status('NOV CERTIFIED')=='unknown'
    assert normalize_agency_status('CLOSED')=='closed'
    left,right=heat_context.evidence[:2]
    left.status='VIOLATION OPEN';right.status='CLOSED'
    left.metadata['issue']=right.metadata['issue']='heat'
    from models.identity import RecordMatch
    matches=[RecordMatch(evidence_id=e.evidence_id,decision='accepted',method='fixture',scope='building',confidence=.9,reason='fixture') for e in (left,right)]
    result=reconcile_evidence([left,right],matches)
    assert result.conflicts
    assert left.status=='VIOLATION OPEN' and right.status=='CLOSED'


def test_unapproved_sql_is_stopped_before_transport():
    request=Mock();provider=DynamicZetarisProvider(request)
    with pytest.raises(ValueError):provider._query('DROP TABLE teammate.records',1)
    request.assert_not_called()


def test_late_source_creation_gets_bounded_owned_cleanup():
    calls=[]
    def transport(path,method,body):
        calls.append(body['sql'])
        if body['sql']=='SHOW LIGHTNING DATABASES':return {'headers':['name'],'data':[]}
        if body['sql'].startswith('CREATE LIGHTNING DATABASE'):time.sleep(.04)
        return {}
    provider=DynamicZetarisProvider(transport,budget=ExecutionBudget(ExecutionLimits(investigation_timeout_seconds=.01)))
    result=provider.fetch_where(load_registry()['hpd_violations'],'1=1')
    provider.close();time.sleep(.08)
    drops=[sql for sql in calls if sql.startswith('DROP')]
    assert result.status=='unavailable'
    assert 1<=len(drops)<=2
    assert all(sql=='DROP LIGHTNING DATABASE '+provider.namespace for sql in drops)


def test_terminal_inconclusive_cannot_be_reopened_by_local_revision():
    final=merge_critic_reports(CriticReport(task_id='t',outcome='INCONCLUSIVE'),
                              CriticReport(task_id='t',outcome='REVISE',revision_instructions=['Try again']))
    assert final.outcome.value=='INCONCLUSIVE'
    assert final.revision_instructions==['Try again']


def test_inconclusive_review_never_publishes_legal_drafts(heat_task,heat_context):
    from integration import board_update
    from models.schemas import CriticOutcome,InvestigationStatus
    result=LegalResearchWorkflow(reasoning_mode='demo_deterministic').run(heat_task,heat_context)
    assert result.findings
    result.critic_outcome=CriticOutcome.INCONCLUSIVE
    result.status=InvestigationStatus.INCONCLUSIVE
    update=board_update(result,heat_context.evidence)
    assert not update['legal_findings']
    assert update['withheld_finding_ids']
