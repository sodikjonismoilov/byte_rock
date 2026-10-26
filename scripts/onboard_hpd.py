"""Onboard bounded official HPD REST sources using current Zetaris SQL.

Does not replace existing tables. Captures status, never server error bodies.
Run: python scripts/onboard_hpd.py --source <new_or_existing_owned_source>
"""
import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
from urllib.parse import urlencode


def onboarding_statements(source):
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', source):
        raise ValueError('Invalid source identifier')
    statements = [('source', f'CREATE LIGHTNING DATABASE {source} DESCRIBE BY "SignSafe HPD development data source" OPTIONS ()')]
    for table, dataset, limit, order in (
        ('hpd_buildings', 'kj4p-ruqc', 5000, 'buildingid'),
        ('hpd_violations', 'wvxf-dwi5', 200, 'violationid DESC')):
        endpoint = f'https://data.cityofnewyork.us/resource/{dataset}.json?' + urlencode({'zip':'10017','$limit':limit,'$order':order})
        statements.append((table, f'CREATE LIGHTNING REST TABLE {table} FROM {source} REQUEST(endpoint "{endpoint}", method "get", response_type "json", http_encoding "URLENCODED") HEADER () BODY ()'))
    return statements


def onboard(request, source, *, engine_id=None):
    statements = onboarding_statements(source)
    trace = []
    def query(sql, limit=10):
        body = {'sql':sql, 'limit':limit}
        if engine_id:
            body['engineId'] = engine_id
        return request('/api/proxy/sql-editor/sqls/run-query', 'POST', body)
    # Physical REST databases are separate from logical SHOW DATASOURCES.
    databases = query('SHOW LIGHTNING DATABASES', 100)
    names = {row[databases['headers'].index('name')] for row in databases['data']}
    for name, sql in statements:
        if name == 'source' and source in names:
            trace.append({'object':source,'status':'already_present'})
            continue
        if name != 'source':
            tables = query(f'SHOW TABLES IN {source}',100)
            index = tables['headers'].index('table_identifier')
            if f'{source}.{name}' in {row[index] for row in tables['data']}:
                trace.append({'object':f'{source}.{name}','status':'already_present_not_replaced'})
                continue
        query(sql)
        trace.append({'object':source if name == 'source' else f'{source}.{name}',
                      'status':'ddl_accepted_not_yet_row_verified','sql':sql})
    # A successful DDL response is not enough: read actual rows through Zetaris.
    for table in ('hpd_buildings','hpd_violations'):
        response = query(f'SELECT * FROM {source}.{table} LIMIT 1',1)
        if not response.get('data'):
            raise ValueError('Registered source did not return a real row')
        trace.append({'object':f'{source}.{table}','status':'row_verified','column_names':response['headers'],'row_count':len(response['data'])})
    return {'capture_type':'live_zetaris_onboarding_verification','source':source,
            'captured_at':datetime.now(UTC).isoformat(),'attempts':trace,
            'coverage':'ZIP 10017; buildings endpoint cap 5000, violation endpoint cap 200 ordered by descending violation ID. Not complete city or building history.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True)
    parser.add_argument('--output',type=Path,default=Path(__file__).resolve().parents[1]/'reports'/'zetaris_onboarding_verified.json')
    args = parser.parse_args()
    if __package__:
        from .zetaris_api import zetaris_request
    else:
        from zetaris_api import zetaris_request
    try:
        capture = onboard(zetaris_request,args.source,engine_id=os.environ.get('ZETARIS_ENGINE_ID'))
    except Exception as error:
        print(f'Zetaris onboarding failed: {type(error).__name__}. No direct API substitution was made.')
        return 1
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(capture,indent=2)+'\n')
    print('Both HPD tables verified with actual Zetaris rows.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
