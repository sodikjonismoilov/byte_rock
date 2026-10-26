import json
from concurrent.futures import ThreadPoolExecutor
import pytest
from models.schemas import ResearchPlan,ResearchDraft,CriticReport
from tools.execution import ExecutionLimits,ExecutionBudget,ExecutionStopped
from tools.llm import JSONModelAdapter,ModelTruncated,request_size,request_budget
from workflow import LegalResearchWorkflow
from events import ActivityTrace,JSONLEventSink
from integration import SharedInvestigationState,board_update


def configured(monkeypatch):
    monkeypatch.setenv('LLM_PROVIDER','nvidia')
    monkeypatch.setenv('NVIDIA_MODEL','fixture-model')
    monkeypatch.setenv('NVIDIA_API_KEY','private-reliability-sentinel')
    monkeypatch.setenv('LEGAL_CONTEXT_MAX_BYTES','60000')
    monkeypatch.setenv('LEGAL_CONTEXT_MAX_TOKENS','60000')
    monkeypatch.setenv('LEGAL_MODEL_MAX_TOKENS','100000')


def model_transport(task,*,truncations=0,invalid=False):
    calls=[];research_calls=0
    def transport(body):
        nonlocal research_calls
        payload=json.loads(body['messages'][-1]['content']);calls.append((body,payload))
        if payload['role']=='planner':
            content=ResearchPlan(task_id=task.task_id,objective='Heat duty',questions=[{'question_id':'law','prompt':'heat hot water','recommended_tool':'legal_search'}]).model_dump_json()
        elif payload['role']=='researcher':
            research_calls+=1
            if research_calls<=truncations:return {'choices':[{'finish_reason':'length','message':{'content':'{"findings":['}}]}
            if invalid:return {'choices':[{'finish_reason':'stop','message':{'content':'{"findings":['}}]}
            source=next(a for a in payload['authorities'] if a['id']=='hpd-heat-hot-water')
            content=json.dumps({'task_id':task.task_id,'findings':[{'finding_id':'f1','issue':'heat','summary':'Official heat guidance; current property conditions remain unverified.',
                'evidence_ids':['EV-HEAT-HPD-002'],'legal_conclusions':[{'claim_scope':'current_guidance','citations':[{'authority_id':source['id'],'supporting_quote':source['excerpt']}]}]}]})
        else:content=CriticReport(task_id=task.task_id,outcome='INCONCLUSIVE',reasoning_mode='live_fixture').model_dump_json()
        return {'choices':[{'finish_reason':'stop','message':{'content':content}}]}
    return transport,calls


def test_truncation_retries_once_smaller_then_runs_critic_and_preserves_citations(monkeypatch,heat_task,heat_context):
    configured(monkeypatch);transport,calls=model_transport(heat_task,truncations=1)
    adapter=JSONModelAdapter(ExecutionLimits(),transport)
    result=LegalResearchWorkflow(model_adapter=adapter,max_revision_cycles=0).run(heat_task,heat_context)
    research=[p for _,p in calls if p['role']=='researcher']
    assert len(research)==2 and research[-1]['observation_limit']==1
    assert len(calls)==4 and calls[-1][1]['role']=='independent_critic'
    claim=result.findings[0].legal_conclusions[0]
    assert claim.citations[0]['authority_id']=='hpd-heat-hot-water'
    assert claim.identifiers and claim.supported
    assert result.review_history and result.execution['model_calls']==4
    assert sum(e['type']=='research.truncation_retry' for e in result.activity_events)==1
    for body,payload in calls:
        assert len(json.dumps(body).encode())+256<=60000
        assert request_size({'planner':ResearchPlan,'researcher':ResearchDraft,'independent_critic':CriticReport}[payload['role']],payload,'fixture-model')<=request_budget()
    assert all(e['data']['request_bytes']<=e['data']['request_budget'] for e in result.activity_events if e['type']=='context.request_built')
    assert 'private-reliability-sentinel' not in json.dumps(result.activity_events)


def test_repeated_truncation_stops_after_single_retry(monkeypatch,heat_task,heat_context):
    configured(monkeypatch);transport,calls=model_transport(heat_task,truncations=10)
    result=LegalResearchWorkflow(model_adapter=JSONModelAdapter(ExecutionLimits(),transport)).run(heat_task,heat_context)
    assert [p['role'] for _,p in calls]==['planner','researcher','researcher']
    assert result.status.value=='inconclusive' and not result.review_history
    assert 'truncated' in result.errors[0].message and not result.findings
    assert result.execution['model_calls']==3


def test_invalid_nontruncated_json_is_not_retried_or_repaired(monkeypatch,heat_task,heat_context):
    configured(monkeypatch);transport,calls=model_transport(heat_task,invalid=True)
    result=LegalResearchWorkflow(model_adapter=JSONModelAdapter(ExecutionLimits(),transport)).run(heat_task,heat_context)
    assert len(calls)==2 and not result.findings
    assert 'invalid structured' in result.errors[0].message


