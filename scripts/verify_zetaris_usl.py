"""One bounded SignSafe USL setup/verification; no agent or application query changes.

Uses the existing connector and public bounded REST definitions via Zetaris only.
Setup refuses existing namespaces. --resume deploys only into an existing empty
semantic namespace using existing sources. --verify is read-only and reusable.
No raw exception bodies, credentials or connection origins enter diagnostics.
"""
from __future__ import annotations
import argparse
from datetime import UTC,datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
SQL=ROOT/'sql/zetaris_usl'


def identifiers(namespace,hpd_table):
    if not re.fullmatch(r'signsafe_usl_[a-z0-9_]{1,48}',namespace):raise ValueError('Use a distinct signsafe_usl_ namespace')
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*',hpd_table):raise ValueError('Invalid HPD table identifier')
    return {'namespace':namespace,'hpd_table':hpd_table,'source_db':namespace+'_sources'}


def render(name,variables):
    sql=(SQL/name).read_text().strip()
    for key,value in variables.items():sql=sql.replace('${'+key+'}',value)
    if '${' in sql:raise ValueError('Unresolved SQL parameter')
    return sql


def source_statements(source_db):
    if not re.fullmatch(r'signsafe_usl_[a-z0-9_]{1,60}_sources',source_db):raise ValueError('Invalid owned source namespace')
    return [sql.strip() for sql in render('sources.sql',{'source_db':source_db}).split(';') if sql.strip()]


def safe_error(error):
    message=str(error)
    for key,value in os.environ.items():
        if re.search(r'SECRET|TOKEN|PASSWORD|API_KEY|USERNAME|BASE_URL',key,re.I) and len(value)>=4:message=message.replace(value,'[PRIVATE]')
    message=re.sub(r'(?i)bearer\s+\S+','Bearer [PRIVATE]',message)
    message=re.sub(r'https?://[^\s\"<>]+','[URL]',message)
    return message[:1500]


