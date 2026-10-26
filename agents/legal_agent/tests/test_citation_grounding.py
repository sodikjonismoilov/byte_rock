import json
from datetime import date
import pytest
from pydantic import ValidationError
from citations import selection_schema,selected_draft,ground_draft,assess_claim,audit_claims
from models.schemas import LegalConclusion,ResearchDraft,Finding,LegalSourceHit
from tools.legal_search import LegalSearchTool
from agents.critic import critique_draft


def registry():return {s.id:s for s in LegalSearchTool().sources}


def claim_for(sid='hpd-heat-hot-water',scope='current_guidance'):
    source=registry()[sid]
    prefix='Current official guidance states: ' if scope=='current_guidance' else 'The provided statutory excerpt states: '
    return LegalConclusion(statement=prefix+source.excerpt,source_ids=[sid],claim_scope=scope,support_quotes={sid:source.excerpt})


def draft_for(claim):return ResearchDraft(task_id='t',plan_revision=0,findings=[Finding(finding_id='f',issue='heat',summary='Source text only',legal_conclusions=[claim])])


def test_model_selects_registry_id_without_generating_metadata():
    source=registry()['hpd-heat-hot-water'];wire=selection_schema([source.model_dump(mode='json')])
    value={'task_id':'t','findings':[{'finding_id':'f','issue':'heat','summary':'Source text','legal_conclusions':[
        {'statement':'Current official guidance states: '+source.excerpt,'claim_scope':'current_guidance',
         'citations':[{'authority_id':source.id,'supporting_quote':source.excerpt}]}]}]}
    draft=selected_draft(wire.model_validate(value))
    result=ground_draft(draft,{source.id:source},as_of=date.today())
    claim=result.findings[0].legal_conclusions[0]
    assert claim.identifiers==[source.identifier]
    assert claim.citations[0]['title']==source.title and claim.citations[0]['source_url']==source.url
    assert claim.citations[0]['provenance']==source.excerpt_provenance
    assert assess_claim(claim,{source.id:source},as_of=date.today())['claim_support_verified']
    value['findings'][0]['legal_conclusions'][0]['identifiers']=['invented']
    with pytest.raises(ValidationError):wire.model_validate(value)


@pytest.mark.parametrize('sid',['unknown','dob-boilers','mem-2','wvxf-dwi5:123'])
def test_wire_rejects_unknown_unretrieved_or_wrong_domain_ids(sid):
    source=registry()['hpd-heat-hot-water'];wire=selection_schema([source.model_dump(mode='json')])
    with pytest.raises(ValidationError):wire.model_validate({'task_id':'t','findings':[{'finding_id':'f','issue':'heat','summary':'bad',
        'legal_conclusions':[{'statement':'bad','claim_scope':'current_guidance','citations':[{'authority_id':sid,'supporting_quote':'bad'}]}]}]})


def test_deterministic_metadata_overwrites_generated_strings_but_not_support():
    claim=claim_for();claim.identifiers=['HPD Building ID 1571'];claim.citations=[{'title':'fake','source_url':'https://fake.invalid'}]
    claim.statement='Current official guidance states: HPD determines all litigation procedures.'
    result=ground_draft(draft_for(claim),registry(),as_of=date.today()).findings[0].legal_conclusions[0]
    assert result.identifiers==[registry()['hpd-heat-hot-water'].identifier]
    assert result.citations[0]['title']!='fake'
    assert not result.supported and 'wrong_topic_source' in result.grounding_errors


@pytest.mark.parametrize('sid,statement',[
 ('hpd-heat-hot-water','Current official guidance states: HPD initiates housing court litigation.'),
 ('dob-boilers','Current official guidance states: DOB issues all demolition permits for construction.')])
def test_wrong_topic_source_is_rejected_despite_valid_identity(sid,statement):
    claim=claim_for(sid);claim.statement=statement
    result=assess_claim(claim,registry(),as_of=date.today())
    assert result['source_identity_valid'] and not result['claim_support_verified']
    assert 'wrong_topic_source' in result['errors']


def test_plausible_paraphrase_is_not_independently_verified_entailment():
    claim=claim_for();claim.statement='Current official guidance states: This property violates the heat law.'
    result=assess_claim(claim,registry(),as_of=date.today())
    assert result['source_identity_valid'] and not result['claim_support_verified']
    assert 'claim_not_entailed_by_exact_excerpt' in result['errors']