def test_finish_reason_length_rejected_even_when_json_valid(monkeypatch):
    configured(monkeypatch)
    transport=lambda body:{'choices':[{'finish_reason':'length','message':{'content':ResearchDraft(task_id='t',plan_revision=0,findings=[]).model_dump_json()}}]}
    with pytest.raises(ModelTruncated):JSONModelAdapter(ExecutionLimits(),transport).complete(ResearchDraft,{})


def test_schema_overhead_cannot_bypass_complete_request_budget(monkeypatch):
    configured(monkeypatch);monkeypatch.setenv('LEGAL_CONTEXT_MAX_BYTES','2000')
    called=[]
    with pytest.raises(ExecutionStopped,match='request exceeds'):
        JSONModelAdapter(ExecutionLimits(),lambda body:called.append(body)).complete(ResearchDraft,{'role':'researcher'})
    assert not called


def test_shared_state_two_agents_cas_handoff_preserves_both_patches(tmp_path,heat_task,heat_context):
    trace=ActivityTrace(JSONLEventSink(tmp_path/'trace.jsonl'))
    state=SharedInvestigationState(trace)
    result=LegalResearchWorkflow(reasoning_mode='demo_deterministic').run(heat_task,heat_context)
    board=board_update(result,heat_context.evidence)
    from threading import Barrier
    barrier=Barrier(2)
    def update(actor):
        version=state.read(heat_task.task_id).version
        barrier.wait(timeout=3)
        while True:
            try:
                return state.update(heat_task.task_id,actor=actor,expected_version=version,
                    board=board if actor=='legal' else None,
                    coverage_gaps=[{'source':actor,'reason':'coverage is bounded'}],status='completed' if actor=='legal' else 'running')
            except ValueError as error:
                assert 'Stale' in str(error)
                version=state.read(heat_task.task_id).version
    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(update,['planner','legal']))
    snapshot=state.read(heat_task.task_id)
    assert snapshot.version==2 and set(snapshot.task_status)=={'planner','legal'}
    assert snapshot.accepted_findings and snapshot.authority_refs and snapshot.evidence_refs
    assert {g['actor'] for g in snapshot.coverage_gaps}=={'planner','legal'}
    with pytest.raises(ValueError,match='Stale'):state.update(heat_task.task_id,actor='planner',expected_version=0,status='error')
    state.update(heat_task.task_id,actor='root_critic',expected_version=2,critic_decisions=[{'outcome':'BLOCKED'}],status='blocked')
    final=state.read(heat_task.task_id)
    assert final.root_blocked and not final.accepted_findings and final.task_status['investigation']=='blocked'
    assert final.evidence_refs==snapshot.evidence_refs and len(final.critic_decisions)>len(snapshot.critic_decisions)
    snapshot.evidence_refs.clear()
    assert state.read(heat_task.task_id).evidence_refs
    events=[json.loads(line)['type'] for line in (tmp_path/'trace.jsonl').read_text().splitlines()]
    assert 'shared_state.updated' in events and 'shared_state.conflict' in events


def test_shared_state_rejects_unknown_board_references(heat_task):
    state=SharedInvestigationState(ActivityTrace())
    with pytest.raises(ValueError,match='Unknown evidence'):
        state.update(heat_task.task_id,actor='legal',expected_version=0,board={'task_id':heat_task.task_id,'reconciliation':{'accepted_ids':['not-retrieved']}})
    assert state.read(heat_task.task_id).version==0


def test_truncation_retry_is_not_reset_on_a_revision(heat_task,heat_context):
    from unittest.mock import Mock
    from agents.model_agents import ModelAgents
    from tools.legal_search import LegalSearchTool
    plan=ResearchPlan(task_id=heat_task.task_id,objective='heat',questions=[{'question_id':'law','prompt':'heat','recommended_tool':'legal_search'}])
    adapter=Mock();adapter.complete.side_effect=[ModelTruncated('truncated'),ResearchDraft(task_id=heat_task.task_id,plan_revision=0,findings=[]),ModelTruncated('truncated')]
    agents=ModelAgents(adapter)
    agents.research(heat_task,heat_context,plan,LegalSearchTool())
    with pytest.raises(ModelTruncated):agents.research(heat_task,heat_context,plan,LegalSearchTool())
    assert adapter.complete.call_count==3


@pytest.mark.parametrize('limit,count',[(3,4),(1,2)])
def test_wire_schema_enforces_observation_limits(limit,count):
    from citations import selection_schema
    from pydantic import ValidationError
    wire=selection_schema([],[],max_observations=limit)
    with pytest.raises(ValidationError):wire.model_validate({'task_id':'t','findings':[
        {'finding_id':str(i),'issue':'maintenance','summary':'Observation'} for i in range(count)]})