def run(request,variables,*,engine_id=None,verify_only=False,resume=False,deadline_seconds=420,max_queries=40):
    if verify_only and resume:raise ValueError('Choose resume or verify, not both')
    if not 0<deadline_seconds<=420 or not 1<=max_queries<=40:raise ValueError('Invalid verification bounds')
    if variables!=identifiers(variables['namespace'],variables['hpd_table']):raise ValueError('Unvalidated SQL variables')
    started=time.monotonic();namespace=variables['namespace'];source_db=variables['source_db']
    receipt={'schema_version':'signsafe.usl.verification.v1','mode':'live_zetaris','captured_at':datetime.now(UTC).isoformat(),
        'operation_mode':'resume_deploy' if resume else 'read_only_verify' if verify_only else 'initial_setup',
        'namespace':namespace,'source_db':source_db,'engine_selection':'explicit' if engine_id else 'server_default_unidentified',
        'limits':{'seconds':deadline_seconds,'queries':max_queries,'new_source_rows_each':20},
        'steps':[],'compiled':False,'activated':False,'usl_queries_ok':0,'dq_registered':False,'dq_executed':False,
        'scope':'ZIP 10017 bounded heterogeneous records; no inferred property joins; not an address investigation'}
    phase='preflight'
    def query(sql,*,retain=True):
        if len(receipt['steps'])>=max_queries or time.monotonic()-started>=deadline_seconds:raise TimeoutError('USL verification budget exhausted')
        step={'phase':phase,'sql':sql,'at':datetime.now(UTC).isoformat()};receipt['steps'].append(step)
        before=time.monotonic()
        try:
            response=request('/api/proxy/sql-editor/sqls/run-query','POST',{'sql':sql,'limit':100,**({'engineId':engine_id} if engine_id else {})},timeout=min(20,deadline_seconds-(before-started)))
            headers=response.get('headers');rows=response.get('data')
            if not isinstance(headers,list) or not isinstance(rows,list):raise ValueError('Unexpected SQL response shape')
            step.update(status='ok',headers=headers,returned_rows=len(rows))
            if retain:step['rows']=rows
            else:step['response_sha256']=hashlib.sha256(json.dumps(response,sort_keys=True).encode()).hexdigest()
            return response
        except Exception as error:
            step.update(status='error',error_type=type(error).__name__,message=safe_error(error));raise
        finally:step['seconds']=round(time.monotonic()-before,3)
    try:
        query('SELECT 1');query('SHOW SERVER VERSION')
        existing=query('SHOW NAMESPACES OR TABLES IN lightning.metastore')
        name_index=existing['headers'].index('name')
        names={str(row[name_index]).rsplit('.',1)[-1] for row in existing['data']}
        if resume:
            if namespace not in names:raise ValueError('Resume requires a visible existing semantic namespace; nothing created')
            children=query('SHOW NAMESPACES OR TABLES IN lightning.metastore.'+namespace)
            if children['data']:raise ValueError('Resume requires an empty semantic namespace; existing objects will not be overwritten')
        elif not verify_only and namespace in names:raise ValueError('Semantic namespace exists; use --resume for an empty namespace or --verify. Nothing overwritten.')
        dbs=query('SHOW LIGHTNING DATABASES')
        db_index=dbs['headers'].index('name')
        source_exists=source_db in {str(row[db_index]) for row in dbs['data']}
        if resume and not source_exists:raise ValueError('Resume requires the existing source database; nothing registered')
        if not verify_only and not resume and source_exists:raise ValueError('Source namespace exists; setup is once-only. Nothing overwritten.')
        phase='source_registration'
        if not verify_only and not resume:
            for statement in source_statements(source_db):query(statement,retain=False)
        phase='schema_verification'
        tables=[variables['hpd_table'],source_db+'.dob_permits',source_db+'.oath_fdny']
        required=[{'violationid','buildingid','bin','bbl','boro','block','lot','inspectiondate','currentstatus'},
            {'permit_si_no','bin__','borough','block','lot','issuance_date','permit_status'},
            {'ticket_number','violation_location_borough','violation_location_block_no','violation_location_lot_no','violation_date','hearing_status'}]
        for table,columns in zip(tables,required):
            result=query('DESCRIBE DATASOURCE TABLE '+table)
            position=result['headers'].index('col_name')
            if not columns<={row[position] for row in result['data']}:raise ValueError('Required original source columns are unavailable; no inferred replacement')
        phase='exploration'
        for sql in render('explore.sql',variables).split(';'):
            if sql.strip():
                result=query(sql.strip())
                if not result['data']:raise ValueError('Selected source returned no actual rows')
        if not verify_only:
            phase='deploy'
            if not resume:query('CREATE NAMESPACE IF NOT EXISTS lightning.metastore.'+namespace,retain=False)
            else:
                # Recheck immediately before deployment, not just before source reads.
                children=query('SHOW NAMESPACES OR TABLES IN lightning.metastore.'+namespace)
                if children['data']:raise ValueError('Namespace changed during preflight; no existing objects overwritten')
            query(render('model.sql',variables),retain=False);receipt['compiled']=True
            phase='activate'
            query(render('activate.sql',variables),retain=False);receipt['activated']=True
        else:
            phase='load_existing';query('LOAD USL renter_records_v1 NAMESPACE lightning.metastore.'+namespace,retain=False)
        phase='usl_queries'
        for sql in render('verify.sql',variables).split(';'):
            if sql.strip():
                result=query(sql.strip())
                if not result['data']:raise ValueError('USL query returned no rows')
                receipt['usl_queries_ok']+=1
        phase='data_quality'
        if not verify_only:query(render('dq.sql',variables),retain=False);receipt['dq_registered']=True
        query('LIST DQ USL lightning.metastore.'+namespace+'.renter_records_v1')
        result=query('RUN DQ source_identity_integrity TABLE lightning.metastore.'+namespace+'.renter_records_v1.events')
        if not result['data']:raise ValueError('DQ returned no execution result')
        receipt['dq_executed']=True;receipt['status']='PASS'
    except Exception as error:
        receipt.update(status='PARTIAL' if any(s.get('status')=='ok' for s in receipt['steps']) else 'NOT_DEMONSTRATED',
            failed_phase=phase,error_type=type(error).__name__,error=safe_error(error))
    receipt['duration_seconds']=round(time.monotonic()-started,3)
    return receipt


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--namespace',default='signsafe_usl_20261026')
    parser.add_argument('--hpd-table',default='signsafe_hpd_20261025.hpd_violations')
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--verify',action='store_true',help='Read-only rerun; does not create, overwrite, activate or register rules')
    mode.add_argument('--resume',action='store_true',help='Deploy into an existing empty semantic namespace; never create namespaces or register sources')
    parser.add_argument('--output',type=Path,default=ROOT/'reports/sponsor_compliance/usl_verification.json')
    args=parser.parse_args(argv)
    try:
        variables=identifiers(args.namespace,args.hpd_table)
        from scripts.zetaris_api import zetaris_request
        receipt=run(zetaris_request,variables,engine_id=os.getenv('ZETARIS_ENGINE_ID'),verify_only=args.verify,resume=args.resume)
    except Exception as error:
        print('Zetaris USL setup unavailable: '+safe_error(error),file=sys.stderr);return 1
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(receipt,indent=2)+'\n');args.output.chmod(0o600)
    print(json.dumps({k:receipt[k] for k in ['status','namespace','compiled','activated','usl_queries_ok','dq_registered','dq_executed','duration_seconds']}))
    return 0 if receipt['status']=='PASS' else 2


if __name__=='__main__':raise SystemExit(main())
