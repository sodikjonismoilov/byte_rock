import json
import urllib.error
from unittest.mock import Mock
import pytest
from agents.planner import make_plan
from agents.researcher import research
from agents.critic import critique_draft
from models.schemas import ResearchPlan, ResearchDraft, CriticReport, CriticOutcome, CriticIssue
from tools.execution import ExecutionLimits, ExecutionStopped
from tools.llm import JSONModelAdapter
from tools.legal_search import LegalSearchTool
from workflow import LegalResearchWorkflow


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv('LLM_BASE_URL','https://provider.invalid/v1')
    monkeypatch.setenv('LLM_MODEL','test-model')
    monkeypatch.setenv('LLM_API_KEY','test-secret-never-in-prompt')


def test_adapter_validates_json_and_keeps_key_out_of_payload(configured, heat_task,heat_context):
    plan=make_plan(heat_task,heat_context)
    transport=Mock(return_value={'choices':[{'message':{'content':plan.model_dump_json()}}]})
    adapter=JSONModelAdapter(ExecutionLimits(),transport)
    assert adapter.complete(ResearchPlan,{'role':'planner'}).task_id == heat_task.task_id
    assert 'test-secret-never-in-prompt' not in json.dumps(transport.call_args.args)
    transport.return_value={'choices':[{'message':{'content':'{"questions":"invalid"}'}}]}
    with pytest.raises(ExecutionStopped,match='invalid structured'):
        adapter.complete(ResearchPlan,{})


def test_api_retries_and_sanitizes_errors(configured):
    transport=Mock(side_effect=urllib.error.HTTPError('https://x',503,'test-secret',{},None))
    adapter=JSONModelAdapter(ExecutionLimits(max_retries=1),transport)
    with pytest.raises(ExecutionStopped) as exc:
        adapter.complete(ResearchPlan,{})
    assert adapter.calls == transport.call_count == 2
    assert 'test-secret' not in str(exc.value)


def test_model_workflow_replans_and_preserves_unaffected_findings(heat_task,heat_context):
    plan=make_plan(heat_task,heat_context)
    # Keep model plans small and executable.
    plan.questions=plan.questions[1:2]
    revised=plan.model_copy(deep=True)
    revised.questions[0].prompt='Check heat duty applicability and confirm operative source version'
    good=research(heat_task,heat_context,plan)
    from models.schemas import LegalConclusion
    authority=next(s for s in LegalSearchTool().sources if s.id=='hpd-heat-hot-water')
    for finding in good.findings:
        finding.legal_conclusions=[LegalConclusion(statement='Current official guidance states: '+authority.excerpt,
            source_ids=[authority.id],claim_scope='current_guidance',support_quotes={authority.id:authority.excerpt})]
    bad=good.model_copy(deep=True)
    stable=good.findings[0].model_copy(deep=True)
    stable.finding_id='retained-valid'
    bad.findings.append(stable)
    bad.findings[0].legal_conclusions[0].source_ids=['invented']
    revise=CriticReport(task_id=heat_task.task_id,outcome='REVISE',issues=[CriticIssue(code='unsupported_legal_conclusion',message='Retrieve support',finding_ids=[bad.findings[0].finding_id])])
    passed=CriticReport(task_id=heat_task.task_id,outcome='PASS')
    adapter=Mock()
    adapter.complete.side_effect=[plan,bad,revise,revised,good,passed]
    result=LegalResearchWorkflow(model_adapter=adapter).run(heat_task,heat_context)
    assert result.status.value == 'completed', result.model_dump()
    assert result.revision_cycles == 1
    assert result.reasoning_mode == 'llm:injected'
    assert any(f.finding_id=='retained-valid' for f in result.findings)
    assert result.plans[0].questions[0].prompt != result.plans[1].questions[0].prompt
    assert result.tool_calls == 3  # Includes the independently executed Critic-directed authority lookup.
    assert any(e["type"]=="critic.follow_up" for e in result.activity_events)
    assert adapter.complete.call_count == 6


def test_unchanged_model_research_plan_stops(heat_task,heat_context):
    plan=make_plan(heat_task,heat_context); plan.questions=plan.questions[1:2]
    draft=ResearchDraft(task_id=heat_task.task_id,plan_revision=0,findings=[])  # Isolate unchanged-plan protection from external historical gaps.
    report=CriticReport(task_id=heat_task.task_id,outcome='REVISE',revision_instructions=['Research a different source'])
    adapter=Mock(); adapter.complete.side_effect=[plan,draft,report,plan]
    result=LegalResearchWorkflow(model_adapter=adapter).run(heat_task,heat_context)
    assert result.status.value=='inconclusive'
    assert 'did not change research' in result.errors[0].message


def test_model_cannot_select_write_tool():
    with pytest.raises(ValueError):
        ResearchPlan.model_validate({'task_id':'x','objective':'write','questions':[{'question_id':'q','prompt':'send email','recommended_tool':'send_email'}]})


