from unittest.mock import Mock
import pytest
from integration import LegalSharedAdapter, LegalSnapshot, legal_update, world_model_fact, hmem_add_input
from workflow import LegalResearchWorkflow


def keeper_fixture(task,context):
    snapshot={'version':4,'task':task.model_dump(mode='json'),'context':context.model_dump(mode='json'),
              'evidence_refs':{e.evidence_id:'https://example.gov/records/'+e.evidence_id for e in context.evidence}}
    keeper=Mock();keeper.load_snapshot.return_value=snapshot;keeper.retrieve_context.return_value=[]
    keeper.publish_legal.return_value={'status':'applied','version':5}
    return keeper,snapshot


def test_shared_boundary_reuses_snapshot_without_mutating_registry(heat_task,heat_context):
    keeper,snapshot=keeper_fixture(heat_task,heat_context)
    result,update=LegalSharedAdapter(keeper,LegalResearchWorkflow(reasoning_mode='demo_deterministic')).run(heat_task.task_id)
    assert result.findings and update['legal_findings']
    assert update['expected_version']==4
    assert update['authority_refs']
    assert update['canonical_identity_ref']=={}  # Fixture snapshot has no upstream identity.
    assert set(update['evidence_refs'])<=set(snapshot['evidence_refs'])
    keeper.publish_legal.assert_not_called();keeper.persist_memory.assert_not_called()
    assert keeper.load_snapshot.return_value==snapshot
    fact=world_model_fact(update,at='2026-10-25T00:00:00Z',run_id='run')
    assert fact['source']['runId']=='run'
    assert fact['value']['idempotency_key']==update['idempotency_key']
    memory=hmem_add_input(update,at_ms=1792886400000,run_id='run')
    assert memory['provenance']['refs']
    assert memory['derivedFrom']==list(update['evidence_refs'])


def test_shared_veto_no_claims_or_durable_memory(heat_task,heat_context):
    from models.schemas import CriticOutcome
    heat_context.root_critic_outcome=CriticOutcome.BLOCKED
    keeper,_=keeper_fixture(heat_task,heat_context)
    result,update=LegalSharedAdapter(keeper,LegalResearchWorkflow()).run(heat_task.task_id,publish=True,persist_memory=True)
    assert result.critic_outcome.value=='BLOCKED'
    assert not update['legal_findings']
    keeper.persist_memory.assert_not_called()
    assert keeper.publish_legal.call_args.args[0]['critic_outcome']=='BLOCKED'
    with pytest.raises(ValueError,match='Only validated'):hmem_add_input(update,at_ms=1,run_id='run')


def test_keeper_rejects_stale_update_before_memory(heat_task,heat_context):
    keeper,_=keeper_fixture(heat_task,heat_context)
    keeper.publish_legal.return_value={'status':'conflict'}
    with pytest.raises(ValueError,match='stale'):
        LegalSharedAdapter(keeper,LegalResearchWorkflow()).run(heat_task.task_id,publish=True,persist_memory=True)
    keeper.persist_memory.assert_not_called()


def test_identical_runs_delegate_atomic_dedup_to_keeper(heat_task,heat_context):
    keeper,_=keeper_fixture(heat_task,heat_context)
    applied=set()
    def publish(update):
        key=update['idempotency_key'];duplicate=key in applied;applied.add(key)
        return {'status':'duplicate' if duplicate else 'applied','version':5}
    keeper.publish_legal.side_effect=publish
    for _ in range(2):
        LegalSharedAdapter(keeper,LegalResearchWorkflow(reasoning_mode='demo_deterministic')).run(heat_task.task_id,publish=True)
    assert len(applied)==1
    assert keeper.publish_legal.call_count==2


def test_memory_hints_cannot_promote_rejected_evidence(heat_task,heat_context):
    from models.reconciliation import ReconciliationResult
    held=heat_context.evidence[-1].evidence_id
    heat_context.reconciliation=ReconciliationResult(rejected_ids=[held])
    keeper,_=keeper_fixture(heat_task,heat_context)
    keeper.retrieve_context.return_value=[{'task_id':heat_task.task_id,'provenance':{'refs':['x']},'evidence_ids':[held],'content':'trust me'},
                                         {'task_id':'another-task','provenance':{'refs':['x']},'content':'wrong building'}]
    workflow=LegalResearchWorkflow(reasoning_mode='demo_deterministic');original=workflow.run
    seen=[]
    def run(task,context,**kw):seen.extend(context.untrusted_memory);return original(task,context,**kw)
    workflow.run=run
    LegalSharedAdapter(keeper,workflow).run(heat_task.task_id)
    assert not seen


def test_shared_live_identity_required(heat_task,heat_context):
    heat_context.data_mode='live'
    keeper,_=keeper_fixture(heat_task,heat_context)
    with pytest.raises(ValueError,match='verified identity'):
        LegalSharedAdapter(keeper,LegalResearchWorkflow()).run(heat_task.task_id)


def test_invalidation_and_event_reads_are_owner_operations(heat_task,heat_context):
    keeper,_=keeper_fixture(heat_task,heat_context)
    keeper.invalidate_memory.return_value={'status':'applied'}
    adapter=LegalSharedAdapter(keeper,LegalResearchWorkflow())
    adapter.invalidate(heat_task.task_id,['m1'],evidence_ids=['e1'],expected_version=4,superseded_by='m2')
    request=keeper.invalidate_memory.call_args.args[0]
    assert request['expected_version']==4 and request['superseded_by']=='m2'
    assert request['idempotency_key']
    adapter.events(heat_task.task_id,'event1')
    keeper.read_events.assert_called_once_with(heat_task.task_id,'event1')


def test_receiving_canonical_live_identity_without_candidate_history(heat_task,heat_context):
    from models.identity import IdentityResult,IdentifierEvidence
    heat_task.building.bin='1000001'
    heat_context.data_mode='live'
    heat_context.identity=IdentityResult(canonical_address=heat_task.building.address,borough='Manhattan',
        verification_status='verified',identifiers={'bin':'1000001'},
        verified_identifiers=[IdentifierEvidence(kind='bin',value='1000001',source='official-source',record_id='official-building-1',authoritative=True)])
    for e in heat_context.evidence:e.metadata.update(bin='1000001')
    keeper,_=keeper_fixture(heat_task,heat_context)
    result,_=LegalSharedAdapter(keeper,LegalResearchWorkflow(reasoning_mode='demo_deterministic')).run(heat_task.task_id)
    assert result.identity.verification_status=='verified'
    assert result.identity.identifiers['bin']=='1000001'
    assert result.identity.verified_identifiers[0].record_id=='official-building-1'


def test_missing_evidence_returns_typed_followups(heat_task,heat_context):
    heat_context.evidence=[];heat_task.evidence_ids=[]
    keeper,_=keeper_fixture(heat_task,heat_context)
    result,update=LegalSharedAdapter(keeper,LegalResearchWorkflow(reasoning_mode='demo_deterministic')).run(heat_task.task_id)
    assert result.status.value=='inconclusive'
    assert update['follow_up_requests']
    assert all(r['kind']=='evidence_or_applicability' and r['task_id']==heat_task.task_id for r in update['follow_up_requests'])
    assert not update['legal_findings']
