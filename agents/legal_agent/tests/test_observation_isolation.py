"""Strict observation isolation; rejected claims never reach the legal Critic."""
import json
import pytest
from pydantic import ValidationError
from citations import selection_schema,validate_observations
from tools.legal_search import LegalSearchTool
from tools.llm import JSONModelAdapter
from tools.execution import ExecutionLimits,ExecutionStopped
from models.schemas import ResearchPlan,CriticReport
from workflow import LegalResearchWorkflow
from events import ActivityTrace


def observation(fid,authority='hpd-heat-hot-water'):
    source=next(s for s in LegalSearchTool().sources if s.id=='hpd-heat-hot-water')
    return {'finding_id':fid,'issue':'heat','summary':'Current heat guidance; current property conditions require verification.',
        'evidence_ids':['EV-HEAT-HPD-002'],'legal_conclusions':[{'claim_scope':'current_guidance',
            'citations':[{'authority_id':authority,'supporting_quote':source.excerpt}]}]}


def wire():
    sources=[s.model_dump(mode='json') for s in LegalSearchTool().sources if s.id=='hpd-heat-hot-water']
    return selection_schema(sources,['EV-HEAT-HPD-002'])


def test_mixed_observations_drop_whole_invalid_observation_without_repair():
    invalid=observation('bad','not-retrieved');invalid['legal_conclusions'].append(observation('other')['legal_conclusions'][0])
    trace=ActivityTrace();value=validate_observations(wire(),json.dumps({'task_id':'t','findings':[observation('good'),invalid]}),trace)
    assert [f.finding_id for f in value.findings]==['good']
    assert value.findings[0].legal_conclusions[0].citations[0].authority_id=='hpd-heat-hot-water'
    assert any('discarded in full' in text for text in value.caveats)
    rejected=[e for e in trace.events if e['type']=='research.observation_rejected']
    assert len(rejected)==1 and rejected[0]['data']['finding_id']=='bad'
    assert rejected[0]['data']['accepted_as_claim'] is False
    assert 'not-retrieved' not in json.dumps(trace.events)


def test_all_invalid_marks_legal_review_unavailable():
    trace=ActivityTrace()
    with pytest.raises(ExecutionStopped,match='Legal review unavailable'):
        validate_observations(wire(),json.dumps({'task_id':'t','findings':[observation('bad','not-retrieved')]}),trace)
    assert [e['type'] for e in trace.events][-1]=='legal.review_unavailable'


@pytest.mark.parametrize('change', ['malformed','missing_task','overflow','global_unknown_evidence','duplicate_ids'])
def test_observation_isolation_never_repairs_envelope_or_array_limits(change):
    value={'task_id':'t','findings':[observation('good'),observation('bad','not-retrieved')]}
    if change=='malformed':content=json.dumps(value)[:-1]
    else:
        if change=='missing_task':value.pop('task_id')
        if change=='overflow':value['findings']=[observation('bad'+str(i),'not-retrieved') for i in range(4)]
        if change=='global_unknown_evidence':value['evidence_ids_used']=['not-registered']
        if change=='duplicate_ids':value['findings'][1]['finding_id']='good'
        content=json.dumps(value)
    with pytest.raises((ValidationError,ValueError)):validate_observations(wire(),content)


@pytest.mark.parametrize('all_invalid',[False,True])
def test_critic_receives_only_valid_observations_or_is_unavailable(monkeypatch,heat_task,heat_context,all_invalid):
    monkeypatch.setenv('LLM_PROVIDER','nvidia');monkeypatch.setenv('NVIDIA_MODEL','fixture-model');monkeypatch.setenv('NVIDIA_API_KEY','private-observation-key')
    monkeypatch.setenv('LEGAL_CONTEXT_MAX_BYTES','60000');monkeypatch.setenv('LEGAL_CONTEXT_MAX_TOKENS','60000');monkeypatch.setenv('LEGAL_MODEL_MAX_TOKENS','100000')
    roles=[];reviewed=[]
    def transport(body):
        payload=json.loads(body['messages'][-1]['content']);roles.append(payload['role'])
        if payload['role']=='planner':
            content=ResearchPlan(task_id=heat_task.task_id,objective='Heat duty',questions=[{'question_id':'law','prompt':'heat hot water','recommended_tool':'legal_search'}]).model_dump_json()
        elif payload['role']=='researcher':
            content=json.dumps({'task_id':heat_task.task_id,'findings':([observation('good')] if not all_invalid else [])+[observation('bad','not-retrieved')]})
        else:
            reviewed.extend(payload['draft']['findings'])
            content=CriticReport(task_id=heat_task.task_id,outcome='PASS').model_dump_json()
        return {'choices':[{'finish_reason':'stop','message':{'content':content}}]}
    result=LegalResearchWorkflow(model_adapter=JSONModelAdapter(ExecutionLimits(),transport),max_revision_cycles=0).run(heat_task,heat_context)
    assert any(e['type']=='research.observation_rejected' for e in result.activity_events)
    if all_invalid:
        assert roles==['planner','researcher','researcher'] and not reviewed and not result.findings  # One repair retry first.
        assert result.status.value=='inconclusive' and not result.review_history
        assert 'Legal review unavailable' in result.errors[0].message
    else:
        assert roles==['planner','researcher','independent_critic']
        assert [f['finding_id'] for f in reviewed]==['good']
        assert result.review_history and result.critic_outcome.value=='PASS'
        claim=result.findings[0].legal_conclusions[0]
        assert claim.supported and claim.citations[0]['authority_id']=='hpd-heat-hot-water'
        assert result.citation_metrics['claims_with_verified_support']==1


def test_root_blocked_precedence_prevents_model_execution(heat_task,heat_context):
    from unittest.mock import Mock
    heat_context.root_critic_outcome='BLOCKED'
    adapter=Mock()
    result=LegalResearchWorkflow(model_adapter=adapter).run(heat_task,heat_context)
    assert result.critic_outcome.value=='BLOCKED' and not result.findings
    adapter.complete.assert_not_called()
