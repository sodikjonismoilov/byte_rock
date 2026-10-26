import time
from unittest.mock import Mock
import pytest
from tools.execution import ExecutionLimits, ExecutionStopped, ReadOnlySearch, PropertyQuery
from tools.legal_search import LegalSearchTool
from workflow import LegalResearchWorkflow


def test_limits_and_template_permissions():
    with pytest.raises(ValueError): ExecutionLimits(max_tool_calls=11)
    with pytest.raises(ValueError): ExecutionLimits(max_revision_cycles=3)
    with pytest.raises(ValueError): PropertyQuery(bin='1; DROP TABLE t')
    with pytest.raises(ValueError): PropertyQuery(bin='1000001',template='write').statement()
    assert PropertyQuery(bin='1000001').statement()[1] == {'bin':'1000001'}


def test_budget_counts_retry_attempts_and_cache():
    tool=Mock(); tool.sources=[]; tool.search.side_effect=ConnectionError('transient')
    bounded=ReadOnlySearch(tool,ExecutionLimits(max_tool_calls=2,max_retries=2))
    with pytest.raises(ExecutionStopped): bounded.search('heat')
    assert tool.search.call_count == 2 and bounded.calls == 2
    cached=ReadOnlySearch(LegalSearchTool(),ExecutionLimits())
    cached.search('heat'); cached.search('heat')
    assert cached.calls == 1


def test_tool_timeout():
    tool=Mock(); tool.sources=[]
    def slow(*a,**kw): time.sleep(.05); return []
    tool.search.side_effect=slow
    bounded=ReadOnlySearch(tool,ExecutionLimits(tool_timeout_seconds=.001,max_retries=0))
    with pytest.raises(ExecutionStopped): bounded.search('heat')


def test_budget_stop_is_qualified(heat_task,heat_context):
    result=LegalResearchWorkflow(limits=ExecutionLimits(max_tool_calls=0)).run(heat_task,heat_context)
    assert result.status.value == 'inconclusive'
    assert result.errors[0].code == 'execution_stopped'


def test_missing_model_config_never_claims_demo(heat_task,heat_context,monkeypatch):
    monkeypatch.setenv('LLM_PROVIDER','compatible')
    monkeypatch.delenv('LLM_API_KEY',raising=False)
    result=LegalResearchWorkflow().run(heat_task,heat_context)
    assert result.reasoning_mode == 'llm:compatible'
    assert result.status.value == 'inconclusive'
    assert result.errors[0].code == 'execution_stopped'
