"""Address-driven source access through bounded, owned REST registrations.

Every upstream filter/page is in the registered endpoint; downstream SQL never
pretends to broaden a fixed request. One temporary namespace per run is removed
on close. No teammate source is altered and no persistent state database exists.
"""
from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
import inspect
import threading
import re
import uuid
from urllib.parse import urlencode
from urllib.request import urlopen

if __package__ and __package__.startswith('agents.legal_agent'):
    from .execution import ExecutionBudget, ExecutionStopped
else:
    from tools.execution import ExecutionBudget, ExecutionStopped


class RetrievalStopped(RuntimeError):
    pass


def error_category(error):
    """Useful categories without storing credential-bearing response bodies."""
    message=str(error).lower()
    if 'timed out' in message or 'timeout' in message:return 'transport_timeout'
    if 'http 401' in message or 'http 403' in message:return 'authorization_unavailable'
    if 'http 429' in message:return 'rate_limited'
    if 'repeated source identity' in message:return 'unstable_pagination_or_repeated_source_id'
    if 'identifier missing' in message:return 'agency_identifier_missing'
    if 'namespace cap' in message:return 'active_namespace_cap'
    return type(error).__name__


@dataclass
class SourceRetrieval:
    source_key: str
    provider: str
    rows: list = field(default_factory=list)
    pages: list = field(default_factory=list)
    status: str = 'not_queried'
    complete: bool = False
    reason: str = ''
    match_field: str | None = None
    query_filter: str = ''

    def as_dict(self):
        return dict(source_key=self.source_key,provider=self.provider,rows=self.rows,pages=self.pages,
                    status=self.status,complete=self.complete,reason=self.reason,match_field=self.match_field,query_filter=self.query_filter)


def literal(value, data_type='text'):
    text = str(value)
    if data_type == 'number':
        if not re.fullmatch(r'[0-9]+',text):
            raise ValueError('Invalid numeric identifier')
        return text
    if len(text) > 300 or any(ord(c)<32 for c in text):
        raise ValueError('Invalid filter value')
    return "'" + text.replace("'", "''") + "'"


def equals(source, field, value):
    if field not in source['fields']:
        raise ValueError('Filter field not in verified schema')
    return field + ' = ' + literal(value,source['fields'][field])


