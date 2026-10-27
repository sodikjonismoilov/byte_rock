import json
from unittest.mock import Mock
import pytest
from pydantic import ValidationError
from agents.model_agents import ModelAgents
from models.schemas import ResearchPlan, ResearchQuestion, ResearchDraft, Finding, LegalConclusion, CriticReport, CriticIssue
from tools.execution import ExecutionLimits,ExecutionStopped
from tools.legal_search import LegalSearchTool
from workflow import LegalResearchWorkflow


def responses(task,context):
    return ResearchPlan(task_id=task.task_id,objective='Inspect accepted heat evidence',questions=[
        ResearchQuestion(question_id='review',prompt='Review heat records',recommended_tool='evidence_review',evidence_ids=task.evidence_ids)])


def test_model_mode_executes_authority_search_and_supplies_exact_text(heat_task,heat_context):
    payloads=[]
    class Adapter:
        def complete(self,schema,payload):
            payloads.append(payload)
            if schema is ResearchPlan:return responses(heat_task,heat_context)
            if schema is ResearchDraft:return ResearchDraft(task_id=heat_task.task_id,plan_revision=payload['plan']['revision'],findings=[])
            return CriticReport(task_id=heat_task.task_id,outcome='INCONCLUSIVE')
    result=LegalResearchWorkflow(model_adapter=Adapter(),max_revision_cycles=0).run(heat_task,heat_context)
    assert result.tool_calls==1
    researcher=next(p for p in payloads if p['role']=='researcher')
    source=next(s for s in researcher['authorities'] if s['id']=='hpd-heat-hot-water')
    assert source['excerpt'] and source['identifier'] and source['jurisdiction']=='NYC'
    assert source['excerpt_provenance']['excerpt_sha256']
    assert source['excerpt_provenance']['historical_version_verified'] is False
    assert result.legal_sources and result.retrieved_source_ids
    assert any(q.recommended_tool=='legal_search' for q in result.plans[0].questions)


@pytest.mark.parametrize('factory',[
    lambda:ResearchQuestion(question_id='q',prompt='bad',evidence_ids=['mem-2']),
    lambda:Finding(finding_id='F002',issue='heat',summary='bad',evidence_ids=['mem-3']),
    lambda:LegalConclusion(statement='bad',source_ids=['mem-2']),
    lambda:ResearchDraft(task_id='t',plan_revision=0,findings=[],evidence_ids_used=['mem-2'])])
def test_memory_ids_rejected_in_authoritative_schema_fields(factory):
    with pytest.raises(ValidationError,match='Memory IDs are context only'):factory()


def test_plan_rejects_authority_id_in_evidence_registry(heat_task,heat_context):
    plan=responses(heat_task,heat_context);plan.questions[0].evidence_ids=['hpd-heat-hot-water']
    agents=ModelAgents(Mock(complete=Mock(return_value=plan)))
    with pytest.raises(ExecutionStopped,match='outside their evidence or memory registry'):agents.plan(heat_task,heat_context)
    q=ResearchQuestion(question_id='hint',prompt='Review a hint',memory_ids=['mem-2'])
    assert not q.evidence_ids and q.memory_ids==['mem-2']


