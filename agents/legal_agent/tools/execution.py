"""Permissions and budgets enforced outside agent prompts."""
import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from pydantic import BaseModel, Field


class ExecutionLimits(BaseModel):
    investigation_timeout_seconds: float = Field(default=300, gt=0, le=900)
    max_total_tool_calls: int = Field(default=160, ge=0, le=300)
    cleanup_timeout_seconds: float = Field(default=15, gt=0, le=30)
    max_revision_cycles: int = Field(default=2, ge=0, le=2)
    max_tool_calls: int = Field(default=10, ge=0, le=10)
    tool_timeout_seconds: float = Field(default=5, gt=0, le=60)
    max_retries: int = Field(default=1, ge=0, le=2)
    model_timeout_seconds: float = Field(default=30, gt=0, le=60)
    max_model_calls: int = Field(default=9, ge=0, le=9)

    @classmethod
    def from_env(cls):
        fields = {'max_revision_cycles':'LEGAL_MAX_REVISIONS', 'max_tool_calls':'LEGAL_MAX_TOOL_CALLS',
                  'investigation_timeout_seconds':'INVESTIGATION_TIMEOUT', 'max_total_tool_calls':'INVESTIGATION_MAX_TOOL_CALLS',
                  'tool_timeout_seconds':'LEGAL_TOOL_TIMEOUT', 'max_retries':'LEGAL_MAX_RETRIES',
                  'model_timeout_seconds':'LLM_TIMEOUT', 'max_model_calls':'LEGAL_MAX_MODEL_CALLS'}
        return cls(**{k:os.environ[v] for k,v in fields.items() if v in os.environ})


class ExecutionStopped(RuntimeError):
    pass


class ExecutionBudget:
    """One investigation budget shared by data access and the legal workflow.

    Waiting deadlines cannot kill Python threads. Real transports also receive
    remaining-time limits; late DDL cleanup uses a separate, bounded allowance.
    """
    def __init__(self, limits=None, *, clock=time.monotonic, trace=None):
        if __package__ and __package__.startswith("agents.legal_agent"):
            from ..events import ActivityTrace
        else:
            from events import ActivityTrace
        self.trace=trace or ActivityTrace()
        self.limits=limits or ExecutionLimits.from_env()
        self.clock=clock;self.started=clock()
        self.deadline=self.started+self.limits.investigation_timeout_seconds
        self.tool_calls=0;self.model_calls=0;self.events=[]
        self._lock=threading.Lock()

    def check(self):
        if self.clock()>=self.deadline:
            self.trace.emit('budget.exhausted',resource='deadline')
            raise ExecutionStopped('Aggregate investigation deadline exhausted')

    def timeout(self, ceiling):
        self.check()
        return max(.001,min(ceiling,self.deadline-self.clock()))

    def consume(self,kind,name):
        with self._lock:
            self.check()
            field='model_calls' if kind=='model' else 'tool_calls'
            limit=self.limits.max_model_calls if kind=='model' else self.limits.max_total_tool_calls
            if getattr(self,field)>=limit:
                self.trace.emit('budget.exhausted',resource=kind)
                raise ExecutionStopped('Aggregate '+kind+' call budget exhausted')
            setattr(self,field,getattr(self,field)+1)
            self.events.append({'kind':kind,'name':name,'status':'started'})
            self.trace.emit(kind+'.invoked',operation=name)

    def invoke(self,fn,*args,ceiling=30,on_late=None,**kwargs):
        wait=self.timeout(ceiling)
        pool=ThreadPoolExecutor(max_workers=1)
        future=pool.submit(fn,*args,**kwargs)
        try:
            result=future.result(timeout=wait)
            self.check()
            self.trace.emit("operation.completed",operation=getattr(fn,"__name__","operation"))
            return result
        except FutureTimeout:
            if on_late:
                future.add_done_callback(lambda completed:on_late())
            self.trace.emit('operation.failed',status='deadline')
            raise ExecutionStopped('Aggregate operation waiting deadline exhausted') from None
        except Exception as error:
            self.trace.emit('operation.failed',error_type=type(error).__name__)
            raise
        finally:
            pool.shutdown(wait=False,cancel_futures=True)

    def snapshot(self):
        return {'run_id':self.trace.run_id,'tool_calls':self.tool_calls,'model_calls':self.model_calls,
                'elapsed_seconds':max(0,self.clock()-self.started),
                'deadline_seconds':self.limits.investigation_timeout_seconds}


class ReadOnlySearch:
    """Only exposes legal_search. Exact read-only repeats use an investigation cache.

    The timeout bounds caller latency. Running Python thread code cannot be killed;
    remote adapters must also implement transport deadlines and read-only credentials.
    """
    def __init__(self, tool, limits, budget=None):
        self._tool, self.limits = tool, limits
        self.sources = tool.sources
        self.calls = 0
        self.cache = {}
        self.events = []
        self.budget=budget or ExecutionBudget(limits)

    def search(self, query, limit=5):
        if not isinstance(query, str) or not 0 < len(query) <= 4000 or not 1 <= limit <= 20:
            raise ValueError('Invalid legal_search arguments')
        key = (query, limit)
        if key in self.cache:
            self.budget.check()
            return self.cache[key]
        for attempt in range(self.limits.max_retries + 1):
            if self.calls >= self.limits.max_tool_calls:
                raise ExecutionStopped('Research tool budget exhausted')
            self.calls += 1
            self.budget.consume('tool','legal_search')
            pool = ThreadPoolExecutor(max_workers=1)
            future = pool.submit(self._tool.search, query, limit=limit)
            try:
                result = future.result(timeout=self.budget.timeout(self.limits.tool_timeout_seconds))
                self.budget.check()
                if __package__ and __package__.startswith("agents.legal_agent"):
                    from ..models.schemas import LegalSourceHit
                else:
                    from models.schemas import LegalSourceHit
                result = [LegalSourceHit.model_validate(h.model_dump() if hasattr(h,'model_dump') else h) for h in result]
                self.cache[key] = result
                self.events.append({'tool':'legal_search','query':query,'attempt':attempt,'status':'ok'})
                self.budget.trace.emit('tool.completed',operation='legal_search',query=query,count=len(result),attempt=attempt,authority_ids=[h.source.id for h in result],excerpt_ids=[h.source.id for h in result if h.source.excerpt])
                return result
            except (TimeoutError, ConnectionError, FutureTimeout):
                self.events.append({'tool':'legal_search','query':query,'attempt':attempt,'status':'transient_failure'})
                self.budget.trace.emit('tool.failed',operation='legal_search',attempt=attempt)
                if attempt == self.limits.max_retries:
                    raise ExecutionStopped('Legal search unavailable after bounded retries') from None
            finally:
                pool.shutdown(wait=False, cancel_futures=True)


class PropertyQuery(BaseModel):
    """Future database adapter input, never accepts arbitrary SQL."""
    template: str = 'by_bin'
    bin: str = Field(pattern=r'^\d{7}$')

    def statement(self):
        if self.template != 'by_bin':
            raise ValueError('Query template not allowed')
        return 'SELECT * FROM building_records WHERE bin = :bin', {'bin':self.bin}
