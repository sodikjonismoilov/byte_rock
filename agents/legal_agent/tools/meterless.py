"""Meterless Runtime 1.4/provider v4. No tokens or connect links in diagnostics."""
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import tempfile
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlsplit
if __package__ and __package__.startswith('agents.legal_agent'):
    from .execution import ExecutionStopped
else:
    from tools.execution import ExecutionStopped

PROVIDER_ID='meterless'
PROVIDER_NAME='Meterless Runtime'
APP_ID='signsafe-legal'
DEFAULT_BASE_URL='http://127.0.0.1:8088/v1'
CHAT_TIMEOUT=180


def parse_connection(value):
    """Return canonical origin/v1 and optional fragment token; never echo input."""
    if not isinstance(value,str):raise ValueError('Invalid Meterless URL')
    value=value.strip() or DEFAULT_BASE_URL
    if '://' not in value:value='http://'+value
    try:
        parsed=urlsplit(value)
        if parsed.scheme not in {'http','https'} or not parsed.hostname or parsed.username or parsed.password or parsed.query:
            raise ValueError()
        port=parsed.port
        host=parsed.hostname
        if any(c.isspace() for c in host):raise ValueError()
        host='['+host+']' if ':' in host else host
        origin=parsed.scheme+'://'+host+((':'+str(port)) if port else '')
        path=parsed.path.rstrip('/')
        if path not in {'','/v1','/v1/chat/completions','/v1/models','/healthz','/connect'}:raise ValueError()
        token=None
        if path=='/connect':
            values=parse_qs(parsed.fragment,keep_blank_values=True)
            if len(values.get('k',[]))!=1 or not values['k'][0]:raise ValueError()
            token=values['k'][0]
        elif parsed.fragment:raise ValueError()
        if token=='rt-local' or token and any(c in token for c in '\r\n'):raise ValueError()
        return origin+'/v1',token
    except (ValueError,TypeError):raise ValueError('Invalid Meterless URL or connect link') from None


class MeterlessSettings:
    """Private local provider preferences, never an evidence/state registry."""
    def __init__(self,path=None):
        self.path=Path(path or os.getenv('METERLESS_SETTINGS_FILE') or Path(__file__).resolve().parents[3]/'.local'/'meterless.json')
    def load(self):
        if not self.path.exists():return {}
        try:
            data=json.loads(self.path.read_text())
            if not isinstance(data,dict):raise ValueError()
            return data
        except (ValueError,OSError):raise ExecutionStopped('Cannot read private Meterless settings') from None
    def save(self,*,base_url,token=None,model=None):
        base,connect_token=parse_connection(base_url)
        old=self.load()
        # A token is bound to its origin; never carry it to a newly pasted host.
        data={'base_url':base,'model':model if model is not None else old.get('model','meterless/auto')}
        supplied=connect_token if connect_token is not None else token
        if supplied is None and old.get('base_url')==base:supplied=old.get('meterless_runtime_token','')
        if supplied=='rt-local' or supplied and any(c in supplied for c in '\r\n'):raise ValueError('Use the real runtime token')
        data['meterless_runtime_token']=supplied or ''
        self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        fd,tmp=tempfile.mkstemp(dir=self.path.parent,prefix='.meterless-')
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as stream:json.dump(data,stream)
            os.chmod(tmp,0o600);os.replace(tmp,self.path)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
    def public(self):
        data=self.load()
        return {'provider':PROVIDER_ID,'name':PROVIDER_NAME,'base_url':data.get('base_url',DEFAULT_BASE_URL),
                'model':data.get('model','meterless/auto'),'has_token':bool(data.get('meterless_runtime_token'))}


@dataclass(repr=False)
class RuntimeConfig:
    base_url: str=DEFAULT_BASE_URL
    token: str=field(default='',repr=False)
    model: str='meterless/auto'
    def __post_init__(self):
        self.base_url,fragment_token=parse_connection(self.base_url)
        if fragment_token:self.token=fragment_token
        if not isinstance(self.token,str) or self.token=='rt-local' or any(c in self.token for c in '\r\n'):
            raise ValueError('Use the real runtime token')
        if not isinstance(self.model,str) or not self.model.startswith('meterless/') or len(self.model)<=10:
            raise ValueError('Choose a discovered meterless routing ID')

    @classmethod
    def from_env(cls,*,settings=None,legacy=False):
        stored=(settings or MeterlessSettings()).load()
        prefix='NIGHTSHIFT' if legacy else 'METERLESS'
        base=os.getenv(prefix+'_BASE_URL') or stored.get('base_url',DEFAULT_BASE_URL)
        model=os.getenv(prefix+'_MODEL') or stored.get('model','meterless/auto')
        stored_token=stored.get('meterless_runtime_token','') if parse_connection(base)[0]==stored.get('base_url') else ''
        token=os.getenv(prefix+'_API_KEY') or os.getenv('meterless_runtime_token') or os.getenv('METERLESS_RUNTIME_TOKEN') or stored_token
        state_dir=os.getenv('METERLESS_STATE_DIR')
        if not token and state_dir:
            try:token=(Path(state_dir)/'proxy-token').read_text().strip()
            except OSError:raise ExecutionStopped('Cannot read configured Meterless proxy-token') from None
        return cls(base,token,model)