def test_current_guidance_cannot_be_relabelled_as_statute_or_historical_liability():
    claim=claim_for()
    assert assess_claim(claim,registry(),as_of=date.today())['claim_support_verified']
    claim.claim_scope='statute_text'
    assert 'authority_type_mismatch' in assess_claim(claim,registry())['errors']
    claim.claim_scope='historical_application';claim.statement='The landlord was liable in 2009.'
    result=assess_claim(claim,registry())
    assert not result['claim_support_verified'] and not result['historical_version_verified']
    assert 'historical_applicability_unverified' in result['errors']


def test_statute_text_quote_is_not_verified_historical_application():
    claim=claim_for('rpl-235-b','statute_text')
    result=assess_claim(claim,registry(),as_of=date.today())
    assert result['claim_support_verified'] and not result['historical_version_verified']


def test_identity_and_support_counts_are_separate():
    valid=claim_for();bad=claim_for();bad.statement='Current official guidance states: The property is safe.'
    draft=ResearchDraft(task_id='t',plan_revision=0,findings=[Finding(finding_id='f',issue='heat',summary='Mixed claims',legal_conclusions=[valid,bad])])
    ground_draft(draft,registry(),as_of=date.today())
    rows,metrics=audit_claims(draft.findings,registry(),set(),as_of=date.today())
    assert metrics=={'cited_claims':2,'claims_with_valid_source_identity':2,'claims_with_verified_support':1}
    assert sum(r['claim_support_verified'] for r in rows)==1


def test_critic_recomputes_support_instead_of_trusting_grounded_flag(heat_task,heat_context):
    source=registry()['hpd-heat-hot-water'];claim=claim_for()
    draft=ResearchDraft(task_id=heat_task.task_id,plan_revision=0,evidence_ids_used=heat_task.evidence_ids,
        retrieved_sources=[LegalSourceHit(source=source,score=1)],findings=[Finding(finding_id='f',issue='heat',summary='Claim',
        evidence_ids=[heat_context.evidence[0].evidence_id],evidence_kinds=[heat_context.evidence[0].kind],legal_conclusions=[claim])])
    ground_draft(draft,registry(),as_of=heat_context.as_of)
    claim=draft.findings[0].legal_conclusions[0]
    claim.statement='Current official guidance states: HPD controls court litigation.';claim.supported=True;claim.grounding_errors=[]
    result=critique_draft(heat_task,heat_context,draft)
    assert result.outcome.value!='PASS'
    assert {'wrong_topic_source','claim_support_unverified'}<={i.code for i in result.issues}


def test_topic_selection_does_not_substitute_unrelated_guidance():
    search=LegalSearchTool()
    assert 'hpd-heat-hot-water' not in {h.source.id for h in search.search('housing court litigation eviction procedure',limit=20)}
    assert 'dob-boilers' not in {h.source.id for h in search.search('demolition permit construction rules',limit=20)}
    assert 'dob-boilers' in {h.source.id for h in search.search('boiler inspection work permit',limit=20)}


def test_historical_gap_does_not_repeat_catalog_search(heat_task,heat_context):
    from agents.model_agents import ModelAgents
    from models.schemas import CriticReport,CriticIssue
    from tools.execution import ExecutionBudget,ReadOnlySearch
    from unittest.mock import Mock
    source=registry()['rpl-235-b'];agents=ModelAgents(Mock())
    agents.retrieved={source.id:LegalSourceHit(source=source,score=1)}
    budget=ExecutionBudget();search=ReadOnlySearch(LegalSearchTool(),budget.limits,budget)
    for query in ['Retrieve operative version as of 2009','Find historical law effective on the incident date']:
        feedback=CriticReport(task_id=heat_task.task_id,outcome='INCONCLUSIVE',issues=[CriticIssue(
            code='VERSION_UNVERIFIED',message='Historical applicability unknown',follow_up_query=query,recoverable=True)])
        assert not agents.queue_followups(heat_task,heat_context,feedback,search,1)
    assert search.calls==0 and agents.external_limits
    assert any(e['type']=='research.external_gap' for e in budget.trace.events)


