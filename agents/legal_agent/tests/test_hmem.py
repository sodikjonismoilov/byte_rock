import json
from pathlib import Path
import shutil
import subprocess
import pytest
from memory import LegalMemory
from models.schemas import CriticOutcome,InvestigationStatus
from tools.execution import ExecutionBudget
from workflow import LegalResearchWorkflow

pytestmark=pytest.mark.skipif(shutil.which('node') is None,reason='Node 22+ required for official H-MEM reference')


def prepared_context(context):
    for record in context.evidence:record.metadata['source_url']='https://example.gov/fixture/'+record.evidence_id
    return context


def test_cold_warm_actual_engine_persistence_and_provenance(tmp_path,heat_task,heat_context):
    prepared_context(heat_context)
    folder=tmp_path/'memory'
    cold=LegalResearchWorkflow(reasoning_mode='demo_deterministic',memory=LegalMemory(folder,allow_sample=True)).run(heat_task,heat_context)
    assert cold.status.value=='completed'
    assert any(e['type']=='memory.retrieved' and e['data']['count']==0 for e in cold.activity_events)
    assert (folder/'state.json').exists() and (folder/'ledger.jsonl').exists()
    original_count=len(json.loads((folder/'state.json').read_text())['records'])
    warm=LegalResearchWorkflow(reasoning_mode='demo_deterministic',memory=LegalMemory(folder,allow_sample=True)).run(heat_task,heat_context)
    assert any(e['type']=='memory.retrieved' and e['data']['count']>0 for e in warm.activity_events)
    context=heat_context.model_copy(update={'identity':cold.identity,'reconciliation':cold.reconciliation})
    hints=LegalMemory(folder,allow_sample=True).retrieve(heat_task,context,budget=ExecutionBudget())
    assert hints and hints[0]['provenance']['refs'] and hints[0]['evidence_ids']
    assert hints[0]['timestamp'] and hints[0]['trust_label']=='validated_sample_finding'
    assert not hints[0]['is_evidence']
    state=json.loads((folder/'state.json').read_text())
    assert len(state['records'])==original_count  # Idempotent repeated validated results.
    from context import agent_context
    projected=agent_context(heat_task,context.model_copy(update={'untrusted_memory':hints}))
    assert projected['untrusted_memory'][0]['provenance']['refs']
    assert not projected['untrusted_memory'][0]['is_evidence']
    assert all('raw_record' not in m['content'] for m in state['records'])
    assert (folder/'state.json').stat().st_mode & 0o777==0o600


def test_blocked_or_unverified_findings_not_durable(tmp_path,heat_task,heat_context):
    prepared_context(heat_context)
    result=LegalResearchWorkflow(reasoning_mode='demo_deterministic').run(heat_task,heat_context)
    context=heat_context.model_copy(update={'identity':result.identity,'reconciliation':result.reconciliation})
    memory=LegalMemory(tmp_path,allow_sample=True)
    result.critic_outcome=CriticOutcome.BLOCKED
    assert memory.store(heat_task,context,result,budget=ExecutionBudget())==[]
    assert not (tmp_path/'state.json').exists()
    result.critic_outcome=CriticOutcome.INCONCLUSIVE;result.status=InvestigationStatus.INCONCLUSIVE
    memory.store(heat_task,context,result,budget=ExecutionBudget())
    state=json.loads((tmp_path/'state.json').read_text())
    assert all(m['layer']=='working' and json.loads(m['content'])['trust_label']=='review_feedback_only' for m in state['records'])
    assert all('findings' not in json.loads(m['content']) for m in state['records'])


def test_rejected_evidence_invalidation_scope_and_supersession(tmp_path,heat_task,heat_context):
    from models.reconciliation import ReconciliationResult
    prepared_context(heat_context)
    result=LegalResearchWorkflow(reasoning_mode='demo_deterministic').run(heat_task,heat_context)
    context=heat_context.model_copy(update={'identity':result.identity,'reconciliation':result.reconciliation})
    memory=LegalMemory(tmp_path,allow_sample=True)
    saved=memory.store(heat_task,context,result,budget=ExecutionBudget())
    assert saved
    hints=memory.retrieve(heat_task,context,budget=ExecutionBudget());assert hints
    held={e for m in hints for e in m['evidence_ids']}
    held_context=context.model_copy(update={'reconciliation':ReconciliationResult(rejected_ids=list(held))})
    assert not memory.retrieve(heat_task,held_context,budget=ExecutionBudget())
    for m in saved:memory.invalidate(heat_task,context,m['id'],budget=ExecutionBudget())
    assert not LegalMemory(tmp_path,allow_sample=True).retrieve(heat_task,context,budget=ExecutionBudget())
    assert all(m['supersededBy']=='invalidated' for m in json.loads((tmp_path/'state.json').read_text())['records'])


def test_sample_memory_requires_explicit_opt_in(tmp_path,heat_task,heat_context):
    result=LegalResearchWorkflow(reasoning_mode='demo_deterministic').run(heat_task,heat_context)
    context=heat_context.model_copy(update={'identity':result.identity})
    with pytest.raises(ValueError,match='fixture opt-in'):
        LegalMemory(tmp_path).retrieve(heat_task,context,budget=ExecutionBudget())


def test_official_vendored_hmem_conformance():
    root=Path(__file__).resolve().parents[3]
    result=subprocess.run(['node','--experimental-transform-types',str(root/'agents/legal_agent/vendor/hmem/conformance/runner.ts')],
                          capture_output=True,text=True,timeout=20,
                          env={**__import__('os').environ,'HMEM_IMPL':str(root/'agents/legal_agent/vendor/hmem/src/index.ts')})
    assert result.returncode==0,result.stdout+result.stderr
    assert '13/13 checks passed' in result.stdout


def test_replacement_invalidation_retains_ledger_and_scoped_lineage(tmp_path,heat_task,heat_context):
    prepared_context(heat_context)
    result=LegalResearchWorkflow(reasoning_mode='demo_deterministic').run(heat_task,heat_context)
    context=heat_context.model_copy(update={'identity':result.identity,'reconciliation':result.reconciliation})
    memory=LegalMemory(tmp_path,allow_sample=True)
    old=memory.store(heat_task,context,result,budget=ExecutionBudget())[0]
    corrected=result.model_copy(deep=True)
    corrected.findings[0].summary+=' Corrected fixture summary after review.'
    new=memory.store(heat_task,context,corrected,budget=ExecutionBudget())[0]
    assert old['id']!=new['id']
    memory.invalidate(heat_task,context,old['id'],budget=ExecutionBudget(),superseded_by=new['id'])
    records=json.loads((tmp_path/'state.json').read_text())['records']
    assert next(r for r in records if r['id']==old['id'])['supersededBy']==new['id']
    assert next(r for r in records if r['id']==new['id'])['derivedFrom']
    ledger=[json.loads(line) for line in (tmp_path/'ledger.jsonl').read_text().splitlines()]
    assert any(row['action']=='update' and row['memoryId']==old['id'] for row in ledger)
