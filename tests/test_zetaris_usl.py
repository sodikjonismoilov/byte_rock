"""Support-script unit tests: mock SQL transport, never claimed live receipts."""
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock
import pytest
from scripts.verify_zetaris_usl import identifiers,render,source_statements,run,safe_error


def transport(fail_activation=False,missing_schema=False):
    calls=[]
    def request(path,method,body,timeout):
        sql=body['sql'];calls.append(sql)
        if sql.startswith('SHOW NAMESPACES'):return {'headers':['name'],'data':[]}
        if sql=='SHOW LIGHTNING DATABASES':return {'headers':['name'],'data':[]}
        if sql.startswith('DESCRIBE'):
            columns='violationid buildingid bin bbl boro block lot inspectiondate currentstatus' if 'hpd_violations' in sql else 'permit_si_no bin__ borough block lot issuance_date permit_status' if 'dob_permits' in sql else 'ticket_number violation_location_borough violation_location_block_no violation_location_lot_no violation_date hearing_status'
            return {'headers':['col_name','data_type'],'data':[[c,'string'] for c in (columns.split() if not missing_schema else ['wrong'])]}
        if sql.startswith('ACTIVATE') and fail_activation:raise RuntimeError('fixture-private-key activation rejected')
        if sql.startswith(('CREATE','COMPILE','ACTIVATE','REGISTER','LOAD')):return {'headers':[],'data':[]}
        return {'headers':['mock_count'],'data':[['1']]}
    return request,calls


def test_owned_identifiers_and_static_templates():
    with pytest.raises(ValueError):identifiers('team_global','x.y')
    with pytest.raises(ValueError):identifiers('signsafe_usl_test','x.y;DROP TABLE victim')
    values=identifiers('signsafe_usl_test','mock_hpd.hpd_violations')
    assert '${' not in render('activate.sql',values)
    assert 'UNION ALL' in render('activate.sql',values) and ' JOIN ' not in render('activate.sql',values)
    assert 'api_key' not in str(source_statements(values['source_db'])).lower()
    assert '%24limit=20' in source_statements(values['source_db'])[1]


def test_success_requires_actual_activation_queries_and_dq_execution():
    request,calls=transport();result=run(request,identifiers('signsafe_usl_test','mock_hpd.hpd_violations'))
    assert result['status']=='PASS' and result['compiled'] and result['activated']
    assert result['usl_queries_ok']==3 and result['dq_registered'] and result['dq_executed']
    compile_sql=next(sql for sql in calls if sql.startswith('COMPILE'))
    assert 'CREATE TABLE events' in compile_sql
    assert len([s for s in result['steps'] if s['phase']=='exploration'])==6
    assert len(result['steps'])<=40


def test_failed_activation_remains_partial_and_sanitizes_errors(monkeypatch):
    monkeypatch.setenv('ZETARIS_API_KEY','fixture-private-key')
    request,calls=transport(fail_activation=True)
    result=run(request,identifiers('signsafe_usl_test','mock_hpd.hpd_violations'))
    assert result['status']=='PARTIAL' and result['compiled'] and not result['activated']
    assert not result['dq_executed'] and not result['usl_queries_ok']
    assert 'fixture-private-key' not in json.dumps(result)


def test_schema_verification_precedes_semantic_ddl_and_missing_columns_stop():
    request,calls=transport(missing_schema=True)
    result=run(request,identifiers('signsafe_usl_test','mock_hpd.hpd_violations'))
    assert result['failed_phase']=='schema_verification'
    assert not any(sql.startswith('COMPILE') for sql in calls)


def test_verify_mode_is_read_only_and_setup_refuses_existing_namespace():
    request,calls=transport()
    result=run(request,identifiers('signsafe_usl_test','mock_hpd.hpd_violations'),verify_only=True)
    assert result['status']=='PASS' and result['dq_executed']
    assert not any(sql.startswith(('CREATE','COMPILE','ACTIVATE','REGISTER','UPDATE','DROP')) for sql in calls)
    def existing(path,method,body,timeout):
        return {'headers':['name'],'data':[['signsafe_usl_test']]} if body['sql'].startswith('SHOW NAMESPACES') else request(path,method,body,timeout)
    result=run(existing,identifiers('signsafe_usl_test','mock_hpd.hpd_violations'))
    assert result['status']=='PARTIAL' and not result['compiled']


def test_missing_credentials_fail_before_network(tmp_path):
    env={**os.environ,'ZETARIS_ORG_ID':''}
    result=subprocess.run([sys.executable,'-B','scripts/verify_zetaris_usl.py','--output',str(tmp_path/'receipt.json')],env=env,capture_output=True,text=True,timeout=10)
    assert result.returncode==1 and 'numeric organization ID' in result.stderr
    assert not (tmp_path/'receipt.json').exists()


def resumed_transport(*,occupied=False,visible=True,source_exists=True,fail_activation=False):
    request,calls=transport(fail_activation=fail_activation)
    def existing(path,method,body,timeout):
        sql=body['sql']
        if sql.startswith('SHOW NAMESPACES') or sql=='SHOW LIGHTNING DATABASES':
            calls.append(sql)
            if sql=='SHOW NAMESPACES OR TABLES IN lightning.metastore':
                return {'headers':['name'],'data':[['signsafe_usl_test']] if visible else []}
            if sql=='SHOW LIGHTNING DATABASES':
                return {'headers':['name'],'data':[['signsafe_usl_test_sources']] if source_exists else []}
            return {'headers':['name'],'data':[['renter_records_v1']] if occupied else []}
        return request(path,method,body,timeout)
    return existing,calls


def test_resume_deploys_without_creating_sources_or_namespaces():
    request,calls=resumed_transport()
    result=run(request,identifiers('signsafe_usl_test','mock_hpd.hpd_violations'),resume=True)
    assert result['status']=='PASS' and result['operation_mode']=='resume_deploy'
    assert result['compiled'] and result['activated'] and result['usl_queries_ok']==3 and result['dq_executed']
    assert not any(sql.startswith(('CREATE NAMESPACE','CREATE LIGHTNING','DROP','UPDATE','REMOVE')) for sql in calls)
    compile_index=next(i for i,sql in enumerate(calls) if sql.startswith('COMPILE'))
    assert calls[compile_index-1]=='SHOW NAMESPACES OR TABLES IN lightning.metastore.signsafe_usl_test'
    assert len([sql for sql in calls if sql.startswith('DESCRIBE')])==3


@pytest.mark.parametrize('options',[{'occupied':True},{'visible':False},{'source_exists':False}])
def test_resume_missing_prerequisites_or_existing_objects_stop_without_writes(options):
    request,calls=resumed_transport(**options)
    result=run(request,identifiers('signsafe_usl_test','mock_hpd.hpd_violations'),resume=True)
    assert result['status']=='PARTIAL' and not result['compiled']
    assert not any(sql.startswith(('CREATE','COMPILE','ACTIVATE','REGISTER','DROP','UPDATE')) for sql in calls)


def test_resume_activation_error_stops_before_queries_or_dq():
    request,calls=resumed_transport(fail_activation=True)
    result=run(request,identifiers('signsafe_usl_test','mock_hpd.hpd_violations'),resume=True)
    assert result['compiled'] and not result['activated']
    assert result['failed_phase']=='activate' and result['usl_queries_ok']==0 and not result['dq_executed']
    assert sum(sql.startswith('ACTIVATE') for sql in calls)==1