def test_inconclusive_critic_executes_different_search_then_revises(heat_task,heat_context):
    seen=[]
    class Adapter:
        def complete(self,schema,payload):
            if schema is ResearchPlan:return responses(heat_task,heat_context)
            if schema is ResearchDraft:
                return ResearchDraft(task_id=heat_task.task_id,plan_revision=payload['plan']['revision'],findings=[])
            return CriticReport(task_id=heat_task.task_id,outcome='INCONCLUSIVE',issues=[
                CriticIssue(code='missing_legal_authority',message='Retrieve current agency guidance',recoverable=True,
                            follow_up_query='HPD heat hot water inspection complaint procedure',recommended_agent_or_tool='legal_search')])
    search=LegalSearchTool();original=search.search
    def capture(query,limit=5):seen.append(query);return original(query,limit)
    search.search=capture
    result=LegalResearchWorkflow(model_adapter=Adapter(),search_tool=search,max_revision_cycles=2).run(heat_task,heat_context)
    assert result.revision_cycles==1  # Identical follow-up cannot manufacture a second revision.
    assert len(seen)==2 and seen[0]!=seen[1]
    assert seen[1]=='HPD heat hot water inspection complaint procedure'
    assert len(result.review_history)==6 and result.review_history[0].outcome.value=='INCONCLUSIVE'
    assert result.critic_outcome.value=='INCONCLUSIVE'
    assert any(e['type']=='critic.follow_up' for e in result.activity_events)
    assert result.execution['model_calls']==6


def test_targeted_research_stops_within_revision_and_model_budget(heat_task,heat_context):
    class Adapter:
        count=0
        def complete(self,schema,payload):
            if schema is ResearchPlan:return responses(heat_task,heat_context)
            if schema is ResearchDraft:return ResearchDraft(task_id=heat_task.task_id,plan_revision=payload['plan']['revision'],findings=[])
            self.count+=1
            return CriticReport(task_id=heat_task.task_id,outcome='INCONCLUSIVE',issues=[CriticIssue(
                code='missing_legal_authority',message='Target next source',recoverable=True,
                follow_up_query='heat inspection authority '+str(self.count))])
    result=LegalResearchWorkflow(model_adapter=Adapter(),max_revision_cycles=2).run(heat_task,heat_context)
    assert result.revision_cycles==2 and result.execution['model_calls']==9
    assert result.tool_calls<=5
    limited=LegalResearchWorkflow(model_adapter=Adapter(),limits=ExecutionLimits(max_model_calls=4),max_revision_cycles=2).run(heat_task,heat_context)
    assert limited.execution['model_calls']==4 and limited.status.value=='inconclusive'
    assert limited.errors and limited.errors[0].code=='execution_stopped'


def test_external_fact_gap_and_blocked_do_not_trigger_legal_research_retry(heat_task,heat_context):
    class Adapter:
        def complete(self,schema,payload):
            if schema is ResearchPlan:return responses(heat_task,heat_context)
            if schema is ResearchDraft:return ResearchDraft(task_id=heat_task.task_id,plan_revision=0,findings=[])
            return CriticReport(task_id=heat_task.task_id,outcome='INCONCLUSIVE',issues=[CriticIssue(
                code='current_condition_unknown',message='Needs a new inspection',recommended_agent_or_tool='request_external')])
    result=LegalResearchWorkflow(model_adapter=Adapter()).run(heat_task,heat_context)
    assert result.revision_cycles==0 and result.execution['model_calls']==3
    heat_context.root_critic_outcome='BLOCKED'
    blocked=LegalResearchWorkflow(model_adapter=Adapter()).run(heat_task,heat_context)
    assert blocked.critic_outcome.value=='BLOCKED' and blocked.tool_calls==0 and blocked.execution['model_calls']==0


def test_synthetic_invalid_plan_is_rejected_without_laundering_memory_ids():
    from pathlib import Path
    fixture=json.loads((Path(__file__).parent/'fixtures/reference_domain_rejection.synthetic.json').read_text())
    with pytest.raises(ValidationError,match='Memory IDs are context only'):
        ResearchPlan.model_validate(fixture['plan'])
    with pytest.raises(ValidationError,match='Memory IDs are context only'):
        Finding.model_validate(fixture['finding'])


