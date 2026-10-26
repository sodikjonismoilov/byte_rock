/** Isolated upstream H-MEM proof, not a shared Keeper service or production store.
 * node --experimental-transform-types scripts/smoke_meterless_reference.mjs /tmp/byte-rock-meterless-reference
 */
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import assert from 'node:assert/strict';
const upstream=process.argv[2];
if(!upstream)throw new Error('Pass an inspected official Meterless checkout path');
const { HMEM }=await import(pathToFileURL(resolve(upstream,'engines/hmem/reference/src/index.ts')).href);
const directory=mkdtempSync(resolve(tmpdir(),'byte-rock-hmem-proof-'));
try {
  const engine=new HMEM({persistDir:directory,actor:'legal-reference-smoke'});
  const saved=engine.add({content:'DEVELOPMENT FIXTURE: legal research must preserve official evidence references and uncertainty.',
    type:'factual',layer:'long_term',confidence:0.7,source:'legal-reference-smoke-fixture',chatId:'smoke-only',
    provenance:{origin:'manual',learnedAt:Date.now(),label:'Fixture used for upstream engine verification',refs:['https://data.cityofnewyork.us/resource/wvxf-dwi5.json']}});
  const hydrated=new HMEM({persistDir:directory,actor:'legal-reference-smoke'});
  assert.equal(hydrated.store.get(saved.id)?.source,'legal-reference-smoke-fixture');
  const recalled=hydrated.query('legal official evidence uncertainty',{chatId:'smoke-only',threshold:0,topN:3});
  assert(recalled.memories.some(row=>row.memory.id===saved.id));
  hydrated.store.update(saved.id,{confidence:0,supersededBy:'invalidated-by-reference-smoke'});
  assert.equal(hydrated.store.get(saved.id)?.confidence,0);
  console.log(JSON.stringify({engine:'official Meterless H-MEM reference',data_mode:'fixture',production_integration:false,
    operations:['add','persist','hydrate','query','invalidate via store.update'],
    persisted_read_verified:true,retrieval_verified:true,invalidation_verified:true,
    ledger_entries:hydrated.ledger.all().length}));
} finally {rmSync(directory,{recursive:true,force:true});}
