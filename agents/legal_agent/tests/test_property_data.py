"""Provider transport mocks and explicitly synthetic replay-boundary scenarios."""
from datetime import UTC, datetime
import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from models.schemas import InvestigationContext, LegalIssueTask
from tools.property_data import BUILDINGS, VIOLATIONS, NYCOpenDataDevelopmentProvider, RecordBatch, ZetarisPropertyProvider
from tools.zetaris import map_hpd_building, map_hpd_rows
from workflow import LegalResearchWorkflow
from reporting import write_report


def provider(request):
    return ZetarisPropertyProvider(request, source='mock_hpd', buildings_table='buildings', violations_table='violations')


def discovery():
    return {'headers':['table_identifier'], 'data':[['mock_hpd.buildings'],['mock_hpd.violations']]}


def test_zetaris_requires_actual_table_discovery():
    with pytest.raises(ValueError):
        provider(Mock(return_value={'headers':['table_identifier'],'data':[]}))


def test_query_preserves_dataset_and_engine_and_cannot_interpolate_address():
    request = Mock(side_effect=[discovery(), {'headers':['buildingid','violationid'],'data':[['123','456']]}])
    data = ZetarisPropertyProvider(request, source='mock_hpd', buildings_table='buildings', violations_table='violations', engine_id='mock-engine')
    batch = data.fetch(VIOLATIONS, building_id='123', limit=20)
    assert batch.provider == 'zetaris' and batch.dataset == VIOLATIONS
    assert batch.rows == [{'buildingid':'123','violationid':'456'}]
    assert request.call_args.args[2]['engineId'] == 'mock-engine'
    with pytest.raises(ValueError):
        data.fetch(VIOLATIONS, building_id="1' OR 1=1 --")
    assert request.call_count == 2


def test_failed_zetaris_query_never_silently_falls_back():
    request = Mock(side_effect=[discovery(), ConnectionError('mock outage')])
    data = provider(request)
    with pytest.raises(ConnectionError):
        data.fetch(BUILDINGS)


def test_explicit_development_provider_is_labelled_at_evidence_boundary():
    row = {'violationid':'mock-1','buildingid':'123','housenumber':'1','streetname':'MOCK ST',
           'inspectiondate':None,'currentstatus':'OPEN','novdescription':'Synthetic record', 'class':'A'}
    transport = Mock(return_value=[row])
    data = NYCOpenDataDevelopmentProvider(transport=transport)
    batch = data.fetch(VIOLATIONS, building_id='123', limit=10)
    record = map_hpd_rows(batch.rows,retrieved_at=batch.retrieved_at,provider=batch.provider)[0]
    assert 'DEVELOPMENT FALLBACK' in record.source
    assert record.metadata['data_provider'] == 'nyc_open_data_development_fallback'
    assert 'via Zetaris' not in record.source
    assert 'buildingid=123' in transport.call_args.args[0]


def test_building_files_identity_provenance_and_bbl_derivation():
    row = {'buildingid':'123','bin':'1000001','boroid':'1','block':'20','lot':'5',
           'housenumber':'1','streetname':'MOCK ST','boro':'MANHATTAN','zip':'10017','recordstatus':'Active'}
    candidate, record = map_hpd_building(row,retrieved_at=datetime.now(UTC))
    assert record.metadata['bbl'] == '1000200005'
    assert record.metadata['bbl_derivation'] == {'boroid':'1','block':'20','lot':'5'}
    assert candidate.candidate_id == 'kj4p-ruqc:123'
    assert all(i.record_id == '123' and not i.fictional for i in candidate.identifiers)
    assert record.status == 'Active' and record.date is None


