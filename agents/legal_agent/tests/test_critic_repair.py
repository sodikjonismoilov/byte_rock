"""One repair retry for schema-invalid model output; the strict schema is never relaxed or filled in."""
import json
import pytest
from events import ActivityTrace, InMemoryEventSink
from models.schemas import CriticReport
from tools.execution import ExecutionBudget, ExecutionLimits, ExecutionStopped
from tools.llm import JSONModelAdapter

PAYLOAD = {'role': 'independent_critic', 'task_id': 't1'}
VALID = CriticReport(task_id='t1', outcome='REVISE', reasoning_mode='fixture').model_dump_json()


@pytest.fixture
def adapter_for(monkeypatch):
    for key, value in {'LLM_PROVIDER': 'nvidia', 'NVIDIA_MODEL': 'fixture-model', 'NVIDIA_API_KEY': 'private-sentinel',
                       'LEGAL_CONTEXT_MAX_BYTES': '60000', 'LEGAL_CONTEXT_MAX_TOKENS': '60000', 'LEGAL_MODEL_MAX_TOKENS': '100000'}.items():
        monkeypatch.setenv(key, value)

    def build(*answers):
        sink = InMemoryEventSink(); calls = []
        queue = list(answers)
        def transport(body):
            calls.append(body)
            return {'choices': [{'finish_reason': 'stop', 'message': {'content': queue.pop(0)}}]}
        adapter = JSONModelAdapter(ExecutionLimits(), transport, budget=ExecutionBudget(trace=ActivityTrace(sink)))
        return adapter, calls, sink
    return build


def test_repaired_answer_succeeds_with_same_strict_schema_and_traces_the_retry(adapter_for):
    adapter, calls, sink = adapter_for('{"issues":[]}', VALID)
    report = adapter.complete(CriticReport, PAYLOAD)
    assert report.outcome.value == 'REVISE' and report.task_id == 't1'
    assert len(calls) == 2
    assert 'task_id (missing)' in calls[1]['messages'][0]['content'] and 'outcome (missing)' in calls[1]['messages'][0]['content']
    assert json.loads(calls[1]['messages'][-1]['content']) == PAYLOAD  # Same payload, note only in instructions.
    retry = [e for e in sink.events if e['type'] == 'model.repair_retry']
    assert len(retry) == 1 and retry[0]['data']['role'] == 'independent_critic' and retry[0]['data']['reason'] == 'invalid_structured_output'
    assert {tuple(v['path']) for v in retry[0]['data']['validation']} == {('task_id',), ('outcome',)}


def test_second_invalid_answer_still_stops_with_existing_error_and_one_extra_call(adapter_for):
    adapter, calls, sink = adapter_for('{"issues":[]}', '{"revision_instructions":[]}')
    with pytest.raises(ExecutionStopped, match='Model returned invalid structured output'):
        adapter.complete(CriticReport, PAYLOAD)
    assert len(calls) == 2  # Never more than one extra call.
    failed = [e for e in sink.events if e['type'] == 'model.failed']
    assert [e['data']['repair'] for e in failed] == [False, True]
    assert len([e for e in sink.events if e['type'] == 'model.repair_retry']) == 1


def test_missing_outcome_is_never_accepted_or_defaulted(adapter_for):
    adapter, calls, _ = adapter_for('{"task_id":"t1","issues":[]}', '{"task_id":"t1","issues":[]}')
    with pytest.raises(ExecutionStopped, match='invalid structured output'):
        adapter.complete(CriticReport, PAYLOAD)
    assert len(calls) == 2


def test_fenced_json_is_not_tolerated(adapter_for):
    adapter, calls, _ = adapter_for('```json\n' + VALID + '\n```', '```json\n' + VALID + '\n```')
    with pytest.raises(ExecutionStopped, match='invalid structured output'):
        adapter.complete(CriticReport, PAYLOAD)


def test_valid_first_answer_makes_a_single_call(adapter_for):
    adapter, calls, sink = adapter_for(VALID)
    adapter.complete(CriticReport, PAYLOAD)
    assert len(calls) == 1 and not [e for e in sink.events if e['type'] == 'model.repair_retry']


def test_truncation_and_transport_errors_are_not_repair_retried(adapter_for):
    adapter, calls, _ = adapter_for('x')
    adapter.transport = lambda body: calls.append(body) or {'choices': []}  # Malformed envelope: nothing to repair.
    with pytest.raises(ExecutionStopped, match='invalid structured output'):
        adapter.complete(CriticReport, PAYLOAD)
    assert len(calls) == 1
