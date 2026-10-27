"""Synthetic transport scenarios, plus separately labelled real-record replays."""
import json
from pathlib import Path
from urllib.parse import parse_qs,urlparse
from unittest.mock import Mock

import pytest
from address_investigation import building_where,investigate_address,parse_address
from agents.planner import plan_sources
from risk_reporting import write_risk_report
from tools.address_data import AddressDataProvider,DynamicZetarisProvider,DynamicNYCDevelopmentProvider,RecordedAddressProvider
from tools.execution import ExecutionLimits
from tools.source_registry import load_registry
from workflow import LegalResearchWorkflow


def building(**changes):
    row=dict(buildingid='123',bin='1000001',boroid='1',boro='MANHATTAN',block='5',lot='1',
        housenumber='1',lowhousenumber='1',highhousenumber='1',streetname='MOCK STREET',zip='10001',recordstatus='Active')
    row.update(changes);return row


def violation(number='1',**changes):
    row=dict(buildingid='123',bin='1000001',bbl='1000050001',housenumber='1',streetname='MOCK STREET',
        violationid=number,inspectiondate='2026-01-01T00:00:00.000',currentstatus='OPEN',novdescription='Synthetic maintenance record',apartment='',**{'class':'B'})
    row.update(changes);return row


class FixtureProvider(AddressDataProvider):
    name='mock';data_mode='mock'
    def __init__(self,rows=None,**kw):
        super().__init__(**kw);self.rows=rows or {};self.closed=False;self.seen=[]
    def _page(self,source,url):
        self.seen.append((source['key'],url))
        params=parse_qs(urlparse(url).query);offset=int(params['$offset'][0]);limit=int(params['$limit'][0])
        return self.rows.get(source['key'],[])[offset:offset+limit]
    def close(self):self.closed=True


@pytest.mark.parametrize('address,borough,code',[
    ('840 Second Avenue','Manhattan','1'),('88 East 163rd Street','Bronx','2'),
    ('100 Atlantic Avenue','Brooklyn','3'),('31-10 31st Avenue','Queens','4'),
    ('100 St Marks Place','Staten Island','5')])
def test_arbitrary_boroughs_not_fixed_zip(address,borough,code):
    request=parse_address(address,borough)
    where=building_where(load_registry()['hpd_buildings'],request)
    assert 'boroid = '+code in where
    assert 'zip' not in where.lower()
    assert request['original_input']==address


def test_ordinal_normalization_optional_unit_and_borough_conflict():
    request=parse_address('840 2nd Avenue, Manhattan, Apt 4B')
    assert request['normalized_address']=='840 2 AVE'
    assert request['unit']=='4B'
    with pytest.raises(ValueError):parse_address('1 Mock Street, Queens',borough='Brooklyn')


def test_missing_hpd_identity_is_unknown_and_no_downstream_queries():
    p=FixtureProvider()
    report=investigate_address(p,'999 Unknown Street',borough='Queens')
    assert report['identity']['verification_status']=='missing'
    assert not report['factual_findings']
    assert {key for key,_ in p.seen}=={'hpd_buildings'}
    assert report['legal_assessment']['status']=='not_performed_identity_unresolved'
    assert p.closed


def test_ambiguous_address_does_not_select_one_building():
    p=FixtureProvider({'hpd_buildings':[building(),building(buildingid='456',bin='1000002')]})
    report=investigate_address(p,'1 Mock Street',borough='Manhattan')
    assert report['identity']['verification_status']=='ambiguous'
    assert not report['factual_findings']


def test_bounded_identity_cannot_claim_uniqueness():
    p=FixtureProvider({'hpd_buildings':[building()]},page_size=1,max_pages=1)
    report=investigate_address(p,'1 Mock Street',borough='Manhattan')
    assert report['identity']['verification_status']=='ambiguous'


def test_distinct_same_day_violations_are_both_kept():
    p=FixtureProvider({'hpd_buildings':[building()],'hpd_violations':[violation('1'),violation('2',novdescription='A different real-world condition would be separate')]})
    report=investigate_address(p,'1 Mock Street',borough='Manhattan')
    assert len(report['evidence_audit'])==2
    assert not any(d['rule']=='R5' for d in report['record_decisions'])
    assert len(report['factual_findings'])==2


def test_same_day_violations_identical_apart_from_id_still_hit_r5():
    p=FixtureProvider({'hpd_buildings':[building()],'hpd_violations':[violation('1',ordernumber='10'),violation('2',ordernumber='20')]})
    report=investigate_address(p,'1 Mock Street',borough='Manhattan')
    assert any(d['rule']=='R5' for d in report['record_decisions'])
    assert len(report['factual_findings'])==1
    assert 'R5' in ' '.join(report['limitations'])


