import json
import pytest
from context import agent_context, context_bytes
from events import ActivityTrace, InMemoryEventSink, JSONLEventSink
from models.schemas import Finding
from models.reconciliation import ReconciliationResult
from tools.execution import ExecutionBudget, ExecutionLimits, ExecutionStopped
from workflow import LegalResearchWorkflow


def test_context_budget_provenance_uncertainties_and_original_registry(heat_task,heat_context,search_tool):
    evidence=heat_context.evidence[0]
    evidence.metadata.update(origin_record_id='official-123',source_url='https://example.gov/123',raw_record={'private':'x'*10000})
    heat_context.source_coverage=[{'source':'hpd','status':'unavailable'}]
    heat_context.unresolved_questions=['Is the current condition corrected?']
    heat_context.reconciliation=ReconciliationResult(accepted_ids=[evidence.evidence_id],quarantined_ids=[heat_context.evidence[-1].evidence_id])
    source=search_tool.sources[0]
    payload=agent_context(heat_task,heat_context,sources=[source,source],max_bytes=12000)
    assert context_bytes(payload)<=12000
    assert len(payload['authorities'])==1
    assert payload['authorities'][0]['excerpt']==source.excerpt
    assert payload['coverage'][0]['status']=='unavailable'
    assert payload['unresolved_questions']
    row=next(e for e in payload['evidence'] if e['evidence_id']==evidence.evidence_id)
    assert row['metadata']['origin_record_id']=='official-123'
    assert row['identity_match_status']=='accepted'
    assert 'raw_record' not in row['metadata']
    assert evidence.metadata['raw_record']['private']
    assert heat_context.evidence[-1].evidence_id not in [e['evidence_id'] for e in payload['evidence']]


def test_context_omits_whole_oversized_record_and_invalidated_findings(heat_task,heat_context):
    e=heat_context.evidence[0];e.description='original '*10000
    held=heat_context.evidence[-1].evidence_id
    heat_context.reconciliation=ReconciliationResult(rejected_ids=[held])
    f=Finding(finding_id='bad',issue='heat',summary='derived',evidence_ids=[held])
    payload=agent_context(heat_task,heat_context,findings=[f],max_bytes=3000)
    assert e.evidence_id in payload['selection']['omitted_evidence_ids']
    assert payload['selection']['invalidated_finding_ids']==['bad']
    assert not payload['prior_findings']
    assert len(e.description)>3000


def test_mandatory_uncertainty_never_silently_truncated(heat_task,heat_context):
    heat_context.unresolved_questions=['unknown '*2000]
    with pytest.raises(ExecutionStopped,match='Mandatory'):
        agent_context(heat_task,heat_context,max_bytes=1024)


def test_append_only_sanitized_trace(tmp_path,monkeypatch):
    monkeypatch.setenv('NVIDIA_API_KEY','secret-sentinel-123')
    memory=InMemoryEventSink();trace=ActivityTrace(memory,task_id='t')
    trace.emit('tool.failed',authorization='secret-sentinel-123',message='Bearer secret-sentinel-123',raw_record={'private':'tenant'})
    first=memory.events;first[0]['data']['authorization']='changed'
    assert memory.events[0]['data']['authorization']=='[REDACTED]'
    path=tmp_path/'events.jsonl';sink=JSONLEventSink(path)
    for event in memory.events:sink.append(event)
    trace.emit('critic.decision',outcome='BLOCKED')
    sink.append(memory.events[-1])
    rows=[json.loads(line) for line in path.read_text().splitlines()]
    assert len(rows)==2 and rows[0]['event_id']!=rows[1]['event_id']
    assert rows[0]['run_id']==rows[1]['run_id']
    assert 'secret-sentinel' not in path.read_text()
    assert 'tenant' not in path.read_text()


def test_workflow_trace_and_earlier_reviews_retained(heat_task,heat_context):
    sink=InMemoryEventSink();budget=ExecutionBudget(trace=ActivityTrace(sink))
    result=LegalResearchWorkflow(reasoning_mode='demo_deterministic').run(heat_task,heat_context,budget=budget)
    kinds=[e['type'] for e in sink.events]
    assert {'legal.started','identity.decided','plan.selected','critic.decision','report.generated','legal.finished'}<=set(kinds)
    assert len(result.review_history)>=3
    assert result.execution['run_id']==sink.events[0]['run_id']
    assert len(result.activity_events)==len(sink.events)
    assert {e['task_id'] for e in sink.events}=={heat_task.task_id}


def test_exhaustion_trace():
    budget=ExecutionBudget(ExecutionLimits(max_total_tool_calls=0))
    with pytest.raises(ExecutionStopped):budget.consume('tool','search')
    assert budget.trace.sink.events[-1]['type']=='budget.exhausted'


def test_original_context_lookup_retains_text_and_rejects_held(heat_context,search_tool):
    from context import original_context_items
    e=heat_context.evidence[0];s=search_tool.sources[0]
    original=original_context_items(heat_context,[s],evidence_ids=[e.evidence_id],authority_ids=[s.id])
    assert original['evidence'][0].description==e.description
    assert original['authorities'][0].excerpt==s.excerpt
    heat_context.reconciliation=ReconciliationResult(quarantined_ids=[e.evidence_id])
    with pytest.raises(ValueError,match='Held evidence'):
        original_context_items(heat_context,[s],evidence_ids=[e.evidence_id])


def test_jsonl_trace_also_exposes_in_memory_projection(tmp_path):
    trace=ActivityTrace(JSONLEventSink(tmp_path/'trace.jsonl'))
    trace.emit('investigation.started')
    assert trace.events[0]['type']=='investigation.started'
    assert json.loads((tmp_path/'trace.jsonl').read_text())['event_id']==trace.events[0]['event_id']


def test_usage_counters_remain_observable_without_leaking_tokens():
    from events import sanitize
    result=sanitize({'usage':{'prompt_tokens':200,'completion_tokens':50,'total_tokens':250,
        'prompt_tokens_details':{'cached_tokens':100,'api_key':'private'}},'token':'private',
        'message':'http://localhost:8088/connect#k=private'})
    assert result['usage']['total_tokens']==250
    assert result['usage']['prompt_tokens_details']['cached_tokens']==100
    assert result['token']=='[REDACTED]'
    assert 'private' not in json.dumps(result)