def test_official_excerpts_match_capture_and_hash():
    from pathlib import Path
    import hashlib
    root=Path(__file__).resolve().parents[1]
    snapshots=json.loads((root/'data/legal_authority_snapshots.json').read_text())
    sources={s.id:s for s in LegalSearchTool().sources}
    for snapshot in snapshots:
        source=sources[snapshot['authority_id']]
        assert source.excerpt==snapshot['excerpt']
        assert hashlib.sha256(source.excerpt.encode()).hexdigest()==source.excerpt_provenance['excerpt_sha256']
        assert source.excerpt_provenance['source_url']==snapshot['url']
        if 'normalized_page_text' in snapshot:assert source.excerpt in snapshot['normalized_page_text']
        assert not source.excerpt_provenance['historical_version_verified']


def test_relevance_keeps_contradictions_and_deduplicates_memory(heat_task,heat_context):
    from context import agent_context
    from models.reconciliation import ReconciliationResult,EvidenceConflict
    ids=[e.evidence_id for e in heat_context.evidence[:2]]
    heat_context.reconciliation=ReconciliationResult(accepted_ids=ids,conflicts=[EvidenceConflict(category='status_disagreement',evidence_ids=ids,explanation='Open and closed reports differ')])
    hint={'memory_id':'mem-2','summary':'Prior review gap','evidence_ids':[],'trust_label':'review_feedback_only'}
    heat_context.untrusted_memory=[hint,hint.copy()]
    payload=agent_context(heat_task,heat_context,max_bytes=16000)
    assert payload['reconciliation']['conflict_groups'][0]['evidence_ids']==sorted(ids)
    assert payload['reconciliation']['conflict_groups'][0]['pair_count']==1
    assert set(ids)<={e['evidence_id'] for e in payload['evidence']}
    assert len(payload['untrusted_memory'])==1
    assert 'mem-2' not in payload['reference_domains']['evidence_ids']


def test_schema_rejects_cross_domain_authority_and_record_ids():
    with pytest.raises(ValidationError,match='authority IDs cannot be factual evidence'):
        Finding(finding_id='f',issue='heat',summary='bad',evidence_ids=['hpd-heat-hot-water'])
    with pytest.raises(ValidationError,match='record IDs cannot be legal authority'):
        LegalConclusion(statement='bad',source_ids=['wvxf-dwi5:123'])


def test_valid_forward_dependencies_are_ordered_but_cycles_and_unknowns_stop(heat_task,heat_context):
    plan=ResearchPlan(task_id=heat_task.task_id,objective='ordered research',questions=[
        ResearchQuestion(question_id='review',prompt='Interpret source',dependencies=['law'],recommended_tool='evidence_review'),
        ResearchQuestion(question_id='law',prompt='Retrieve heat law',recommended_tool='legal_search')])
    agents=ModelAgents(Mock(complete=Mock(return_value=plan)))
    ordered=agents.plan(heat_task,heat_context)
    assert [q.question_id for q in ordered.questions]==['law','review']
    for dependency in ['review','not-a-task']:
        invalid=plan.model_copy(deep=True);invalid.questions[0].dependencies=[dependency]
        with pytest.raises(ExecutionStopped,match='acyclic'):
            ModelAgents(Mock(complete=Mock(return_value=invalid))).plan(heat_task,heat_context)


def test_unknown_dependencies_are_invalidated_before_context_reuse(heat_context):
    from reconciliation import reconcile_evidence,invalidate_findings
    finding=Finding(finding_id='bad',issue='heat',summary='Unknown source',evidence_ids=['unknown-record'])
    result=reconcile_evidence(heat_context.evidence,findings=[finding])
    assert 'bad' in result.invalidated_finding_ids
    assert not invalidate_findings([finding],result)[0].valid


def test_tampered_official_excerpt_is_rejected(tmp_path):
    from tools.legal_search import load_legal_sources
    source=next(s for s in LegalSearchTool().sources if s.id=='hpd-heat-hot-water').model_dump(mode='json')
    source['excerpt']+=' changed text'
    path=tmp_path/'catalog.json';path.write_text(json.dumps([source]))
    with pytest.raises(ValueError,match='excerpt hash mismatch'):load_legal_sources(str(path))