class MeterlessUnavailable(ExecutionStopped):
    def __init__(self,status):
        self.status=status
        super().__init__('Meterless Runtime '+status+('; paste the real runtime token' if status=='unauthorized' else ''))


def http_transport(method,url,headers,body,timeout):
    """Return status even on 401/403. Never surface secret-bearing error bodies."""
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    req=urllib.request.Request(url,data=json.dumps(body).encode() if body is not None else None,headers=headers,method=method)
    try:
        with urllib.request.build_opener(NoRedirect()).open(req,timeout=timeout) as response:
            raw=response.read(2_000_001)
            if len(raw)>2_000_000:return response.status,None
            try:return response.status,json.loads(raw)
            except ValueError:return response.status,None
    except urllib.error.HTTPError as error:return error.code,None
    except (urllib.error.URLError,TimeoutError,ConnectionError,OSError):return 0,None


class MeterlessRuntime:
    provider_id=PROVIDER_ID
    name=PROVIDER_NAME
    def __init__(self,config=None,*,transport=None,budget=None):
        self.config=config or RuntimeConfig.from_env();self.transport=transport or http_transport
        self.budget=budget;self.status='offline';self.models=[];self.discovered=False
    def _request(self,method,path,body=None,*,timeout=3):
        headers={'Authorization':'Bearer '+self.config.token,'meterless-app':APP_ID,'Content-Type':'application/json'}
        if method=='POST':headers['meterless-scope']='user'
        if self.budget:
            timeout=self.budget.timeout(timeout)
            if method=='GET':self.budget.consume('tool','meterless.models')
        try:return self.transport(method,self.config.base_url+path,headers,body,timeout)
        except ExecutionStopped:raise
        except Exception:return 0,None
    def probe(self,*,timeout=3):
        code,data=self._request('GET','/models',timeout=timeout)
        self.models=[]
        if code in {401,403}:self.status='unauthorized'
        else:
            rows=data.get('data',[]) if isinstance(data,dict) else []
            if isinstance(rows,list):
                self.models=list(dict.fromkeys(row['id'] for row in rows if isinstance(row,dict) and isinstance(row.get('id'),str) and row['id'].startswith('meterless/') and len(row['id'])>10))
            self.status='online' if code==200 and self.models else 'offline'
        self.discovered=True
        reason='connected' if self.status=='online' else 'runtime_token_required' if self.status=='unauthorized' else 'no_meterless_routing_ids' if code==200 else 'connection_unavailable' if code==0 else 'runtime_http_error'
        return {'provider':PROVIDER_ID,'name':PROVIDER_NAME,'status':self.status,'base_url':self.config.base_url,
                'models':self.models.copy(),'requires_token':self.status=='unauthorized','reason':reason,'http_status':code}
    def chat(self,messages,*,model=None,**options):
        if not self.discovered:self.probe()
        if self.status!='online':raise MeterlessUnavailable(self.status)
        selected=model or self.config.model
        if selected not in self.models:raise ExecutionStopped('Selected Meterless routing ID is not advertised by this runtime')
        if not isinstance(messages,list) or not messages or any(not isinstance(m,dict) or not isinstance(m.get('content'),str) for m in messages):
            raise ValueError('Text messages must retain string content')
        code,data=self._request('POST','/chat/completions',{'model':selected,'messages':messages,'stream':False,**options},timeout=CHAT_TIMEOUT)
        if code in {401,403}:self.status='unauthorized';raise MeterlessUnavailable(self.status)
        if code!=200 or not isinstance(data,dict):self.status='offline';raise MeterlessUnavailable(self.status)
        return data
    def complete_text(self,prompt,*,model='meterless/auto'):
        if not isinstance(prompt,str):raise ValueError('Text prompt must be a string')
        if self.budget:self.budget.consume('model','meterless.text')
        response=self.chat([{'role':'user','content':prompt}],model=model)
        try:content=response['choices'][0]['message']['content']
        except (KeyError,TypeError,IndexError):self.status='offline';raise MeterlessUnavailable('offline') from None
        if not isinstance(content,str):self.status='offline';raise MeterlessUnavailable('offline')
        return content


def auto_detect(*,token='',settings=None,transport=None,timeout=.35):
    """Probe only the documented loopback candidates; save first reachable auth/online hit."""
    settings=settings or MeterlessSettings()
    for port in (8088,8090,8787,11434):
        for host in ('127.0.0.1','localhost','[::1]'):
            base=f'http://{host}:{port}/v1'
            runtime=MeterlessRuntime(RuntimeConfig(base,token),transport=transport)
            result=runtime.probe(timeout=timeout)
            if result['status'] in {'online','unauthorized'}:
                settings.save(base_url=base,token=token,model='meterless/auto')
                return result
    return {'provider':PROVIDER_ID,'name':PROVIDER_NAME,'status':'offline','models':[],
            'requires_token':False,'reason':'LIVE_NIGHTSHIFT_NOT_AVAILABLE'}