def test_synthetic_hpd_replay_excludes_every_held_dependency(tmp_path):
    """Synthetic rows mapped through the same replay/identity contracts; no live data."""
    at=datetime(2026,1,1,tzinfo=UTC)
    candidate,building=map_hpd_building({'buildingid':'123','bin':'1000001','boroid':'1','block':'5','lot':'1',
        'housenumber':'1','streetname':'MOCK ST','boro':'MANHATTAN','recordstatus':'Active'},retrieved_at=at,provider='synthetic-fixture')
    rows=[{'violationid':'mock-good','buildingid':'123','bin':'1000001','bbl':'1000050001','housenumber':'1','streetname':'MOCK ST',
        'inspectiondate':'2009-01-01','currentstatus':'OPEN','novdescription':'Synthetic maintenance record','class':'B'},
        {'violationid':'mock-held','buildingid':'999','bin':'1000002','housenumber':'2','streetname':'OTHER ST',
        'inspectiondate':'2009-01-01','currentstatus':'OPEN','novdescription':'Synthetic conflicting property','class':'B'}]
    evidence=[building,*map_hpd_rows(rows,retrieved_at=at,provider='synthetic-fixture')]
    context=InvestigationContext(data_mode='recorded_replay',data_provider='synthetic-fixture',identity_candidates=[candidate],evidence=evidence)
    task=LegalIssueTask(task_id='synthetic-replay',question='Maintenance legal duties',building={'address':'1 Mock Street','borough':'Manhattan'})
    result=LegalResearchWorkflow(reasoning_mode='demo_deterministic').run(task,context)
    assert result.identity.verification_status=='verified'
    assert result.identity.identifiers['hpd_building_id']=='123'
    assert result.status.value=='inconclusive'
    held=set(result.reconciliation.rejected_ids+result.reconciliation.quarantined_ids)
    assert held
    pack=write_report(result,context.evidence,tmp_path)
    assert not pack['board_update']['legal_findings']
    assert pack['board_update']['withheld_finding_ids']
    for finding in pack['board_update']['legal_findings']:
        assert not set(finding['evidence_ids'])&held
    assert all(e.metadata['data_provider']=='synthetic-fixture' for e in context.evidence)


def onboarding_module():
    path = Path(__file__).resolve().parents[3]/'scripts'/'onboard_hpd.py'
    spec = importlib.util.spec_from_file_location('signsafe_onboarding_test',path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_current_registration_syntax_and_untrusted_identifier_rejection():
    module = onboarding_module()
    statements = module.onboarding_statements('mock_hpd')
    assert 'CREATE LIGHTNING REST TABLE' in statements[1][1]
    assert 'kj4p-ruqc.json' in statements[1][1]
    assert 'wvxf-dwi5.json' in statements[2][1]
    assert 'REGISTER REST' not in str(statements)
    with pytest.raises(ValueError):
        module.onboarding_statements('x; DROP TABLE victim')


def test_onboarding_preserves_existing_tables_and_requires_rows():
    module = onboarding_module()
    tables = {'headers':['table_identifier'],'data':[['mock_hpd.hpd_buildings'],['mock_hpd.hpd_violations']]}
    request = Mock(side_effect=[{'headers':['name'],'data':[['mock_hpd']]},tables,tables,
                               {'headers':['buildingid'],'data':[['123']]}, {'headers':['violationid'],'data':[['456']]}])
    capture = module.onboard(request,'mock_hpd')
    assert [e['status'] for e in capture['attempts']][-2:] == ['row_verified','row_verified']
    assert all(not c.args[2]['sql'].startswith(('CREATE','DROP','ALTER')) for c in request.call_args_list)


def test_coordinator_runs_development_provider_without_changing_agents(tmp_path):
    """Explicitly synthetic provider scenario, not a live API test."""
    from investigate_property import investigate_property
    class MockDevelopmentProvider:
        name = 'nyc_open_data_development_fallback'
        def fetch(self,dataset,*,building_id=None,limit=200):
            building = {'buildingid':'123','bin':'1000001','boroid':'1','block':'20','lot':'5',
                        'housenumber':'1','streetname':'MOCK ST','boro':'MANHATTAN','zip':'10017','recordstatus':'Active'}
            violation = dict(building,violationid='mock-1',bbl='1000200005',apartment='',
                inspectiondate='2026-01-01',currentstatus='OPEN',novdescription='Synthetic maintenance record',**{'class':'A'})
            return RecordBatch(dataset,self.name,[building if dataset == BUILDINGS else violation],datetime.now(UTC),'mock transport only')
    result, pack = investigate_property(MockDevelopmentProvider(),tmp_path)
    assert result.data_mode == 'development_fallback'
    assert result.data_provider == 'nyc_open_data_development_fallback'
    assert result.identity.verification_status == 'verified'
    assert 'DEVELOPMENT FALLBACK' in pack['board_update']['source_evidence'][0]['source']
    assert 'data-layer requirement' in ' '.join(result.caveats)
    assert result.reconciliation.accepted_ids == ['wvxf-dwi5:mock-1']
