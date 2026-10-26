"""Append-only activity contracts. Events contain decisions, never raw prompts/records."""
from datetime import datetime, UTC
import copy
import json
import os
from pathlib import Path
import re
import threading
from typing import Protocol
from uuid import uuid4


class EventSink(Protocol):
    def append(self, event: dict) -> None: ...


def sanitize(value, key=''):
    metrics={'prompt_tokens','completion_tokens','total_tokens','cached_tokens','reasoning_tokens','audio_tokens','accepted_prediction_tokens','rejected_prediction_tokens'}
    if key in metrics and (value is None or isinstance(value,(int,float))):return value
    if key in {'prompt_tokens_details','completion_tokens_details'} and isinstance(value,dict):
        return {str(k):sanitize(v,str(k)) for k,v in value.items()}
    if re.search(r'key|token|password|secret|authorization|cookie|prompt|raw_record|description|address|reasoning',key,re.I):
        return '[REDACTED]'
    if isinstance(value,dict):return {str(k):sanitize(v,str(k)) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [sanitize(v,key) for v in value]
    if isinstance(value,str):
        for name,secret in os.environ.items():
            if re.search(r'KEY|TOKEN|PASSWORD|SECRET',name) and len(secret)>=4:value=value.replace(secret,'[REDACTED]')
        value=re.sub(r'(?i)bearer\s+\S+','Bearer [REDACTED]',value)
        value=re.sub(r'(?i)(https?://)[^/@\s]+:[^/@\s]+@',r'\1[REDACTED]@',value)
        value=re.sub(r'(?i)([?&](?:api_key|token|password|secret)=)[^&\s]+',r'\1[REDACTED]',value)
        value=re.sub(r'(?i)(/connect#k=)[^\s]+',r'\1[REDACTED]',value)
        return value[:2000]
    if value is None or isinstance(value,(bool,int,float)):return value
    return str(type(value).__name__)


class InMemoryEventSink:
    def __init__(self):self._events=[];self._lock=threading.Lock()
    def append(self,event):
        with self._lock:self._events.append(copy.deepcopy(sanitize(event)))
    @property
    def events(self):
        with self._lock:return copy.deepcopy(self._events)


class JSONLEventSink:
    def __init__(self,path):self.path=Path(path);self._lock=threading.Lock()
    def append(self,event):
        line=json.dumps(sanitize(event),ensure_ascii=False,default=str)+'\n'
        with self._lock:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            fd=os.open(self.path,os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
            with os.fdopen(fd,'a',encoding='utf-8') as stream:stream.write(line)


class ActivityTrace:
    def __init__(self,sink=None,*,run_id=None,task_id='address-investigation'):
        self.sink=sink or InMemoryEventSink()
        self.memory=self.sink if isinstance(self.sink,InMemoryEventSink) else InMemoryEventSink()
        self.run_id=run_id or str(uuid4());self.task_id=task_id
    def emit(self,event_type,**data):
        event={'schema_version':'legal.activity.v1','event_id':str(uuid4()),'run_id':self.run_id,
               'task_id':self.task_id,'timestamp':datetime.now(UTC).isoformat(),'type':event_type,'data':sanitize(data)}
        self.memory.append(event)
        if self.sink is not self.memory:self.sink.append(event)
        return event['event_id']

    @property
    def events(self):return self.memory.events