def test_cross_dataset_bin_conflict_cannot_support_a_fact():
    bad=dict(complaint_number='9',bin='1999999',house_number='1',house_street='MOCK STREET',status='OPEN')
    p=FixtureProvider({'hpd_buildings':[building()],'dob_complaints':[bad]})
    report=investigate_address(p,'1 Mock Street',borough='Manhattan')
    assert not report['factual_findings']
    assert report['board_update']['legal_record_matches'][0]['decision']=='rejected'


def test_complaint_is_not_a_violation_and_unit_scope_is_retained():
    complaint=dict(problem_id='5',building_id='123',bin='1000001',bbl='1000050001',house_number='1',street_name='MOCK STREET',received_date='2026-01-02',problem_status='CLOSED',major_category='HEAT',apartment='2')
    p=FixtureProvider({'hpd_buildings':[building()],'hpd_complaints':[complaint]})
    report=investigate_address(p,'1 Mock Street',borough='Manhattan',unit='2')
    fact=report['factual_findings'][0]
    assert fact['kind']=='complaint' and fact['scope']=='unit'
    assert 'does not establish a verified' in fact['why_it_matters']
    assert report['evidence_audit'][0]['status']=='CLOSED'


def test_pagination_exhaustion_and_truncation_are_explicit():
    source=load_registry()['hpd_violations']
    p=FixtureProvider({'hpd_violations':[violation(str(i)) for i in range(3)]},page_size=2,max_pages=2)
    result=p.fetch_where(source,'buildingid=123')
    assert result.complete and len(result.rows)==3 and len(result.pages)==2
    bounded=FixtureProvider({'hpd_violations':[violation(str(i)) for i in range(4)]},page_size=2,max_pages=1).fetch_where(source,'buildingid=123')
    assert bounded.status=='bounded' and not bounded.complete


def test_unstable_duplicate_pagination_fails_closed():
    class Repeating(FixtureProvider):
        def _page(self,source,url):return [violation('1')]
    p=Repeating(page_size=1,max_pages=2)
    result=p.fetch_where(load_registry()['hpd_violations'],'1=1')
    assert result.status=='unavailable' and not result.complete


def test_shared_budget_stops_additional_source_queries():
    p=FixtureProvider(max_requests=1)
    p.fetch_where(load_registry()['hpd_buildings'],'1=1')
    result=p.fetch_where(load_registry()['dob_violations'],'1=1')
    assert result.status=='budget_exhausted' and p.requests==1


def test_missing_source_never_becomes_clean_history_or_leaks_error_body():
    class Broken(FixtureProvider):
        def _page(self,source,url):raise RuntimeError('mock-secret-response-body')
    p=Broken()
    report=investigate_address(p,'1 Mock Street',borough='Manhattan')
    assert report['retrieval_status']=='identity_unresolved'
    assert 'mock-secret-response-body' not in json.dumps(report)


def test_legal_budget_uncertainty_does_not_suppress_verified_facts(tmp_path):
    p=FixtureProvider({'hpd_buildings':[building()],'hpd_violations':[violation()]})
    workflow=LegalResearchWorkflow(reasoning_mode='demo_deterministic',limits=ExecutionLimits(max_tool_calls=0))
    report=investigate_address(p,'1 Mock Street',borough='Manhattan',workflow=workflow)
    assert report['legal_assessment']['status']=='inconclusive'
    assert report['factual_findings']
    path=write_risk_report(report,tmp_path)
    text=path.read_text()
    assert 'data.cityofnewyork.us/resource/wvxf-dwi5' in text
    assert 'Synthetic maintenance record' in text
    assert 'not proof that no issue exists' in text


def test_temporary_zetaris_tables_have_upstream_filters_and_bounded_cleanup():
    request=Mock(side_effect=[{'headers':['name'],'data':[]},{}, {}, {'headers':['violationid'],'data':[['1']]}, {}])
    p=DynamicZetarisProvider(request,page_size=2,max_pages=1,max_requests=1)
    result=p.fetch_where(load_registry()['hpd_violations'],'buildingid = 123')
    p.close();p.close()
    sql=[c.args[2]['sql'] for c in request.call_args_list]
    assert result.provider=='zetaris'
    assert 'resource/wvxf-dwi5.json?' in sql[2] and '%24where=' in sql[2]
    assert 'WHERE' not in sql[3]
    assert sql[-1]=='DROP LIGHTNING DATABASE '+p.namespace
    assert len(request.call_args_list)==5