def test_model_cannot_override_critic_gate(heat_task,heat_context):
    plan=make_plan(heat_task,heat_context); plan.questions=plan.questions[1:2]
    draft=research(heat_task,heat_context,plan)
    draft.findings[0].legal_conclusions[0].source_ids=['invented']
    adapter=Mock(); adapter.complete.side_effect=[plan,draft,CriticReport(task_id=heat_task.task_id,outcome='PASS')]
    result=LegalResearchWorkflow(model_adapter=adapter,max_revision_cycles=0).run(heat_task,heat_context)
    assert result.critic_outcome == CriticOutcome.REVISE
    assert result.status.value != 'completed'


def test_injected_models_still_obey_budget_and_deadline(heat_task,heat_context):
    from tools.llm import BoundedModelAdapter
    import time
    adapter=Mock()
    bounded=BoundedModelAdapter(adapter,ExecutionLimits(max_model_calls=0))
    with pytest.raises(ExecutionStopped,match='budget'):
        bounded.complete(ResearchPlan,{})
    adapter.complete.assert_not_called()
    def slow(*args):
        time.sleep(.03)
        return make_plan(heat_task,heat_context)
    adapter.complete.side_effect=slow
    bounded=BoundedModelAdapter(adapter,ExecutionLimits(model_timeout_seconds=.001))
    with pytest.raises(ExecutionStopped,match='deadline'):
        bounded.complete(ResearchPlan,{})


def test_injected_model_failure_returns_controlled_result(heat_task,heat_context):
    adapter=Mock(); adapter.complete.side_effect=RuntimeError('sensitive-secret')
    result=LegalResearchWorkflow(model_adapter=adapter).run(heat_task,heat_context)
    assert result.status.value=='inconclusive'
    assert 'sensitive-secret' not in result.model_dump_json()


def test_nvidia_configuration_uses_documented_endpoint_and_explicit_model(monkeypatch,heat_task,heat_context):
    from tools.llm import provider_configuration
    monkeypatch.setenv('LLM_PROVIDER','nvidia')
    monkeypatch.setenv('NVIDIA_MODEL','explicit-team-model')
    monkeypatch.setenv('NVIDIA_API_KEY','private-sentinel')
    monkeypatch.delenv('NVIDIA_BASE_URL',raising=False)
    provider,endpoint,model,_=provider_configuration()
    assert (provider,endpoint,model)==('nvidia','https://integrate.api.nvidia.com/v1','explicit-team-model')
    plan=make_plan(heat_task,heat_context)
    transport=Mock(return_value={'model':'actual-returned-model','usage':{'total_tokens':10},'choices':[{'message':{'content':plan.model_dump_json()}}]})
    adapter=JSONModelAdapter(ExecutionLimits(),transport)
    adapter.complete(ResearchPlan,{})
    assert adapter.call_history[0]['returned_model']=='actual-returned-model'
    assert 'private-sentinel' not in json.dumps(adapter.call_history)
    monkeypatch.delenv('NVIDIA_MODEL')
    with pytest.raises(ExecutionStopped,match='no provider fallback'):
        JSONModelAdapter(ExecutionLimits(),transport)


def test_explicit_model_mode_without_configuration_is_inconclusive(monkeypatch,heat_task,heat_context):
    for prefix in ('LLM','NVIDIA','NIGHTSHIFT'):
        for suffix in ('PROVIDER','MODEL','BASE_URL','API_KEY'):monkeypatch.delenv(prefix+'_'+suffix,raising=False)
    result=LegalResearchWorkflow(reasoning_mode='llm:configured').run(heat_task,heat_context)
    assert result.status.value=='inconclusive'
    assert result.execution['model_calls']==0
    assert not result.plans
    assert 'requires an explicitly configured' in result.errors[0].message


def test_full_payload_budget_is_enforced_even_for_injected_adapter():
    from tools.llm import BoundedModelAdapter
    adapter=Mock()
    with pytest.raises(ExecutionStopped,match='context budget'):
        BoundedModelAdapter(adapter,ExecutionLimits()).complete(ResearchPlan,{'draft':'x'*70000})
    adapter.complete.assert_not_called()


def test_nightshift_local_contract_normalizes_url_without_remote_plaintext(monkeypatch):
    from tools.llm import provider_configuration
    monkeypatch.setenv('LLM_PROVIDER','nightshift')
    monkeypatch.setenv('NIGHTSHIFT_BASE_URL','http://127.0.0.1:8088/v1/chat/completions')
    monkeypatch.setenv('NIGHTSHIFT_MODEL','meterless/private-routing-mode')
    monkeypatch.setenv('NIGHTSHIFT_API_KEY','actual-local-token')
    assert provider_configuration()[1]=='http://127.0.0.1:8088/v1'
    monkeypatch.setenv('NIGHTSHIFT_BASE_URL','http://user:password@remote.invalid/v1')
    with pytest.raises(ExecutionStopped):provider_configuration()
    monkeypatch.setenv('NIGHTSHIFT_BASE_URL','http://localhost:8088/v1')
    monkeypatch.setenv('NIGHTSHIFT_API_KEY','rt-local')
    with pytest.raises(ExecutionStopped,match='real runtime token'):provider_configuration()
