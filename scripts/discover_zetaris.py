"""Read-only connection/catalog probe using the original UI-proxy connector.

No credentials, server URL, auth responses or exception bodies are persisted.
The capture is live catalog metadata, never an NYC property replay fixture.
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path


def discover(request, *, engine_id=None):
    captures = []
    for sql, limit in (('SELECT 1', 1), ('SHOW DATASOURCES', 100)):
        body = {'sql': sql, 'limit': limit}
        if engine_id:
            body['engineId'] = engine_id
        entry = {'sql': sql, 'requested_at': datetime.now(UTC).isoformat()}
        try:
            result = request('/api/proxy/sql-editor/sqls/run-query', 'POST', body)
            headers, rows = result['headers'], result['data']
            if not isinstance(headers, list) or not isinstance(rows, list):
                raise ValueError('Unexpected query response')
            # Retain only these known metadata columns; never arbitrary server data.
            expected = ['1'] if sql == 'SELECT 1' else ['name', 'description', 'id']
            if headers != expected or any(not isinstance(row, list) or len(row) != len(headers) for row in rows):
                raise ValueError('Unexpected catalog schema')
            entry.update(status='ok', result={'headers': headers, 'data': rows, 'total': result.get('total'), 'timeUsed': result.get('timeUsed')})
        except Exception as error:
            entry.update(status='error', error_type=type(error).__name__)
        captures.append(entry)
    if any(c['status'] == 'error' for c in captures):
        status = 'discovery_failed'
    elif not captures[1]['result']['data']:
        status = 'connected_no_visible_logical_sources'
    else:
        status = 'connected_sources_visible'
    return {'capture_type': 'live_zetaris_catalog_discovery', 'status': status,
            'engine_selection': 'explicit' if engine_id else 'server_selected_unidentified',
            'captures': captures, 'property_records_retrieved': 0,
            'limitation': 'Catalog visibility applies only to the configured organization, credentials and selected engine; it does not establish that no NYC data exists elsewhere.'}


def discover_topology(request, *, engine_id=None):
    """Exact read-only routes/commands observed in the deployed UI, not guessed IDs.

    Public frontend tutorial fixtures are not evidence of registered objects.
    Only authenticated responses from these routes populate this capture.
    """
    checks = []
    routes = (
        ('engines', '/compute/engines', None),
        ('datasources', '/datasource/datasources', None),
        ('lakehouses', '/dlwh/data-lakes', None),
        ('unity_catalogs', '/external-catalog/unity-catalog', None),
        ('metastore_databases', '/metastore/datasource-schemas', 'databases'),
    )
    for label, path, key in routes:
        entry = {'check': label, 'route': '/api/proxy' + path, 'requested_at': datetime.now(UTC).isoformat()}
        try:
            response = request(entry['route'])
            rows = response[key] if key else response
            if not isinstance(rows, list):
                raise ValueError('Unexpected metadata shape')
            items = []
            for row in rows:
                if isinstance(row, str):
                    items.append({'name': row})
                elif isinstance(row, dict):
                    items.append({k: row[k] for k in ('id', 'name', 'alias', 'namespace', 'dbName', 'status', 'type', 'engineType', 'isDefault') if k in row and isinstance(row[k], (str, int, bool))})
                else:
                    raise ValueError('Unexpected metadata item')
            entry.update(status='ok', count=len(rows), items=items)
        except Exception as error:
            entry.update(status='error', error_type=type(error).__name__)
        checks.append(entry)
    for sql in ('SELECT current_database() AS database_name', 'SHOW UNITY CATALOG',
                'SELECT current_catalog() AS catalog_name', 'SHOW TABLES IN default',
                'SHOW LIGHTNING DATABASES'):
        entry = {'check': 'sql_metadata', 'sql': sql, 'requested_at': datetime.now(UTC).isoformat()}
        body = {'sql': sql, 'limit': 100}
        if engine_id:
            body['engineId'] = engine_id
        try:
            response = request('/api/proxy/sql-editor/sqls/run-query', 'POST', body)
            headers, rows = response['headers'], response['data']
            columns = [(i, h) for i, h in enumerate(headers) if h in ('database_name', 'catalog_name', 'table_identifier', 'catalog_type', 'alias', 'name', 'id', 'count')]
            if not columns:
                raise ValueError('Unexpected SQL metadata columns')
            entry.update(status='ok', count=len(rows), items=[{h: row[i] for i, h in columns} for row in rows])
        except Exception as error:
            entry.update(status='error', error_type=type(error).__name__)
        checks.append(entry)
    return {'engine_id_sent': bool(engine_id),
            'engine_resolution': 'explicit_configured_id' if engine_id else 'server_selected_identity_not_exposed_by_query_response',
            'checks': checks,
            'scope': 'Configured organization and credentials only. Empty engine registry does not identify the backend used by successful SQL.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'reports' / 'zetaris_discovery.json')
    args = parser.parse_args()
    if __package__:
        from .zetaris_api import zetaris_request
    else:
        from zetaris_api import zetaris_request
    capture = discover(zetaris_request, engine_id=os.environ.get('ZETARIS_ENGINE_ID'))
    capture['topology'] = discover_topology(zetaris_request, engine_id=os.environ.get('ZETARIS_ENGINE_ID'))
    if any(c.get('sql') == 'SHOW LIGHTNING DATABASES' and c.get('count', 0) > 0 for c in capture['topology']['checks']):
        capture['status'] = 'connected_physical_sources_visible'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(capture, indent=2) + '\n')
    print(capture['status'])
    return 1 if capture['status'] == 'discovery_failed' else 0


if __name__ == '__main__':
    raise SystemExit(main())