class AddressDataProvider:
    """Shared paginated interface for Zetaris and explicit development fallback."""
    name = 'abstract'
    counts_transport_calls=False

    def __init__(self, *, page_size=100, max_pages=3, max_requests=45, budget=None):
        if not 1 <= page_size <= 500 or not 1 <= max_pages <= 10 or not 1 <= max_requests <= 80:
            raise ValueError('Invalid retrieval budget')
        self.page_size,self.max_pages,self.max_requests = page_size,max_pages,max_requests
        self.requests=0
        self.events=[]
        self.budget=budget or ExecutionBudget()
        self.handles_execution_budget=True

    def fetch_where(self, source, where, *, match_field=None, max_pages=None):
        result = SourceRetrieval(source['key'],self.name,match_field=match_field,query_filter=where)
        if source.get('capability') == 'manual_only':
            result.status='manual_only'; result.reason=' '.join(source['limitations']); return result
        seen={}
        # Stable agency-key order; :id is not invented as an agency identifier.
        order = source.get('pagination_order') or ','.join(source['record_id_fields'])
        if order != ':id' and not set(order.split(',')) <= source['fields'].keys():
            raise ValueError('Pagination order not in verified schema')
        for page in range(min(max_pages or self.max_pages,self.max_pages)):
            self.budget.check()
            if self.requests >= self.max_requests:
                result.status='budget_exhausted';result.reason='Shared retrieval page budget reached';break
            params={'$where':where,'$order':order,'$limit':self.page_size,'$offset':page*self.page_size}
            url=f'https://data.cityofnewyork.us/resource/{source["dataset"]}.json?'+urlencode(params)
            self.requests+=1
            event={'source':source['key'],'provider':self.name,'upstream_url':url,'page':page,
                   'requested_at':datetime.now(UTC).isoformat()}
            try:
                if not self.counts_transport_calls:
                    self.budget.consume('tool','source_page')
                    rows=self.budget.invoke(self._page,source,url,ceiling=30)
                else:
                    rows=self._page(source,url)
                if not isinstance(rows,list) or any(not isinstance(r,dict) for r in rows):
                    raise ValueError('Invalid page shape')
                if len(rows)>self.page_size:
                    raise ValueError('Provider exceeded page bound')
                event.update(status='ok',row_count=len(rows),retrieved_at=datetime.now(UTC).isoformat())
                result.pages.append(event.copy());self.events.append(event)
                for row in rows:
                    values=[row.get(k) for k in source['record_id_fields']]
                    if any(value is None or not str(value).strip() for value in values):
                        raise ValueError('Agency record identifier missing')
                    key=tuple(str(value) for value in values)
                    if key in seen:
                        raise ValueError('Repeated source identity across pages; pagination or source snapshot unstable')
                    seen[key]=row
                    result.rows.append(row)
                if len(rows)<self.page_size:
                    result.complete=True;result.status='retrieved' if result.rows else 'no_records';break
                result.status='bounded';result.reason='Page cap reached; remaining records may exist'
            except Exception as error:
                event.update(status='unavailable',error_type=error_category(error))
                if event not in self.events:self.events.append(event)
                result.pages.append(event.copy()) if not result.pages or result.pages[-1] != event else None
                result.complete=False;result.status='unavailable';result.reason=error_category(error)
                break
        return result

    def _page(self,source,url):
        raise NotImplementedError

    def fetch(self,dataset,*,building_id=None,limit=200):
        """Compatibility with the existing PropertyDataProvider contract.

        New orchestration uses fetch_where for audited identifiers and paging.
        Legacy callers still receive an explicitly bounded RecordBatch.
        """
        if __package__ and __package__.startswith("agents.legal_agent"):
            from ..tools.property_data import RecordBatch
        else:
            from tools.property_data import RecordBatch
        if __package__ and __package__.startswith("agents.legal_agent"):
            from ..tools.source_registry import load_registry
        else:
            from tools.source_registry import load_registry
        sources=[s for s in load_registry().values() if s.get('dataset')==dataset]
        if len(sources)!=1 or not isinstance(limit,int) or not 1<=limit<=5000:
            raise ValueError('Dataset or limit not allowed')
        source=sources[0];where='1=1'
        if building_id is not None:
            field=source['identifiers'].get('hpd_building_id')
            if not field:raise ValueError('Source does not support HPD building ID queries')
            where=equals(source,field,building_id)
        result=self.fetch_where(source,where,max_pages=min(self.max_pages,(limit+self.page_size-1)//self.page_size))
        if result.status in {'unavailable','budget_exhausted'}:raise RetrievalStopped(result.reason)
        return RecordBatch(dataset,self.name,result.rows[:limit],datetime.now(UTC),
            '\n'.join(p['upstream_url'] for p in result.pages),bounded=not result.complete or len(result.rows)>limit)

    def close(self):
        pass


class DynamicZetarisProvider(AddressDataProvider):
    name='zetaris'
    counts_transport_calls=True

    def __init__(self,request,*,engine_id=None,**kwargs):
        super().__init__(**kwargs)
        self.request,self.engine_id=request,engine_id
        self.namespace='signsafe_run_'+uuid.uuid4().hex[:16]
        self.created=False; self.closed=False; self.table_count=0;self.blocked=False
        self.creation_attempted=False;self.cleanup_attempts=0;self._cleanup_lock=threading.Lock()

    def _validate_sql(self,sql):
        ns=re.escape(self.namespace)
        allowed=(sql=='SHOW LIGHTNING DATABASES' or
            sql==f'CREATE LIGHTNING DATABASE {self.namespace} DESCRIBE BY "Bounded temporary SignSafe query run" OPTIONS ()' or
            re.fullmatch(rf'SELECT \* FROM {ns}\.p[0-9]{{3}} LIMIT [0-9]+',sql) or
            re.fullmatch(rf'CREATE LIGHTNING REST TABLE p[0-9]{{3}} FROM {ns} REQUEST\(endpoint "https://data\.cityofnewyork\.us/resource/[a-z0-9]{{4}}-[a-z0-9]{{4}}\.json\?[^"\r\n]+", method "get", response_type "json", http_encoding "URLENCODED"\) HEADER \(\) BODY \(\)',sql))
        if not allowed:raise ValueError('SQL operation is not authorized for this owned query run')

    def _request(self,sql,limit,*,timeout):
        body={'sql':sql,'limit':limit}
        if self.engine_id:body['engineId']=self.engine_id
        parameters=inspect.signature(self.request).parameters
        kwargs={'timeout':timeout} if 'timeout' in parameters else {}
        return self.request('/api/proxy/sql-editor/sqls/run-query','POST',body,**kwargs)

    def _query(self,sql,limit):
        self._validate_sql(sql)
        self.budget.consume('tool','zetaris_sql')
        timeout=self.budget.timeout(30)
        self.budget.trace.emit('zetaris.retrieval_started',operation=sql.split()[0])
        try:
            result=self.budget.invoke(self._request,sql,limit,timeout=timeout,ceiling=timeout,on_late=self._late_cleanup)
            self.budget.trace.emit('zetaris.retrieval_completed',operation=sql.split()[0])
            return result
        except Exception as error:
            self.budget.trace.emit('zetaris.retrieval_failed',error_type=type(error).__name__)
            raise

    def _late_cleanup(self):
        if self.closed and self.creation_attempted:self._cleanup()

    def _page(self,source,url):
        if self.closed:raise RetrievalStopped('Provider already closed')
        if self.blocked:raise RetrievalStopped('Active namespace cap reached')
        if not self.created:
            existing=self._query('SHOW LIGHTNING DATABASES',1000)
            name_index=existing['headers'].index('name')
            active=[row[name_index] for row in existing['data'] if re.fullmatch(r'signsafe_run_[0-9a-f]{16}',row[name_index])]
            if len(active)>=3:
                self.blocked=True
                raise RetrievalStopped('Active namespace cap reached; clean up or finish existing owned runs')
            self.creation_attempted=True
            self._query(f'CREATE LIGHTNING DATABASE {self.namespace} DESCRIBE BY "Bounded temporary SignSafe query run" OPTIONS ()',1)
            self.created=True
        if self.table_count >= self.max_requests:raise RetrievalStopped('Temporary table cap reached')
        table=f'p{self.table_count:03d}'
        self.table_count+=1
        # URL is constructed with urlencode and a fixed official host; addresses
        # cannot inject SQL delimiters into the double-quoted endpoint literal.
        if not url.startswith('https://data.cityofnewyork.us/resource/') or '"' in url:
            raise ValueError('Untrusted endpoint')
        sql=f'CREATE LIGHTNING REST TABLE {table} FROM {self.namespace} REQUEST(endpoint "{url}", method "get", response_type "json", http_encoding "URLENCODED") HEADER () BODY ()'
        self._query(sql,1)
        response=self._query(f'SELECT * FROM {self.namespace}.{table} LIMIT {self.page_size+1}',self.page_size+1)
        headers=response['headers']
        if len(headers)!=len(set(headers)):raise ValueError('Ambiguous columns')
        return [dict(zip(headers,row,strict=True)) for row in response['data']]

    def close(self):
        if self.closed:return
        self.closed=True
        if self.creation_attempted:self._cleanup()

    def _cleanup(self):
        # Reserve at most two cleanup operations, including a late-response
        # attempt. Cleanup cannot be disabled by an exhausted research budget.
        with self._cleanup_lock:
            if self.cleanup_attempts>=2:return
            self.cleanup_attempts+=1
        try:
            from concurrent.futures import ThreadPoolExecutor
            pool=ThreadPoolExecutor(max_workers=1)
            try:
                future=pool.submit(self._request,f'DROP LIGHTNING DATABASE {self.namespace}',1,timeout=self.budget.limits.cleanup_timeout_seconds)
                future.result(timeout=self.budget.limits.cleanup_timeout_seconds)
            finally:pool.shutdown(wait=False,cancel_futures=True)
            self.budget.trace.emit('zetaris.cleanup',status='removed')
            self.events.append({'action':'cleanup','namespace':self.namespace,'status':'removed','attempt':self.cleanup_attempts})
        except Exception as error:
            self.budget.trace.emit('zetaris.cleanup',status='failed',error_type=type(error).__name__)
            self.events.append({'action':'cleanup','namespace':self.namespace,'status':'failed','error_type':type(error).__name__})


class DynamicNYCDevelopmentProvider(AddressDataProvider):
    name='nyc_open_data_development_fallback'
    counts_transport_calls=True

    def __init__(self,*,transport=None,**kwargs):
        super().__init__(**kwargs);self.transport=transport or self._http

    @staticmethod
    def _http(url,timeout=30):
        with urlopen(url,timeout=timeout) as response:
            body=response.read(20_000_001)
        if len(body)>20_000_000:raise ValueError('Response cap reached')
        return json.loads(body)

    def _page(self,source,url):
        self.budget.consume('tool','nyc_api_development_fallback')
        if self.transport == self._http:
            return self._http(url,timeout=self.budget.timeout(30))
        return self.budget.invoke(self.transport,url,ceiling=30)


class RecordedAddressProvider(AddressDataProvider):
    """Exact-query offline replay. Never reuse a different property's capture."""
    data_mode='recorded_replay'

    def __init__(self,report):
        super().__init__()
        self.name=report['provider']
        self.captured_at=report.get('generated_at')
        self.queries={(r['source_key'],r['query_filter']):r for r in report['retrievals']}

    def fetch_where(self,source,where,*,match_field=None,max_pages=None):
        raw=self.queries.get((source['key'],where))
        if raw is None:
            return SourceRetrieval(source['key'],self.name,status='unavailable',reason='Query not present in recorded capture',query_filter=where)
        self.events.append({'action':'recorded_replay','source':source['key'],'fresh_network_request':False})
        return SourceRetrieval(**json.loads(json.dumps(raw)))