def test_critic_payload_reserves_space_without_dropping_claims_or_uncertainty(heat_task,heat_context,monkeypatch):
    from agents.model_agents import ModelAgents
    from models.schemas import CriticReport
    from unittest.mock import Mock
    monkeypatch.setenv('LEGAL_MODEL_PAYLOAD_MAX_BYTES','10000')
    monkeypatch.setenv('LEGAL_CONTEXT_MAX_BYTES','14000')
    monkeypatch.setenv('LEGAL_CONTEXT_MAX_TOKENS','14000')
    for evidence in heat_context.evidence:evidence.description+=' filler'*180
    heat_context.unresolved_questions=['Condition remains unknown.']
    source=registry()['hpd-heat-hot-water'];draft=draft_for(claim_for());draft.task_id=heat_task.task_id
    draft.retrieved_sources=[LegalSourceHit(source=source,score=1)]
    adapter=Mock();adapter.complete.return_value=CriticReport(task_id=heat_task.task_id,outcome='INCONCLUSIVE')
    ModelAgents(adapter).critique(heat_task,heat_context,draft,None)
    payload=adapter.complete.call_args.args[1]
    from tools.llm import request_size
    assert request_size(CriticReport,payload)<=10000
    assert len(payload['draft']['findings'])==1 and payload['unresolved_questions']
    assert payload['selection']['omitted_evidence_ids']
    assert not payload['prior_findings']


def test_extra_valid_source_does_not_automatically_support_the_same_claim():
    sources=registry();claim=claim_for()
    claim.source_ids.append('dob-boilers')
    claim.support_quotes['dob-boilers']=sources['dob-boilers'].excerpt
    result=assess_claim(claim,sources,as_of=date.today())
    assert result['source_identity_valid'] and not result['claim_support_verified']


def test_canonical_metadata_tampering_is_independently_rejected(heat_task,heat_context):
    source=registry()['hpd-heat-hot-water'];claim=claim_for()
    draft=ResearchDraft(task_id=heat_task.task_id,plan_revision=0,evidence_ids_used=heat_task.evidence_ids,
        retrieved_sources=[LegalSourceHit(source=source,score=1)],findings=[Finding(finding_id='f',issue='heat',summary='Source text',
        evidence_ids=[heat_context.evidence[0].evidence_id],evidence_kinds=[heat_context.evidence[0].kind],legal_conclusions=[claim])])
    ground_draft(draft,registry(),as_of=heat_context.as_of)
    draft.findings[0].legal_conclusions[0].citations[0]['source_url']='https://wrong.invalid'
    result=critique_draft(heat_task,heat_context,draft)
    assert 'citation_metadata_mismatch' in {i.code for i in result.issues}
    assert result.outcome.value!='PASS'


def test_selected_quote_formats_attribution_without_laundering_a_false_claim():
    source=registry()['hpd-heat-hot-water'];wire=selection_schema([source.model_dump(mode='json')])
    value={'task_id':'t','findings':[{'finding_id':'f','issue':'heat','summary':'Source text only','legal_conclusions':[
        {'claim_scope':'current_guidance','citations':[{'authority_id':source.id,'supporting_quote':source.excerpt}]}]}]}
    result=ground_draft(selected_draft(wire.model_validate(value)),{source.id:source},as_of=date.today())
    claim=result.findings[0].legal_conclusions[0]
    assert claim.statement=='Current official guidance states: '+source.excerpt
    assert claim.supported
    value['findings'][0]['legal_conclusions'][0]['statement']='The landlord was liable in 2009.'
    result=ground_draft(selected_draft(wire.model_validate(value)),{source.id:source},as_of=date.today())
    assert result.findings[0].legal_conclusions[0].statement=='The landlord was liable in 2009.'
    assert not result.findings[0].legal_conclusions[0].supported


def test_model_plan_orders_dependencies_and_rejects_cycles(heat_task,heat_context):
    from agents.model_agents import ModelAgents
    from models.schemas import ResearchPlan,ResearchQuestion
    from tools.execution import ExecutionStopped
    class Adapter:
        def complete(self,schema,payload):return plan.model_copy(deep=True)
    lookup=ResearchQuestion(question_id='lookup',prompt='heat duty text',recommended_tool='legal_search')
    interpretation=ResearchQuestion(question_id='interpret',prompt='interpret accepted heat records',recommended_tool='evidence_review',dependencies=['lookup'])
    plan=ResearchPlan(task_id=heat_task.task_id,objective='Verify source before interpretation',questions=[interpretation,lookup])
    ordered=ModelAgents(Adapter()).plan(heat_task,heat_context)
    assert [q.question_id for q in ordered.questions]==['lookup','interpret']
    plan.questions[1].dependencies=['interpret']
    with pytest.raises(ExecutionStopped,match='acyclic'):
        ModelAgents(Adapter()).plan(heat_task,heat_context)
