"""Verified source configuration; runtime availability is reported separately."""
import json
import re
from pathlib import Path

DEFAULT_REGISTRY = Path(__file__).resolve().parents[1] / 'data' / 'source_registry.json'


def load_registry(path=DEFAULT_REGISTRY):
    data = json.loads(Path(path).read_text())
    result = {s['key']:s for s in data['sources']}
    if len(result) != len(data['sources']):
        raise ValueError('Source keys must be unique')
    for source in result.values():
        if 'dataset' not in source:
            continue
        if not re.fullmatch(r'[a-z0-9]{4}-[a-z0-9]{4}',source['dataset']):
            raise ValueError('Invalid official dataset ID')
        fields = source['fields']
        if any(not re.fullmatch(r'[a-z][a-z0-9_]*',field) for field in fields):
            raise ValueError('Unverified/unsupported source column spelling')
        configured = [*source['record_id_fields'], *source['identifiers'].values(), *source['address_fields'], *source['description_fields']]
        configured += [v for v in (source.get('date_field'),source.get('status_field'),source.get('unit_field'),source.get('borough_field')) if v]
        if not set(configured) <= fields.keys():
            raise ValueError('Source mapping references an unverified column')
    return result