def test_explicit_dynamic_fallback_never_claims_zetaris():
    provider=DynamicNYCDevelopmentProvider(transport=Mock(return_value=[violation()]))
    result=provider.fetch_where(load_registry()['hpd_violations'],'buildingid = 123')
    assert result.provider=='nyc_open_data_development_fallback'


def test_planner_selects_relevant_sources_and_identity_first():
    plan=plan_sources(load_registry(),['habitability'])
    assert plan['selected_sources'][0]=='hpd_buildings'
    assert 'hpd_complaints' in plan['selected_sources']
    assert 'dob_jobs' not in plan['selected_sources']
    with pytest.raises(ValueError):plan_sources(load_registry(),['invented_category'])


def test_court_statistics_are_not_address_specific_cases():
    sources=load_registry()
    assert sources['webcivil_local']['capability']=='manual_only'
    assert sources['webcivil_supreme']['capability']=='manual_only'
    p=FixtureProvider({'hpd_buildings':[building()]})
    report=investigate_address(p,'1 Mock Street',borough='Manhattan')
    assert all(c['status']=='manual_only' for c in report['coverage'] if c['source'].startswith('webcivil'))


def test_recorded_multi_source_replay_never_queries_a_new_address():
    path=Path(__file__).parent/'fixtures/address_replay.synthetic.json'
    capture=json.loads(path.read_text())
    provider=RecordedAddressProvider(capture)
    report=investigate_address(provider,'1 Mock Street',borough='Manhattan',goals=['habitability'])
    assert report['data_mode']=='recorded_replay'
    assert report['identity']['identifiers']['hpd_building_id']=='123'
    assert report['factual_findings']
    assert all(not e.get('fresh_network_request',False) for e in provider.events)
    other=investigate_address(RecordedAddressProvider(capture),'999 Unknown Street',borough='Queens')
    assert not other['factual_findings'] and other['identity']['verification_status']=='missing'


def test_null_agency_id_is_not_converted_to_invented_none_id():
    p=FixtureProvider({'hpd_violations':[violation(None)]})
    result=p.fetch_where(load_registry()['hpd_violations'],'1=1')
    assert result.status=='unavailable' and not result.rows
    assert result.reason=='agency_identifier_missing'


def test_namespace_guard_prevents_uncontrolled_accumulation():
    request=Mock(return_value={'headers':['name'],'data':[[f'signsafe_run_{i:016x}'] for i in range(3)]})
    p=DynamicZetarisProvider(request)
    result=p.fetch_where(load_registry()['hpd_violations'],'1=1')
    assert result.status=='unavailable'
    assert request.call_count==1
    assert not p.created


def test_matcher_followup_is_bounded_and_unchanged_results_do_not_force_approval():
    p=FixtureProvider({'hpd_buildings':[building()],'hpd_violations':[violation('1',bbl='1000050002')]})
    report=investigate_address(p,'1 Mock Street',borough='Manhattan',goals=['habitability'],max_corrections=99)
    follow=[e for e in report['activity_log'] if e['action']=='matcher_follow_up']
    assert len(follow)==1 and follow[0]['unchanged_results_stop']
    assert not report['factual_findings']


def test_changed_followup_requires_new_matcher_and_root_review():
    class Correcting(FixtureProvider):
        def _page(self,source,url):
            where=parse_qs(urlparse(url).query)['$where'][0]
            if source['key']=='hpd_violations' and ' AND ' in where:return [violation('2')]
            return super()._page(source,url)
    p=Correcting({'hpd_buildings':[building()],'hpd_violations':[violation('1',bbl='1000050002')]})
    report=investigate_address(p,'1 Mock Street',borough='Manhattan',goals=['habitability'])
    assert [f['record_id'] for f in report['factual_findings']]==['2']
    decisions={d['record_id']:d['decision'] for d in report['record_decisions']}
    assert decisions['wvxf-dwi5:1']=='reject' and decisions['wvxf-dwi5:2']=='accept'


def test_multiple_buildings_on_lot_do_not_expand_building_scope():
    class MultiLot(FixtureProvider):
        def _page(self,source,url):
            where=parse_qs(urlparse(url).query)['$where'][0]
            if source['key']=='hpd_buildings' and 'block = ' in where:
                return [building(),building(buildingid='456',bin='1000002',housenumber='2')]
            return super()._page(source,url)
    p=MultiLot({'hpd_buildings':[building()]})
    report=investigate_address(p,'1 Mock Street',borough='Manhattan')
    assert report['identity']['verification_status']=='verified'
    assert report['lot_context']['building_ids']==['123','456']
    assert 'property-scoped' in report['lot_context']['limitation']


