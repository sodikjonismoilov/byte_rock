import json
import os
from pathlib import Path
from unittest.mock import Mock
import pytest
from tools.meterless import (APP_ID,CHAT_TIMEOUT,MeterlessRuntime,MeterlessSettings,RuntimeConfig,
    MeterlessUnavailable,auto_detect,parse_connection)
from tools.execution import ExecutionBudget,ExecutionLimits,ExecutionStopped


@pytest.mark.parametrize('value',[
 '127.0.0.1:8088','http://127.0.0.1:8088/','http://127.0.0.1:8088/v1',
 'http://127.0.0.1:8088/v1/chat/completions','http://127.0.0.1:8088/v1/models',
 'http://127.0.0.1:8088/healthz'])
def test_normalize_pasted_urls(value):assert parse_connection(value)==('http://127.0.0.1:8088/v1',None)


def test_connect_link_fragment_is_private_and_persisted(tmp_path):
    settings=MeterlessSettings(tmp_path/'private.json')
    settings.save(base_url='http://192.168.1.5:8090/connect#k=private%2Btoken',model='meterless/future.deep')
    stored=settings.load()
    assert stored['base_url']=='http://192.168.1.5:8090/v1'
    assert stored['meterless_runtime_token']=='private+token'
    assert 'private+token' not in json.dumps(settings.public())
    assert 'connect#' not in settings.path.read_text()
    assert settings.path.stat().st_mode & 0o777==0o600
    settings.save(base_url='http://another-host:8088')
    assert not settings.load()['meterless_runtime_token']


@pytest.mark.parametrize('value',['http://user:pass@localhost:8088','http://localhost:8088/v1?token=private','file:///private','http://localhost:8088/connect#k=rt-local','http://localhost:8088/other'])
def test_bad_url_never_echoes_input(value):
    with pytest.raises(ValueError) as exc:parse_connection(value)
    assert value not in str(exc.value)


def test_ipv6_and_proxy_token_file(tmp_path,monkeypatch):
    assert parse_connection('[::1]:8088/v1/models')[0]=='http://[::1]:8088/v1'
    (tmp_path/'proxy-token').write_text('real-state-token\n')
    monkeypatch.setenv('METERLESS_STATE_DIR',str(tmp_path))
    config=RuntimeConfig.from_env(settings=MeterlessSettings(tmp_path/'settings.json'))
    assert config.token=='real-state-token'
    assert 'real-state-token' not in repr(config)


@pytest.mark.parametrize('code',[401,403])
def test_wrong_token_is_unauthorized_not_offline(code):
    transport=Mock(return_value=(code,None))
    runtime=MeterlessRuntime(RuntimeConfig(token='wrong-token'),transport=transport)
    result=runtime.probe()
    assert result['status']=='unauthorized' and result['requires_token']
    method,url,headers,body,timeout=transport.call_args.args
    assert method=='GET' and url.endswith('/v1/models')
    assert headers['Authorization']=='Bearer wrong-token'
    assert headers['meterless-app']==APP_ID
    assert 'wrong-token' not in json.dumps(result)
    with pytest.raises(MeterlessUnavailable,match='unauthorized'):runtime.complete_text('hello')


@pytest.mark.parametrize('code,data',[(200,{}),(200,{'data':[{'id':'other/model'}]}),(200,None),(500,{}),(0,None)])
def test_no_usable_discovery_is_offline(code,data):
    runtime=MeterlessRuntime(transport=Mock(return_value=(code,data)))
    assert runtime.probe()['status']=='offline'


def test_auto_detect_saves_first_unauthorized_hit_and_stops(tmp_path):
    calls=[]
    def transport(method,url,*args):
        calls.append(url)
        return (401,None) if url=='http://localhost:8090/v1/models' else (0,None)
    settings=MeterlessSettings(tmp_path/'settings.json')
    result=auto_detect(settings=settings,transport=transport)
    assert result['status']=='unauthorized'
    assert len(calls)==5
    assert settings.load()['base_url']=='http://localhost:8090/v1'
    assert calls[:3]==['http://127.0.0.1:8088/v1/models','http://localhost:8088/v1/models','http://[::1]:8088/v1/models']


def test_auto_detect_online_and_all_offline(tmp_path):
    settings=MeterlessSettings(tmp_path/'settings.json')
    result=auto_detect(settings=settings,transport=Mock(return_value=(200,{'data':[{'id':'meterless/auto'}]})))
    assert result['status']=='online' and settings.path.exists()
    before=settings.path.read_text()
    transport=Mock(return_value=(0,None))
    result=auto_detect(settings=settings,transport=transport)
    assert result['reason']=='LIVE_NIGHTSHIFT_NOT_AVAILABLE'
    assert transport.call_count==12 and settings.path.read_text()==before


