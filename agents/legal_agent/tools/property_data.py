"""Provider-neutral read-only HPD access. Never silently switch providers."""
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import inspect
import re
from typing import Protocol
from urllib.parse import urlencode
from urllib.request import urlopen

if __package__ and __package__.startswith('agents.legal_agent'):
    from .execution import ExecutionBudget
else:
    from tools.execution import ExecutionBudget

BUILDINGS = 'kj4p-ruqc'
VIOLATIONS = 'wvxf-dwi5'
DATASETS = {BUILDINGS, VIOLATIONS}


@dataclass
class RecordBatch:
    dataset: str
    provider: str
    rows: list[dict]
    retrieved_at: datetime
    query_reference: str
    bounded: bool = True

    def capture(self):
        return dict(dataset=self.dataset, provider=self.provider, rows=self.rows,
                    retrieved_at=self.retrieved_at.isoformat(), query_reference=self.query_reference,
                    bounded=self.bounded)


class PropertyDataProvider(Protocol):
    name: str
    def fetch(self, dataset: str, *, building_id: str | None = None, limit: int = 200) -> RecordBatch: ...


def validate_request(dataset, building_id, limit):
    if dataset not in DATASETS or not isinstance(limit, int) or not 1 <= limit <= 5000:
        raise ValueError('Dataset or row limit is not allowed')
    if building_id is not None and not re.fullmatch(r'[1-9][0-9]*', str(building_id)):
        raise ValueError('HPD building ID must be a positive integer')


class ZetarisPropertyProvider:
    name = 'zetaris'

    def __init__(self, request, *, source: str, buildings_table: str, violations_table: str, engine_id=None,budget=None):
        if not all(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', x) for x in (source, buildings_table, violations_table)):
            raise ValueError('Invalid configured identifier')
        self.request, self.engine_id = request, engine_id
        self.budget=budget or ExecutionBudget();self.source=source
        self.tables = {BUILDINGS: f'{source}.{buildings_table}', VIOLATIONS: f'{source}.{violations_table}'}
        discovery = self._query(f'SHOW TABLES IN {source}', 100)
        index = discovery['headers'].index('table_identifier')
        visible = {row[index] for row in discovery['data']}
        if not set(self.tables.values()) <= visible:
            raise ValueError('Configured HPD tables are not present in actual Zetaris discovery')

    def _query(self, sql, limit):
        refs='|'.join(re.escape(v) for v in self.tables.values())
        if sql!=f'SHOW TABLES IN {self.source}' and not re.fullmatch(rf"SELECT \* FROM (?:{refs})(?: WHERE buildingid = '[0-9]+')? ORDER BY (?:buildingid|violationid) LIMIT [0-9]+",sql):
            raise ValueError('Unapproved property query')
        self.budget.consume('tool','zetaris_property_query')
        body = {'sql': sql, 'limit': limit}
        if self.engine_id:
            body['engineId'] = self.engine_id
        timeout=self.budget.timeout(30)
        kwargs={'timeout':timeout} if 'timeout' in inspect.signature(self.request).parameters else {}
        return self.budget.invoke(self.request,'/api/proxy/sql-editor/sqls/run-query','POST',body,ceiling=timeout,**kwargs)

    def fetch(self, dataset, *, building_id=None, limit=200):
        validate_request(dataset, building_id, limit)
        # Bind parameters are not documented for this proxy. Only validated
        # numeric building IDs enter SQL, never an address or free-form filter.
        where = f" WHERE buildingid = '{int(building_id)}'" if building_id is not None else ''
        key = 'buildingid' if dataset == BUILDINGS else 'violationid'
        sql = f'SELECT * FROM {self.tables[dataset]}{where} ORDER BY {key} LIMIT {limit}'
        response = self._query(sql, limit)
        headers = response['headers']
        if len(headers) != len(set(headers)):
            raise ValueError('Ambiguous response columns')
        rows = [dict(zip(headers, row, strict=True)) for row in response['data']]
        return RecordBatch(dataset, self.name, rows, datetime.now(UTC), sql)


class NYCOpenDataDevelopmentProvider:
    """Explicit development fallback, not the required sponsor data layer."""
    name = 'nyc_open_data_development_fallback'

    def __init__(self, *, zip_code='10017', transport=None,budget=None):
        if zip_code not in {'10017', '11103'}:
            raise ValueError('ZIP outside hackathon scope')
        self.zip_code = zip_code
        self.transport = transport or self._http
        self.budget=budget or ExecutionBudget()

    @staticmethod
    def _http(url,timeout=30):
        with urlopen(url, timeout=timeout) as response:
            data = response.read(20_000_001)
        if len(data) > 20_000_000:
            raise ValueError('Source response exceeds development limit')
        return json.loads(data)

    def fetch(self, dataset, *, building_id=None, limit=200):
        validate_request(dataset, building_id, limit)
        params = {'zip': self.zip_code, '$limit': limit,
                  '$order': 'buildingid' if dataset == BUILDINGS else 'violationid DESC'}
        if building_id is not None:
            params['buildingid'] = str(building_id)
        url = f'https://data.cityofnewyork.us/resource/{dataset}.json?' + urlencode(params)
        self.budget.consume('tool','nyc_api_development_fallback')
        kwargs={'timeout':self.budget.timeout(30)} if 'timeout' in inspect.signature(self.transport).parameters else {}
        rows = self.budget.invoke(self.transport,url,ceiling=30,**kwargs)
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError('Unexpected official NYC response')
        return RecordBatch(dataset, self.name, rows, datetime.now(UTC), url)
