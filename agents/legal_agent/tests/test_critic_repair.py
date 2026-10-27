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


# --- schema-derived example and required-field repair note ---
from citations import selection_schema
from models.schemas import ResearchDraft, ResearchPlan
from tools.llm import model_request
from tools.schema_hints import example_object, required_fields_note

SENTINEL = 'SECRET-SENTINEL-VALUE-123'


def wire_for(schema):
    if schema is ResearchDraft:
        return selection_schema([{'id': 'hpd-heat-hot-water'}], ['EV-HEAT-HPD-002']).model_json_schema(), selection_schema([{'id': 'hpd-heat-hot-water'}], ['EV-HEAT-HPD-002'])
    return schema.model_json_schema(), schema


@pytest.mark.parametrize('schema', [ResearchPlan, ResearchDraft, CriticReport])
def test_example_object_is_schema_valid_for_every_structured_call(schema):
    schema_json, model = wire_for(schema)
    example = example_object(schema_json, {'task_id': 't1'})
    model.model_validate(example)  # Strict validation of the example itself.
    assert example['task_id'] == 't1'
    if schema is CriticReport:
        assert set(example) == {'task_id', 'outcome'}
    if schema is ResearchDraft:
        citation = example['findings'][0]['legal_conclusions'][0]['citations'][0]
        assert citation['authority_id'] == 'hpd-heat-hot-water' and 'supporting_quote' in citation
        assert example['findings'][0]['evidence_ids'] == ['EV-HEAT-HPD-002']
    if schema is ResearchPlan:
        assert {'question_id', 'prompt'} <= set(example['questions'][0])


def test_every_request_carries_the_example_in_the_system_message():
    _, body = model_request(CriticReport, dict(PAYLOAD))
    system = body['messages'][0]['content']
    assert 'Return exactly one JSON object shaped like this example' in system
    assert '"task_id":"t1"' in system and '"outcome"' in system
    assert json.loads(body['messages'][-1]['content']) == PAYLOAD


def test_repair_note_lists_required_fields_and_types_but_never_response_values(adapter_for):
    adapter, calls, _ = adapter_for(json.dumps({'issues': [{'code': SENTINEL}], 'note': SENTINEL}), VALID)
    adapter.complete(CriticReport, PAYLOAD)
    system = calls[1]['messages'][0]['content']
    note = system.split('rejected by schema validation')[1]
    assert 'top-level object requires: task_id (string), outcome (string)' in note
    assert SENTINEL not in system and SENTINEL not in json.dumps(calls[1]['messages'][-1])


def test_observation_level_failure_gets_one_repair_with_nested_required_fields(adapter_for):
    payload = {'role': 'researcher', 'task_id': 't1', 'authorities': [{'id': 'hpd-heat-hot-water'}], 'reference_domains': {'evidence_ids': ['EV-HEAT-HPD-002']}}
    bad = json.dumps({'task_id': 't1', 'findings': [{'finding_id': 'f1', 'issue': 'heat', 'summary': 's', 'evidence_ids': ['EV-HEAT-HPD-002'],
        'legal_conclusions': [{'claim_scope': 'current_guidance', 'citations': [{'supporting_quote': SENTINEL}]}]}]})
    adapter, calls, sink = adapter_for(bad, bad)
    with pytest.raises(ExecutionStopped, match='Legal review unavailable: all Researcher observations failed validation'):
        adapter.complete(ResearchDraft, payload)
    assert len(calls) == 2  # One repair retry, no more.
    system = calls[1]['messages'][0]['content']
    assert 'citations requires: authority_id (string), supporting_quote (string)' in system and SENTINEL not in system
    retry = [e for e in sink.events if e['type'] == 'model.repair_retry']
    assert len(retry) == 1 and retry[0]['data']['role'] == 'researcher'


def test_required_fields_note_follows_nested_paths():
    schema_json, _ = wire_for(ResearchDraft)
    note = required_fields_note(schema_json, [{'path': ['findings', '0', 'legal_conclusions', '0', 'citations', '0', 'authority_id'], 'type': 'missing'}])
    assert note == 'findings.legal_conclusions.citations requires: authority_id (string), supporting_quote (string)'
    assert required_fields_note(schema_json, [{'path': ['findings'], 'type': 'missing'}]).startswith('top-level object requires: task_id (string), findings (array)')