@pytest.mark.parametrize('code,borough', [('1','Manhattan'),('2','Bronx'),('3','Brooklyn'),('4','Queens'),('5','Staten Island')])
def test_synthetic_identity_resolution_across_all_five_boroughs(code,borough):
    """Fictional transport rows exercise borough handling, not claimed live data."""
    provider=FixtureProvider({'hpd_buildings':[building(boroid=code,boro=borough.upper(),bin=code+'000001')]})
    report=investigate_address(provider,'1 Mock Street',borough=borough,goals=['property_identity'])
    assert report['identity']['verification_status']=='verified'
    assert report['identity']['borough'].casefold()==borough.casefold()
    assert report['identity']['identifiers']['bin']==code+'000001'
    assert provider.name=='mock'


def test_expanded_retrieval_preserves_original_ids_and_excludes_held_dependencies():
    legacy=investigate_address(FixtureProvider({'hpd_buildings':[building()],'hpd_violations':[violation('one')]}),'1 Mock Street',borough='Manhattan')
    current=investigate_address(FixtureProvider({'hpd_buildings':[building()],
        'hpd_violations':[violation('one'),violation('two',bin='1000002',buildingid='999')]}),'1 Mock Street',borough='Manhattan')
    original={e['evidence_id'] for e in legacy['board_update']['source_evidence']}
    expanded={e['evidence_id'] for e in current['evidence_audit']}
    assert original <= expanded
    assert current['identity']['identifiers']['bin']=='1000001'
    held={m['evidence_id'] for m in current['board_update']['legal_record_matches'] if m['decision']!='accepted'}
    assert held
    assert all(not set(f['evidence_ids'])&held for f in current['factual_findings'])


def test_explicit_unit_conflict_and_partial_street_abbreviations():
    with pytest.raises(ValueError):parse_address('1 Mock Street Apt 2',borough='Manhattan',unit='3')
    where=building_where(load_registry()['hpd_buildings'],parse_address('10 St Marks Place',borough='Manhattan'))
    assert 'ST MARKS PLACE' in where


def test_disabled_source_stays_in_catalog_but_is_not_selected():
    registry=load_registry();registry['dob_jobs']['enabled']=False
    plan=plan_sources(registry)
    assert 'dob_jobs' not in plan['selected_sources']


def test_management_contact_is_held_when_its_registration_parent_is_rejected():
    registration=dict(building(),registrationid='200',bin='1999999')
    contact=dict(registrationcontactid='300',registrationid='200',type='CorporateOwner',corporationname='Synthetic Company')
    p=FixtureProvider({'hpd_buildings':[building()],'hpd_registrations':[registration],'registration_contacts':[contact]})
    report=investigate_address(p,'1 Mock Street',borough='Manhattan',goals=['property_identity'])
    assert not report['factual_findings']
    held={m['evidence_id']:m for m in report['board_update']['legal_record_matches']}
    assert held['tesw-yqqr:200']['decision']=='rejected'
    assert held['feu5-w2e2:300']['decision']=='quarantined'


def test_address_pipeline_invokes_all_model_roles_without_live_inference_claim():
    from models.schemas import ResearchPlan,ResearchDraft,CriticReport
    class StructuredFixtureModel:
        def __init__(self):self.roles=[]
        def complete(self,schema,payload):
            self.roles.append(payload['role'])
            if schema is ResearchPlan:
                return ResearchPlan(task_id=payload['task_id'],objective='Fixture model integration',questions=[
                    {'question_id':'q1','prompt':'Check maintenance authority','focus_topics':['maintenance']}])
            if schema is ResearchDraft:
                return ResearchDraft(task_id=payload['task_id'],plan_revision=0,findings=[],caveats=['Fixture response; no live inference.'])
            return CriticReport(task_id=payload['task_id'],outcome='INCONCLUSIVE')
    model=StructuredFixtureModel()
    provider=FixtureProvider({'hpd_buildings':[building()],'hpd_violations':[violation()]})
    report=investigate_address(provider,'1 Mock Street',borough='Manhattan',goals=['habitability'],
        workflow=LegalResearchWorkflow(model_adapter=model,max_revision_cycles=0))
    assert model.roles==['planner','researcher','independent_critic']
    assert report['execution']['model_calls']==3
    assert report['data_mode']=='mock'
    assert report['legal_assessment']['reasoning_mode']=='llm:injected'
    assert provider.closed
    events=report['activity_events']
    assert len({e['run_id'] for e in events})==1
    assert len({e['task_id'] for e in events})==1
    assert {'investigation.started','identity.decided','source.selected','critic.decision','investigation.finished'}<={e['type'] for e in events}
