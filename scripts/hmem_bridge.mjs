/** Small JSON-stdin bridge to the pinned official H-MEM engine. No model/network. */
import { HMEM } from '../agents/legal_agent/vendor/hmem/src/index.ts';
import { readFileSync } from 'node:fs';
process.umask(0o077);
try {
  const request=JSON.parse(readFileSync(0,'utf8'));
  if(typeof request.directory!=='string')throw new Error('Directory required');
  const engine=new HMEM({persistDir:request.directory,actor:'signsafe-legal'});
  let result;
  if(request.operation==='query'){
    result=engine.query(request.query,{chatId:request.scope,topN:request.limit??3,threshold:0.1});
    result.memories=result.memories.filter(r=>r.memory.chatId===request.scope&&!r.memory.supersededBy&&r.memory.confidence>0);
    delete result.context; // Python constructs a bounded, provenance-preserving projection.
  }else if(request.operation==='add'){
    const input=request.input;
    const key=request.idempotency_key;
    if(input.supersedes){const prior=engine.store.get(input.supersedes);if(!prior||prior.chatId!==input.chatId)throw new Error('Invalid supersession scope');}
    const existing=engine.store.all().find(m=>m.tags.includes('idempotency:'+key));
    result=existing??engine.add({...input,tags:[...(input.tags??[]),'idempotency:'+key]});
    if(input.supersedes&&!existing){
      const prior=engine.store.get(input.supersedes);
      if(!prior||prior.chatId!==input.chatId)throw new Error('Invalid supersession scope');
      engine.store.update(prior.id,{supersededBy:result.id,confidence:0});
    }
  }else if(request.operation==='invalidate'){
    const memory=engine.store.get(request.memory_id);
    if(!memory||memory.chatId!==request.scope)throw new Error('Unknown scoped memory');
    if(request.superseded_by){const replacement=engine.store.get(request.superseded_by);if(!replacement||replacement.chatId!==memory.chatId)throw new Error('Invalid replacement scope');}
    result=engine.store.update(memory.id,{confidence:0,supersededBy:request.superseded_by??'invalidated',tags:[...memory.tags,'invalidated']});
  }else if(request.operation==='all'){
    result=engine.store.all().filter(m=>m.chatId===request.scope);
  }else throw new Error('Unsupported operation');
  console.log(JSON.stringify({ok:true,result}));
}catch(error){console.log(JSON.stringify({ok:false,error:'hmem_operation_failed'}));process.exitCode=1;}