def test_plain_text_is_a_string_and_chat_gets_180_seconds():
    transport=Mock(side_effect=[(200,{'data':[{'id':'meterless/auto'},{'id':'meterless/unrecognised.future'},{'id':'other/model'}]}),
                               (200,{'choices':[{'message':{'content':'plain text answer'}}]})])
    runtime=MeterlessRuntime(RuntimeConfig(token='real-token'),transport=transport)
    result=runtime.complete_text('unchanged\nplain "text"')
    assert result=='plain text answer' and isinstance(result,str)
    assert 'meterless/unrecognised.future' in runtime.models
    method,url,headers,body,timeout=transport.call_args.args
    assert headers['Authorization']=='Bearer real-token' and headers['meterless-scope']=='user'
    assert headers['meterless-app']==APP_ID and method=='POST'
    assert body['messages'][0]['content']=='unchanged\nplain "text"'
    assert 'response_format' not in body and timeout==CHAT_TIMEOUT==180
    with pytest.raises(ExecutionStopped,match='not advertised'):runtime.complete_text('hello',model='meterless/invented')


def test_chat_unauthorized_updates_connection_state():
    transport=Mock(side_effect=[(200,{'data':[{'id':'meterless/auto'}]}),(403,None)])
    runtime=MeterlessRuntime(RuntimeConfig(token='expired'),transport=transport)
    with pytest.raises(MeterlessUnavailable,match='unauthorized'):runtime.complete_text('hello')
    assert runtime.status=='unauthorized'


def test_meterless_structured_adapter_reuses_discovery_and_validation(monkeypatch,heat_task,heat_context):
    from tools.llm import JSONModelAdapter,BoundedModelAdapter
    from models.schemas import ResearchPlan
    from agents.planner import make_plan
    monkeypatch.setenv('LLM_PROVIDER','meterless');monkeypatch.setenv('METERLESS_RUNTIME_TOKEN','private-token')
    adapter=JSONModelAdapter(ExecutionLimits())
    plan=make_plan(heat_task,heat_context)
    adapter.runtime.transport=Mock(side_effect=[(200,{'data':[{'id':'meterless/auto'}]}),
        (200,{'model':'meterless/auto','choices':[{'message':{'content':plan.model_dump_json()}}]})])
    budget=ExecutionBudget()
    bounded=BoundedModelAdapter(adapter,budget.limits,budget)
    assert bounded.complete(ResearchPlan,{'task_id':heat_task.task_id}).task_id==heat_task.task_id
    assert adapter.request_timeout_seconds==180
    assert budget.model_calls==1 and budget.tool_calls==1
    assert adapter.call_history[0]['provider']=='meterless'
    assert adapter.runtime.transport.call_args.args[-1] > 170


def test_local_settings_surface_shows_token_field_and_never_returns_it(tmp_path):
    from main import create_app
    from tools.meterless_settings_ui import install_settings_routes
    app=create_app();settings=MeterlessSettings(tmp_path/'settings.json')
    install_settings_routes(app,settings=settings,transport=Mock(return_value=(401,None)))
    client=app.test_client()
    assert b'type="password"' in client.get('/providers/meterless/settings').data
    response=client.post('/providers/meterless/configure',json={'connect_link':'http://localhost:8088/connect#k=private-token'})
    assert response.json['status']=='unauthorized' and response.json['requires_token']
    assert 'private-token' not in response.get_data(as_text=True)
    assert settings.load()['meterless_runtime_token']=='private-token'
    assert client.get('/providers/meterless',environ_overrides={'REMOTE_ADDR':'192.168.0.1'}).status_code==403
    assert client.post('/providers/meterless/configure',json={},headers={'Origin':'https://evil.invalid'}).status_code==403


def test_saved_token_never_follows_an_environment_host_change(tmp_path,monkeypatch):
    settings=MeterlessSettings(tmp_path/'settings.json')
    settings.save(base_url='http://localhost:8088',token='private-runtime-token')
    monkeypatch.setenv('METERLESS_BASE_URL','http://different-host:8088')
    config=RuntimeConfig.from_env(settings=settings)
    assert config.base_url=='http://different-host:8088/v1' and not config.token


def test_legacy_nightshift_maps_to_canonical_meterless_provider(monkeypatch,tmp_path):
    from tools.llm import provider_configuration
    monkeypatch.setenv('METERLESS_SETTINGS_FILE',str(tmp_path/'settings.json'))
    monkeypatch.setenv('LLM_PROVIDER','nightshift')
    monkeypatch.setenv('NIGHTSHIFT_BASE_URL','http://runtime-on-lan:8088/healthz')
    monkeypatch.setenv('NIGHTSHIFT_MODEL','meterless/text.deep')
    monkeypatch.setenv('NIGHTSHIFT_API_KEY','real-legacy-runtime-token')
    provider,base,model,token=provider_configuration()
    assert (provider,base,model)==('meterless','http://runtime-on-lan:8088/v1','meterless/text.deep')
    assert token=='real-legacy-runtime-token'
