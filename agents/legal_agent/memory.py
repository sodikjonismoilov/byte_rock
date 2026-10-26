"""Legal-local H-MEM bridge. Keeper remains authoritative; no evidence store here."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
if __package__ and __package__.startswith('agents.legal_agent'):
    from .tools.execution import ExecutionStopped
else:
    from tools.execution import ExecutionStopped


class LegalMemory:
    def __init__(self,directory,*,node='node',allow_sample=False):
        self.directory=Path(directory).resolve();self.node=node;self.allow_sample=allow_sample
        self.bridge=Path(__file__).resolve().parents[2]/'scripts'/'hmem_bridge.mjs'
    def _scope(self,task,context):
        identity=context.identity
        if not identity or identity.verification_status not in {'verified','sample'}:raise ValueError('Memory requires resolved identity')
        if context.data_mode in {'sample','mock'} and not self.allow_sample:raise ValueError('Sample memory requires explicit fixture opt-in')
        # No memory crosses the sample/live boundary or a building/unit boundary.
        data={'mode':'sample' if context.data_mode in {'sample','mock'} else 'official',
              'identifiers':identity.identifiers,'address':identity.canonical_address,'borough':identity.borough,'unit':identity.unit}
        return 'legal-building:'+hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
    def _call(self,operation,*,budget,**payload):
        budget.consume('tool','hmem.'+operation)
        timeout=budget.timeout(5)
        self.directory.mkdir(parents=True,exist_ok=True,mode=0o700)
        fd=os.open(self.directory/'.lock',os.O_RDWR|os.O_CREAT,0o600)
        started=time.monotonic()
        try:
            while True:
                budget.check()
                try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);break
                except BlockingIOError:
                    if time.monotonic()-started>=timeout:raise ExecutionStopped('H-MEM lock deadline exhausted')
                    time.sleep(.01)
            request={'operation':operation,'directory':str(self.directory),**payload}
            process=subprocess.run([self.node,'--experimental-transform-types',str(self.bridge)],input=json.dumps(request),
                capture_output=True,text=True,timeout=budget.timeout(max(.001,timeout-(time.monotonic()-started))))
            if process.returncode:raise ExecutionStopped('H-MEM operation failed; original evidence remains authoritative')
            result=json.loads(process.stdout)
            if not result.get('ok'):raise ExecutionStopped('H-MEM operation failed')
            budget.trace.emit('memory.operation_completed',operation=operation)
            return result['result']
        except (OSError,ValueError,subprocess.TimeoutExpired):
            raise ExecutionStopped('H-MEM unavailable or exceeded its deadline') from None
        finally:
            fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)
    def retrieve(self,task,context,*,budget,limit=3):
        scope=self._scope(task,context)
        result=self._call('query',budget=budget,scope=scope,query=task.question,limit=min(3,max(1,limit)))
        held=set(context.reconciliation.rejected_ids+context.reconciliation.quarantined_ids) if context.reconciliation else set()
        hints=[];seen=set()
        for row in result['memories']:
            memory=row['memory']
            try:content=json.loads(memory['content'])
            except ValueError:continue
            if held & set(content.get('evidence_ids',[])):continue
            key=(content['summary'],tuple(content.get('evidence_ids',[])),tuple(content.get('authority_ids',[])),content['trust_label'])
            if key in seen:continue
            seen.add(key)
            hints.append({'memory_id':memory['id'],'task_id':task.task_id,'summary':content['summary'],
                'evidence_ids':content.get('evidence_ids',[]),'authority_ids':content.get('authority_ids',[]),
                'provenance':memory['provenance'],'timestamp':memory['timestamp'],'trust_label':content['trust_label'],
                'relevance':row['relevance'],'source':memory['source'],'limitations':content.get('limitations',[]),'is_evidence':False})
        budget.trace.emit('memory.retrieved',count=len(hints),trusted_as_evidence=False)
        return hints
    def store(self,task,context,result,*,budget):
        if not result.critic_outcome or result.critic_outcome.value=='BLOCKED' or result.status.value=='error':
            budget.trace.emit('memory.storage_skipped',reason='unverified_or_blocked');return []
        scope=self._scope(task,context)
        accepted=set(result.reconciliation.accepted_ids) if result.reconciliation else set()
        registry={e.evidence_id:e for e in context.evidence}
        authorities={s.id:s for s in result.legal_sources}
        saved=[]
        if result.status.value=='completed' and result.critic_outcome.value=='PASS':
            for finding in result.findings[:5]:
                refs=set(finding.evidence_ids)
                authority_ids={sid for c in finding.legal_conclusions for sid in c.source_ids}
                if not finding.valid or not refs or not refs<=accepted or not refs<=registry.keys():continue
                if not authority_ids<=authorities.keys() or any(not c.supported or not c.source_ids for c in finding.legal_conclusions):continue
                urls=[registry[e].metadata.get('source_url') for e in sorted(refs)]
                if not all(urls):continue
                urls += [authorities[s].url for s in sorted(authority_ids)]
                content={'summary':finding.summary[:1000],'evidence_ids':sorted(refs),'authority_ids':sorted(authority_ids),
                         'trust_label':'validated_sample_finding' if context.data_mode in {'sample','mock'} else 'critic_validated_finding',
                         'limitations':result.caveats,'is_evidence':False}
                saved.append(self._add(scope,content,urls,task,result,budget))
        else:
            # Store the verified fact of a review gap, never its unsupported draft claims.
            codes=sorted({i.code for i in result.critic_issues})
            content={'summary':'Prior review remained '+result.critic_outcome.value+'. Recheck support and missing information; do not reuse its draft conclusions. Review issues: '+', '.join(codes),
                     'evidence_ids':[],'authority_ids':[],'trust_label':'review_feedback_only','is_evidence':False}
            saved.append(self._add(scope,content,['legal-review:'+task.task_id],task,result,budget,layer='working'))
        budget.trace.emit('memory.stored',count=len(saved),authoritative_evidence=False)
        return saved
    def _add(self,scope,content,refs,task,result,budget,layer='long_term'):
        content={**content,'request':task.question[:1000]}
        key=hashlib.sha256(json.dumps({'scope':scope,'content':content,'refs':refs},sort_keys=True).encode()).hexdigest()
        request={'content':json.dumps(content,sort_keys=True),'type':'factual' if layer=='long_term' else 'general',
            'layer':layer,'source':'legal:'+task.task_id,'confidence':.7,'chatId':scope,'goalRunId':budget.trace.run_id,
            'provenance':{'origin':'plan_completion','learnedAt':int(time.time()*1000),
                          'label':content['trust_label']+'; memory is not official evidence','refs':refs},
            'derivedFrom':content['evidence_ids'],'tags':['project:signsafe',content['trust_label']]}
        return self._call('add',budget=budget,input=request,idempotency_key=key)
    def invalidate(self,task,context,memory_id,*,budget,superseded_by=None):
        result=self._call('invalidate',budget=budget,scope=self._scope(task,context),memory_id=memory_id,superseded_by=superseded_by)
        budget.trace.emit('memory.invalidated',memory_id=memory_id)
        return result
