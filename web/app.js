// SignSafe demo page. Everything shown here comes from the run's real trace.jsonl and report files:
// nothing on this page invents agent activity. Crew names are a presentation layer; each card also
// shows the real role and whether it runs on rules, Zetaris or a model.

const $ = (selector, root = document) => root.querySelector(selector);

function el(tag, attrs, ...kids) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value == null || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? '' : value);
  }
  for (const kid of kids.flat()) {
    if (kid == null || kid === false) continue;
    node.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return node;
}
const safeUrl = (u) => (typeof u === 'string' && /^https?:\/\//.test(u) ? u : null);
const mmss = (s) => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;

const CREW = [
  { id: 'surveyor', name: 'Surveyor', role: 'Identity resolution', engine: 'rules', hue: 210, blurb: 'Works out exactly which building you mean (BBL, BIN, HPD id).' },
  { id: 'archivist', name: 'Archivist', role: 'Records via Zetaris', engine: 'zetaris', hue: 188, blurb: 'Pulls the city’s records through the Zetaris data layer.' },
  { id: 'warden', name: 'Warden', role: 'Critic · rules R1–R10', engine: 'rules', hue: 6, blurb: 'Throws out any record that does not belong to this building.' },
  { id: 'pathfinder', name: 'Pathfinder', role: 'Planner', engine: 'model', hue: 265, blurb: 'Plans which legal and safety questions are worth asking.' },
  { id: 'bloodhound', name: 'Bloodhound', role: 'Researcher', engine: 'model', hue: 32, blurb: 'Chases the evidence behind each question, with citations.' },
  { id: 'magistrate', name: 'Magistrate', role: 'Legal Critic', engine: 'model', hue: 300, blurb: 'Sends weak drafts back, or refuses to conclude without proof.' },
  { id: 'assessor', name: 'Assessor', role: 'Verdict rules', engine: 'rules', hue: 145, blurb: 'Stamps the placard from fixed, checkable rules. Never says “safe”.' },
];
const CREW_BY_ID = Object.fromEntries(CREW.map((c) => [c.id, c]));

const VERDICTS = {
  'WALK AWAY': { level: 'walk', line: 'The city’s records show serious, unresolved problems at this building.' },
  'CAUTION': { level: 'caution', line: 'The records show issues worth asking the landlord about before you sign.' },
  'NO FLAGS FOUND': { level: 'clear', line: 'None of our rules fired on the records we could check. That is not a clean bill of health.' },
  'NOT ENOUGH DATA': { level: 'nodata', line: 'We could not check enough sources to say anything fair. Missing data is not good news.' },
};
const CATEGORY_LABELS = {
  habitability: 'Living conditions', building_safety: 'Building safety', fire_safety: 'Fire safety',
  housing_enforcement: 'City enforcement', eviction_litigation: 'Evictions and litigation',
  tenant_protections: 'Tenant protections', property_identity: 'Building identity',
};
const GROUP_ORDER = ['habitability', 'housing_enforcement', 'building_safety', 'fire_safety', 'eviction_litigation', 'tenant_protections', 'property_identity'];
const QUIET_GROUPS = new Set(['property_identity', 'ownership', 'registration', 'other']);  // context, not conditions: folded by default
const prettyKey = (k) => (CATEGORY_LABELS[k] || String(k).replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase()));
const SEV_RANK = { C: 0, B: 1, A: 2 };
const DECISION_TYPES = new Set(['identity.decided', 'root_critic.decision', 'critic.decision', 'evidence.reconciled', 'verdict.rule_fired', 'verdict.decided', 'run.finished']);

const S = {
  cfg: null, mode: 'sample', job: null, next: 0, timer: null, tick: null, fails: 0, startedAt: 0, running: false,
  crew: {}, sources: new Map(), sourcesTotal: new Set(), warden: { accepted: 0, rejected: 0, held: 0 }, records: new Map(),
  models: new Set(), modelCalls: 0, eventCount: 0, t0: null, board: undefined, queue: [], address: '', verdictLevel: null,
  acceptedSeen: 0, boardSampled: false, lastDecisionToast: 0, seenRules: new Set(),
};

/* ---------- crew ---------- */
function engineTag(c) {
  if (c.engine === 'rules') return el('span', { class: 'tag rules', text: 'rules, no AI' });
  if (c.engine === 'zetaris') return el('span', { class: 'tag zet', text: 'Zetaris' });
  const names = [...S.models];
  let label = 'AI model';
  if (S.final) label = S.final.models_used?.length ? shortModel(S.final.models_used[0]) : 'deterministic';
  else if (names.length) label = shortModel(names[0]);
  return el('span', { class: 'tag model', text: label });
}
const shortModel = (m) => String(m).replace(/^nvidia\//, '');

function avatar(c) { return el('div', { class: 'avatar', style: `--h:${c.hue}`, 'aria-hidden': 'true', text: c.name[0] }); }

function renderCrewIntro() {
  $('#crewIntro').replaceChildren(...CREW.map((c) => el('li', null, avatar(c),
    el('div', null, el('h3', { text: c.name }), el('div', { class: 'role', text: c.role }), el('p', { text: c.blurb })))));
}

function renderStation(id) {
  const c = CREW_BY_ID[id], st = S.crew[id];
  const label = { waiting: 'waiting', working: 'working…', done: 'done', stopped: 'stopped', skipped: 'did not run' }[st.status];
  const node = $(`#st-${id}`) || el('div', { class: 'station', id: `st-${id}` });
  node.dataset.status = st.status;
  node.replaceChildren(avatar(c), el('div', null,
    el('div', { class: 'name', text: c.name }),
    el('div', { class: 'role' }, c.role, engineTag(c)),
    el('div', { class: 'status', text: label }),
    st.note ? el('div', { class: 'note', text: st.note }) : null));
  return node;
}
function renderCrew() {
  const rail = $('#crew');
  rail.replaceChildren(el('h2', { text: 'The crew' }), ...CREW.map((c) => renderStation(c.id)));
}
function patchCrew(id, patch) {
  S.crew[id] = { ...S.crew[id], ...patch };
  const node = $(`#st-${id}`);
  if (node) renderStation(id);
}
const refreshTags = () => CREW.forEach((c) => c.engine === 'model' && patchCrew(c.id, {}));

/* ---------- trace -> state ---------- */
function describe(ev) {
  const d = ev.data || {}, t = ev.type;
  const tone = (x) => ({ BLOCKED: 'bad', REVISE: 'warn', INCONCLUSIVE: 'warn', PASS: 'ok' }[x] || '');
  switch (t) {
    case 'run.started': return { text: `Run started · ${d.requested_provider || ''} · ${d.mode || ''}` };
    case 'investigation.started': return { text: 'Investigation started' };
    case 'identity.decided': return { text: `Identity ${d.status}${d.candidate_count != null ? ` (${plural(d.candidate_count, 'candidate')})` : ''}`, tone: d.status === 'verified' ? 'ok' : 'warn' };
    case 'source.retrieved': return { text: `${d.source}: ${d.status}${d.count != null ? ` · ${plural(d.count, 'record')}` : ''}`, tone: d.status === 'unavailable' ? 'warn' : '' };
    case 'root_critic.decision': return { text: `${d.decision} ${d.record_id || ''}${d.rule ? ` · ${d.rule}` : ''}${d.phase ? ` (${d.phase})` : ''}`, tone: /reject/i.test(d.decision) ? 'bad' : /accept/i.test(d.decision) ? 'ok' : 'warn' };
    case 'evidence.reconciled': return { text: `Reconciled: ${d.accepted} accepted, ${d.rejected} rejected, ${d.quarantined} held`, tone: d.rejected ? 'warn' : 'ok' };
    case 'agent.started': return { text: `${d.role} started${d.revision ? ` · revision ${d.revision}` : ''}` };
    case 'agent.completed': return { text: `${d.role} finished${d.revision ? ` · revision ${d.revision}` : ''}` };
    case 'plan.selected': return { text: `Plan: ${plural(d.questions ?? 0, 'question')}` };
    case 'critic.decision': return { text: `Legal Critic: ${d.outcome}${d.mode ? ` (${d.mode})` : ''}`, tone: tone(d.outcome) };
    case 'research.follow_up_stopped': return { text: `Follow-up research stopped: ${d.reason}` };
    case 'model.started': case 'model.completed': case 'model.failed':
      return { text: `${t.split('.')[1]} · ${d.model || 'model'}${d.role ? ` · ${d.role}` : ''}`, tone: t === 'model.failed' ? 'bad' : '' };
    case 'memory.retrieved': return { text: `Memory recalled: ${plural(d.count ?? 0, 'item')} (never treated as evidence)` };
    case 'memory.stored': return { text: `Memory stored: ${plural(d.count ?? 0, 'item')}` };
    case 'citations.audited': return { text: `Citations audited: ${d.claims_with_verified_support}/${d.cited_claims} verified` };
    case 'verdict.rule_fired': return { text: `Rule ${d.rule_id} fired · ${d.level}`, tone: d.level === 'WALK AWAY' ? 'bad' : 'warn' };
    case 'verdict.decided': return { text: `Verdict: ${d.verdict}`, tone: VERDICTS[d.verdict]?.level === 'walk' ? 'bad' : VERDICTS[d.verdict]?.level === 'caution' ? 'warn' : '' };
    case 'budget.exhausted': return { text: `Budget exhausted: ${d.resource}`, tone: 'warn' };
    case 'run.finished': return { text: `Run finished: ${d.status}${d.termination_reason ? ` · ${d.termination_reason}` : ''}`, tone: d.status === 'completed' ? 'ok' : 'warn' };
    default: { const j = JSON.stringify(d); return { text: j.length > 150 ? j.slice(0, 150) + '…' : j }; }
  }
}

const ROLE_TO_CREW = (role) => (/plan/i.test(role) ? 'pathfinder' : /research/i.test(role) ? 'bloodhound' : /critic|review/i.test(role) ? 'magistrate' : null);
const wardenNote = () => `${S.warden.accepted} accepted · ${S.warden.rejected} rejected · ${S.warden.held} held`;
function sourceCounts() {
  let checked = 0, unavailable = 0, manual = 0;
  for (const s of S.sources.values()) { if (s.status === 'manual_only') manual++; else if (s.status === 'unavailable' || s.status === 'budget_exhausted') unavailable++; else checked++; }
  return { checked, unavailable, manual, total: Math.max(S.sourcesTotal.size, S.sources.size) };
}
const sourceNote = () => { const c = sourceCounts(); return `${c.checked}/${c.total} sources checked${c.unavailable ? ` · ${c.unavailable} unavailable` : ''}${c.manual ? ` · ${c.manual} manual` : ''}`; };

function ingest(ev) {
  const d = ev.data || {}, t = ev.type;
  S.eventCount++;
  if (S.t0 == null && ev.ts) S.t0 = Date.parse(ev.ts);
  addTraceRow(ev);
  switch (t) {
    case 'investigation.started': patchCrew('surveyor', { status: 'working', note: 'Resolving the address…' }); break;
    case 'identity.decided':
      patchCrew('surveyor', { status: d.status === 'verified' || d.status === 'sample' ? 'done' : 'stopped', note: describe(ev).text }); break;
    case 'source.selected':
      S.sourcesTotal.add(d.source);
      if (S.crew.archivist.status === 'waiting') patchCrew('archivist', { status: 'working', note: 'Querying sources…' });
      break;
    case 'source.retrieved': {
      const rank = { retrieved: 3, no_records: 2, unavailable: 1 };
      const prev = S.sources.get(d.source);
      if (!prev || (rank[d.status] || 0) >= (rank[prev.status] || 0)) S.sources.set(d.source, { status: d.status, count: (d.status === 'retrieved' ? (prev?.count || 0) + (d.count || 0) : prev?.count || 0) });
      patchCrew('archivist', { status: 'working', note: sourceNote() });
      renderCounters();
      break;
    }
    case 'root_critic.decision': wardenDecision(d); break;
    case 'evidence.reconciled':
      patchCrew('archivist', { status: 'done', note: sourceNote() });
      patchCrew('warden', { status: 'done', note: wardenNote() });
      break;
    case 'agent.started': {
      const id = ROLE_TO_CREW(d.role || '');
      if (id) patchCrew(id, { status: 'working', note: d.revision ? `Revision ${d.revision}` : 'Working…' });
      if (id === 'pathfinder' && d.revision) toast('Sent back for revision', `Revision ${d.revision}`, 'warn');
      break;
    }
    case 'agent.completed': {
      const id = ROLE_TO_CREW(d.role || '');
      if (id) patchCrew(id, { status: 'done', note: S.crew[id].note === 'Working…' ? 'Finished' : S.crew[id].note });
      break;
    }
    case 'plan.selected': patchCrew('pathfinder', { note: `${plural(d.questions ?? 0, 'question')} planned` }); break;
    case 'research.follow_up_stopped': patchCrew('bloodhound', { note: `Follow-up stopped: ${String(d.reason).replace(/_/g, ' ')}` }); break;
    case 'critic.decision': {
      patchCrew('magistrate', { status: 'done', note: `Outcome: ${d.outcome}` });
      if (d.outcome === 'REVISE') toast('Magistrate', 'Draft sent back for revision', 'warn');
      else if (d.outcome === 'BLOCKED') toast('Magistrate', 'Refused: the draft is blocked', 'bad');
      else if (d.outcome === 'INCONCLUSIVE') toast('Magistrate', 'Will not conclude without proof', 'warn');
      break;
    }
    case 'model.started': case 'model.completed': case 'model.failed':
      if (d.model) { S.models.add(d.model); refreshTags(); if (S.mode !== 'sample') setPill('live'); }
      if (t === 'model.completed') S.modelCalls++;
      if (t === 'model.failed') toast('Model call failed', d.model || '', 'bad');
      renderCounters();
      break;
    case 'verdict.rule_fired':
      patchCrew('assessor', { status: 'working', note: `Rule ${d.rule_id} fired` });
      toast(`Rule ${d.rule_id}`, d.level, d.level === 'WALK AWAY' ? 'bad' : 'warn');
      break;
    case 'verdict.decided': {
      patchCrew('assessor', { status: 'done', note: d.verdict });
      const level = VERDICTS[d.verdict]?.level;
      if (level) { S.verdictLevel = level; S.board?.setVerdict(level); }
      break;
    }
    case 'budget.exhausted': toast('Budget exhausted', d.resource || '', 'warn'); break;
    default: break;
  }
}

function wardenDecision(d) {
  const id = d.record_id;
  if (!id) return;
  const dec = String(d.decision || '').toLowerCase();
  const state = dec.startsWith('accept') ? 'accepted' : dec.startsWith('reject') ? 'rejected' : 'held';
  const prev = S.records.get(id);
  if (prev) S.warden[prev.state]--;
  S.records.set(id, { state, rule: d.rule, phase: d.phase });
  S.warden[state]++;
  patchCrew('warden', { status: 'working', note: wardenNote() });
  // Rejections and holds are the story, so every one reaches the board. When the board is backed up, only
  // every 5th accepted record is drawn; the counters, the ledger and the evidence list still count them all.
  const skipCard = !prev && state === 'accepted' && S.queue.length > 24 && (S.acceptedSeen++ % 5 !== 0);
  if (skipCard) { if (!S.boardSampled) { S.boardSampled = true; noteSampling(); } }
  else { if (!prev) S.queue.push(['add', id]); S.queue.push(['resolve', id, state]); }
  renderLedger();
  if (state !== 'accepted') {
    const now = Date.now(), firstOfRule = !S.seenRules.has(d.rule);  // each rule announces itself once, then toasts are throttled
    if (firstOfRule || now - S.lastDecisionToast > 1800) {
      S.seenRules.add(d.rule); S.lastDecisionToast = now;
      toast(state === 'rejected' ? 'REJECTED' : 'HELD', `${id}${d.rule ? ` · rule ${d.rule}` : ''}`, state === 'rejected' ? 'bad' : 'warn');
    }
  }
  renderCounters();
}

/* ---------- UI bits ---------- */
function toast(label, text, tone = '') {
  const box = $('#toasts');
  const key = `${label}|${text}`;
  if ([...box.children].some((n) => n.dataset.key === key)) return;  // never stack identical toasts
  const node = el('div', { class: `toast ${tone}`, 'data-key': key }, el('b', { text: label }), text ? ` ${text}` : '');
  box.append(node);
  while (box.children.length > 3) box.firstChild.remove();
  setTimeout(() => node.remove(), 4800);
}
function renderCounters() {
  const c = sourceCounts();
  const box = $('#counters');
  const pill = (label, value) => el('div', { class: 'counter' }, el('b', { text: value }), label);
  box.replaceChildren(
    pill('sources checked', c.total ? `${c.checked}/${c.total}` : '0'),
    pill('records pinned', String(S.warden.accepted)),
    pill('rejected · held', `${S.warden.rejected} · ${S.warden.held}`),
    pill('model calls', String(S.modelCalls)),
    pill('elapsed', mmss(S.running ? (Date.now() - S.startedAt) / 1000 : S.elapsed || 0)));
}
let ledgerTimer = 0;
function renderLedger() {  // coalesced: a burst of decisions redraws the chips once
  if (ledgerTimer) return;
  ledgerTimer = setTimeout(() => { ledgerTimer = 0; drawLedger(); }, 150);
}
function drawLedger() {
  const box = $('#ledger');
  const all = [...S.records.entries()];
  const items = all.slice(-160);
  const earlier = all.length - items.length;
  box.replaceChildren(
    earlier > 0 ? el('span', { class: 'rec more', text: `… ${earlier} earlier records, all counted above` }) : null,
    ...items.map(([id, r]) => {
      const full = String(id).replace(/%7C/gi, '|');
      const shown = full.length > 34 ? `${full.slice(0, 33)}…` : full;
      return el('span', { class: `rec ${r.state}`, title: r.rule ? `${full} · rule ${r.rule}` : full, text: `${r.state === 'accepted' ? '✓' : r.state === 'rejected' ? '✗' : '⏸'} ${shown}` });
    }));
}
function noteSampling() {
  const sub = $('#hudSub');
  if (sub && !sub.textContent.includes('sample')) sub.textContent += ' · sampled view';
}
function addTraceRow(ev) {
  const info = describe(ev);
  const off = S.t0 != null && ev.ts ? (Date.parse(ev.ts) - S.t0) / 1000 : 0;
  const row = el('div', { class: `tr ${info.tone || ''}` }, el('span', { class: 'tm', text: mmss(Math.max(0, off)) }), el('span', { class: 'ty', text: ev.type }), el('span', { text: info.text }));
  if (DECISION_TYPES.has(ev.type)) row.dataset.d = '1';
  const box = $('#trace');
  const stick = box.scrollTop + box.clientHeight >= box.scrollHeight - 30;
  box.append(row);
  while (box.childElementCount > 5000) box.firstElementChild.remove();
  if (stick) box.scrollTop = box.scrollHeight;
  $('#underCount').textContent = `${S.eventCount} events`;
}

/* ---------- board ---------- */
async function ensureBoard() {
  if (S.board !== undefined) return S.board;
  try {
    const module = await import('/static/board.js');
    S.board = module.createBoard($('#board'), { reducedMotion: matchMedia('(prefers-reduced-motion: reduce)').matches });
  } catch (error) {
    S.board = null;
  }
  if (!S.board) $('#board').hidden = true;
  return S.board;
}
function pumpQueue() {
  if (!S.board) { S.queue.length = 0; return; }
  const perTick = 2 + Math.min(10, Math.floor(S.queue.length / 15));  // drain faster when the queue is long
  for (let i = 0; i < perTick && S.queue.length; i++) {
    const [op, id, state] = S.queue.shift();
    if (op === 'add') S.board.addRecord(id, id.split(':')[0]);
    else S.board.resolveRecord(id, state);
  }
}
setInterval(pumpQueue, 110);

/* ---------- run lifecycle ---------- */
function resetRun() {
  Object.assign(S, { next: 0, fails: 0, sources: new Map(), sourcesTotal: new Set(), warden: { accepted: 0, rejected: 0, held: 0 }, records: new Map(), models: new Set(), modelCalls: 0, eventCount: 0, t0: null, queue: [], final: null, elapsed: 0, verdictLevel: null, acceptedSeen: 0, boardSampled: false, lastDecisionToast: 0, seenRules: new Set() });
  S.crew = Object.fromEntries(CREW.map((c) => [c.id, { status: 'waiting', note: '' }]));
  S.board?.reset();
  $('#trace').replaceChildren(); $('#ledger').replaceChildren(); $('#toasts').replaceChildren();
  $('#result').hidden = true; $('#result').replaceChildren(); $('#errorBox').hidden = true; $('#downloads').replaceChildren();
  $('#underCount').textContent = ''; $('#under').open = false;
  renderCrew(); renderCounters();
}

async function startRun(payload) {
  const button = $('#go'); button.disabled = true;
  $('#formError').hidden = true;
  let response;
  try {
    response = await fetch('/api/runs', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(payload) });
  } catch (error) {
    button.disabled = false; return showFormError('Could not reach the SignSafe server. Is it still running?');
  }
  const body = await response.json().catch(() => ({}));
  button.disabled = false;
  if (!response.ok) return showFormError(body.error || 'Could not start the investigation.');

  S.job = body.id; S.address = payload.address; S.mode = payload.mode;
  $('#home').hidden = true; $('#case').hidden = false; $('#again').hidden = true;
  resetRun();
  $('#hudAddr').textContent = payload.address;
  $('#hudSub').textContent = `${payload.borough || 'Borough not given'}${payload.unit ? ` · unit ${payload.unit}` : ''} · ${payload.mode === 'sample' ? 'recorded demo' : 'live city data'}`;
  setPill(payload.mode === 'sample' ? 'sample' : 'live');
  S.running = true; S.startedAt = Date.now();
  await ensureBoard();
  clearInterval(S.tick); S.tick = setInterval(renderCounters, 1000);
  clearTimeout(S.timer); poll();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}
function showFormError(message) { const box = $('#formError'); box.textContent = message; box.hidden = false; }

async function poll() {
  try {
    const response = await fetch(`/api/runs/${S.job}?after=${S.next}`);
    if (!response.ok) throw new Error(String(response.status));
    const body = await response.json();
    S.fails = 0; S.elapsed = body.elapsed;
    body.events.forEach(ingest); S.next = body.next;
    renderCounters();
    if (body.state === 'running') S.timer = setTimeout(poll, 900);
    else finish(body);
  } catch (error) {
    S.fails++;
    if (S.fails > 6) { S.running = false; clearInterval(S.tick); showRunError('Lost connection to the SignSafe server.'); }
    else S.timer = setTimeout(poll, 1500);
  }
}

function showRunError(message) {
  for (const c of CREW) if (S.crew[c.id].status === 'working' || S.crew[c.id].status === 'waiting') patchCrew(c.id, { status: 'stopped' });
  const box = $('#errorBox'); box.textContent = message; box.hidden = false;
  $('#again').hidden = false;
}

function finish(body) {
  S.running = false; clearInterval(S.tick);
  if (body.state === 'error') { showRunError(body.error || 'The investigation failed.'); renderCounters(); return; }
  const r = body.result; S.final = r;
  if (r.coverage?.length) {  // the report's coverage list is authoritative: it includes sources the trace never selected
    S.sources = new Map(r.coverage.map((c) => [c.source, { status: ['retrieved', 'no_records', 'manual_only'].includes(c.status) ? c.status : 'unavailable', count: c.records_returned || 0 }]));
    S.sourcesTotal = new Set(S.sources.keys());
    patchCrew('archivist', { status: 'done', note: sourceNote() });
  }
  for (const c of CREW) {
    const st = S.crew[c.id].status;
    if (c.id === 'assessor') {
      if (r.verdict && st !== 'done') patchCrew('assessor', { status: 'done', note: r.verdict.verdict });
      else if (!r.verdict) patchCrew('assessor', { status: 'skipped', note: 'Verdict rules not installed in this build' });
    } else if (st === 'working') patchCrew(c.id, { status: 'done' });
    else if (st === 'waiting') patchCrew(c.id, { status: 'skipped', note: c.engine === 'model' ? 'Not needed for this run' : '' });
  }
  refreshTags();
  const level = r.verdict ? VERDICTS[r.verdict.verdict]?.level : null;
  if (level) { S.verdictLevel = level; S.board?.setVerdict(level); }
  setPill(r.data_mode === 'recorded_replay' ? 'sample' : 'live', r);
  drawLedger(); renderCounters(); renderResult(body); renderDownloads(body);
  $('#again').hidden = false;
  setTimeout(() => $('#result').scrollIntoView({ behavior: 'smooth', block: 'start' }), 500);
}

const placeOf = (r) => [r.address || S.address, r.borough].filter(Boolean).join(', ');

/* ---------- result ---------- */
function renderResult(body) {
  const r = body.result, v = r.verdict;
  const info = v ? VERDICTS[v.verdict] : null;
  const counted = new Set((v?.rules_fired || []).flatMap((x) => x.evidence_ids || []));
  const place = placeOf(r);
  $('#hudAddr').textContent = place;  // board title and placard show the same text

  const rules = (v?.rules_fired || []).map((rule) => el('li', { 'data-level': rule.level },
    el('b', { text: `${rule.rule_id} · ${rule.level}` }), ' ', rule.summary || '',
    el('div', null, ...(rule.evidence_ids || []).map((id) => el('code', { text: id })), ' ',
      ...(rule.source_urls || []).filter(safeUrl).slice(0, 3).map((u, i) => el('a', { href: u, target: '_blank', rel: 'noopener', text: `record ${i + 1} ↗` }), ' '))));
  const reasons = v?.basis?.not_enough_data_reasons || [];
  const cov = v?.basis?.coverage;
  const covText = cov && (cov.checked ?? cov.sources_checked) != null ? `Checked ${cov.checked ?? cov.sources_checked} of ${cov.machine_readable ?? cov.machine_readable_sources ?? '?'} machine-readable sources. ` : '';

  const also = (Array.isArray(v?.basis?.also_on_record) ? v.basis.also_on_record : []).filter((x) => typeof x === 'string' && x);
  const titleOf = new Map((r.coverage || []).map((c) => [c.source, c.title || c.source]));
  const partial = (Array.isArray(v?.basis?.partial_sources) ? v.basis.partial_sources : []).map((k) => titleOf.get(k) || String(k));

  const placard = el('article', { class: 'placard', 'data-level': info?.level || 'none' },
    el('header', null, el('span', { text: 'NYC renter inspection' }), el('span', { text: `Case ${String(r.run_id).slice(0, 8)}` })),
    el('div', { class: 'place', text: place }),
    el('div', { class: `stamp${(v ? v.verdict : 'Facts only').length > 11 ? ' long' : ''}`, text: v ? v.verdict : 'Facts only' }),
    el('p', { class: 'vline', text: info ? info.line : 'This build has no verdict rules installed, so you are looking at the checked records without a rating.' }),
    rules.length ? el('ul', { class: 'rules' }, rules) : null,
    reasons.length ? el('ul', { class: 'rules' }, reasons.map((x) => el('li', { 'data-level': 'NOTE', text: String(x) }))) : null,
    also.length ? el('div', { class: 'also' }, el('h4', { text: 'Also on record' }), el('ul', null, also.map((x) => el('li', { text: String(x) })))) : null,
    el('footer', null, covText, v?.disclaimer || 'Not a safety guarantee. Based only on recorded agency data; missing data is not good news.',
      partial.length ? el('div', { text: `Some results were truncated (${partial.join(', ')}), so counts may be higher than shown.` }) : null,
      r.data_mode === 'recorded_replay' ? el('div', { text: 'Data source: recorded replay (not live agency data).' }) : null));

  const groups = new Map();
  for (const f of r.findings || []) {
    const key = (f.categories || [])[0] || 'other';
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(f);
  }
  const isCounted = (f) => (f.evidence_ids || []).some((id) => counted.has(id));
  const rank = (f) => [isCounted(f) ? 0 : 1, /open/i.test(f.recorded_status || '') ? 0 : 1, SEV_RANK[String(f.severity || '').toUpperCase()] ?? 3];
  const byRank = (a, b) => { const x = rank(a), y = rank(b); for (let i = 0; i < 3; i++) if (x[i] !== y[i]) return x[i] - y[i]; return String(b.event_date || '').localeCompare(String(a.event_date || '')); };
  const ordered = [...groups.entries()].map(([key, list]) => [key, [...list].sort(byRank)])
    .sort((a, b) => (QUIET_GROUPS.has(a[0]) - QUIET_GROUPS.has(b[0])) || ((GROUP_ORDER.indexOf(a[0]) + 99) % 99 - (GROUP_ORDER.indexOf(b[0]) + 99) % 99) || b[1].length - a[1].length);
  const SHOW = 12;
  const groupNode = ([key, list]) => {
    const cards = list.map((f) => findingCard(f, isCounted(f)));
    const head = `${prettyKey(key)} · ${list.length}`;
    const body = el('div', { class: 'finds' }, cards.slice(0, SHOW));
    const rest = cards.length > SHOW ? el('details', { class: 'more' }, el('summary', { text: `Show the other ${cards.length - SHOW}` }), el('div', { class: 'finds' }, cards.slice(SHOW))) : null;
    if (QUIET_GROUPS.has(key)) return el('details', { class: 'group quiet' }, el('summary', { text: head }), body, rest);
    return el('div', { class: 'group' }, el('h3', { text: head }), body, rest);
  };
  // Apartment-level records the Critic holds (R8, no unit requested) but the verdict counts. Optional field.
  const apt = v?.basis?.apartment_level, aptRecords = Array.isArray(apt?.records) ? apt.records : [];
  const aptNode = () => {
    const cards = aptRecords.map((a) => findingCard({
      severity: a.class, recorded_status: a.status, event_date: a.inspection_date, evidence_ids: [a.evidence_id], source_url: a.source_url,
      description: `${/open/i.test(a.status || '') ? 'Open' : 'Recorded'} violation${a.class ? ` (Class ${String(a.class).toUpperCase()})` : ''} recorded for an individual apartment.`,
    }, /open/i.test(a.status || '') && ['B', 'C'].includes(String(a.class || '').toUpperCase()), a.apartment));
    const total = Math.max(aptRecords.length, (Number(apt.open_class_c) || 0) + (Number(apt.open_class_b) || 0));
    const rest = cards.length > SHOW ? el('details', { class: 'more' }, el('summary', { text: `Show the other ${cards.length - SHOW}` }), el('div', { class: 'finds' }, cards.slice(SHOW))) : null;
    return el('div', { class: 'group' }, el('h3', { text: `Apartment-level records · ${total}` }),
      el('p', { class: 'sub', text: 'Recorded for individual apartments. Held out of the list above, but counted in the verdict.' }),
      el('div', { class: 'finds' }, cards.slice(0, SHOW)), rest);
  };
  const isQuiet = ([key]) => QUIET_GROUPS.has(key);
  const evidence = el('section', { class: 'card' }, el('h2', { text: 'The evidence' }),
    el('p', { class: 'sub', text: r.findings?.length ? `${plural(r.findings.length, 'record')} survived the Warden. Records outlined in red were counted in the verdict.` : 'No records survived for this building. That is a query result, not proof of no problems.' }),
    ...ordered.filter((g) => !isQuiet(g)).map(groupNode), aptRecords.length ? aptNode() : null, ...ordered.filter(isQuiet).map(groupNode));

  const buckets = { retrieved: [], no_records: [], manual_only: [], unavailable: [] };
  for (const c of r.coverage || []) (buckets[c.status] || buckets.unavailable).push(c);
  const srcRow = (c, s) => el('div', { class: 'src', 'data-s': s, title: c.reason || '' }, el('span', { text: c.title || c.source }), el('span', { class: 'st', text: s === 'retrieved' ? `${c.records_returned ?? ''} found` : s === 'no_records' ? 'none found' : s === 'manual_only' ? 'CHECK MANUALLY' : 'COULD NOT CHECK' }));
  const checked = el('section', { class: 'card' }, el('h2', { text: 'What we checked' }),
    el('p', { class: 'sub', text: 'Every source is listed, including the ones we could not reach. Unchecked is unknown, never safe.' }),
    el('div', { class: 'checked-grid' }, buckets.retrieved.map((c) => srcRow(c, 'retrieved')), buckets.no_records.map((c) => srcRow(c, 'no_records')), buckets.manual_only.map((c) => srcRow(c, 'manual_only')), buckets.unavailable.map((c) => srcRow(c, 'unavailable'))));

  const total = (r.coverage || []).length, ok = buckets.retrieved.length + buckets.no_records.length;
  const stat = (label, value) => el('div', { class: 'stat' }, el('b', { text: value }), label);
  const glance = el('section', { class: 'card' }, el('h2', { text: 'At a glance' }),
    el('div', { class: 'stats' },
      stat('sources checked', total ? `${ok} of ${total}` : '–'),
      stat(aptRecords.length ? 'records kept (building\u2011level)' : 'records kept', String(r.findings?.length ?? 0)),
      stat('rejected · held by the Warden', `${S.warden.rejected} · ${S.warden.held}`),
      stat(r.models_used?.length ? 'AI model used' : 'reasoning', r.models_used?.length ? shortModel(r.models_used[0]) : 'deterministic')),
    r.limitations?.length ? el('div', { class: 'group' }, el('h3', { text: 'Caveats' }), el('div', { class: 'note-box' }, r.limitations.slice(0, 4).map((x) => el('p', { text: x })))) : null);

  const wrap = $('#result');
  wrap.replaceChildren(el('div', { class: 'placard-wrap' }, placard, glance), evidence, checked);
  wrap.hidden = false;
}

// Agency text arrives as "novdescription: ALL CAPS SENTENCE": drop the field label, and show shouty text in sentence case.
function readable(raw) {
  const original = String(raw ?? '');
  const text = original.replace(/^\s*[a-z][a-z0-9_]*:\s+(?=\S)/, '');
  if (text.length > 12 && !/[a-z]/.test(text) && /[A-Z]/.test(text)) {
    return { text: text.toLowerCase().replace(/(^\s*|[.!?]\s+)([a-z])/g, (m, lead, ch) => lead + ch.toUpperCase()), title: text };
  }
  return { text, title: '' };
}

function findingCard(f, isCounted, apartment) {
  const cls = String(f.severity || '').toUpperCase();
  const body = readable(String(f.description || f.kind || 'Agency record').slice(0, 260));
  const link = safeUrl(f.source_url);
  return el('article', { class: `find${isCounted ? ' counted' : ''}` },
    isCounted ? el('span', { class: 'badge-counted', text: 'COUNTED' }) : null,
    el('div', { class: 'row' },
      cls ? el('span', { class: `chip ${cls.toLowerCase()}`, text: `Class ${cls}` }) : null,
      f.recorded_status ? el('span', { class: `chip ${/open/i.test(f.recorded_status) ? 'open' : ''}`, text: String(f.recorded_status).toUpperCase() }) : null,
      f.event_date ? el('span', { class: 'chip', text: String(f.event_date).slice(0, 10) }) : null,
      apartment ? el('span', { class: 'chip apt', text: `Apt ${apartment}` }) : null),
    el('p', body.title ? { text: body.text, title: body.title } : { text: body.text }),
    el('div', { class: 'evid' }, el('span', null, f.agency ? `${String(f.agency).replace(/^Department of /, '')} · ` : '', el('code', { text: (f.evidence_ids || [])[0] || f.finding_id })),
      link ? el('a', { href: link, target: '_blank', rel: 'noopener', text: 'View city record ↗' }) : null));
}

function renderDownloads(body) {
  const r = body.result;
  $('#downloads').replaceChildren(...(r.files || []).filter((n) => ['trace.jsonl', 'renter_report.md', 'run_summary.json', 'investigation_report.json'].includes(n))
    .map((name) => el('a', { href: `/api/runs/${body.id}/files/${name}?download=1`, text: name })));
  $('#underMeta').textContent = `Provider: ${r.provider} · data: ${r.data_mode} · models: ${r.models_used?.length ? r.models_used.map(shortModel).join(', ') : 'none (deterministic reasoning)'} · ${r.duration_seconds != null ? `${Math.round(r.duration_seconds)}s` : ''}`;
}

/* ---------- home ---------- */
function setPill(kind, r) {
  const pill = $('#modePill');
  pill.className = `pill ${kind}`;
  const models = r ? (r.models_used || []) : [...S.models];  // finished: what the run reports; running: model events seen so far
  pill.textContent = kind === 'sample' ? 'Recorded replay · not live data'
    : models.length ? `Live · Zetaris + ${shortModel(models[0])}`
    : r ? 'Live · Zetaris · rules only, no AI model' : 'Live · Zetaris';
}
function setMode(mode) {
  S.mode = mode;
  document.querySelectorAll('.seg').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.mode === mode)));
  $('#modeHint').textContent = mode === 'sample'
    ? 'Replays a saved capture, so it runs offline in seconds. Only the listed sample cases have data.'
    : 'Live runs pull real city records and take about 1-3 minutes, longer when an AI model is used.';
  if (!S.job || !S.running) setPill(mode === 'sample' ? 'sample' : 'live');
}

function submitForm(event) {
  event.preventDefault();
  const address = $('#address').value.trim();
  if (!address) return showFormError('Enter a NYC street address.');
  startRun({ address, borough: $('#borough').value, unit: $('#unit').value.trim(), mode: S.mode });
}

async function boot() {
  S.crew = Object.fromEntries(CREW.map((c) => [c.id, { status: 'waiting', note: '' }]));
  renderCrewIntro();
  try { S.cfg = await (await fetch('/api/config')).json(); } catch (error) { S.cfg = { default_mode: 'sample', cases: [] }; }
  setMode(S.cfg.default_mode === 'live' ? 'live' : 'sample');
  if (S.cfg.cases?.length) {
    const box = $('#cases'); box.hidden = false;
    box.replaceChildren('Try a sample case:', ...S.cfg.cases.map((c) => el('button', { type: 'button', class: 'chip-btn', onclick: () => {
      $('#address').value = c.address; $('#borough').value = c.borough || ''; $('#unit').value = c.unit || '';
      setMode('sample'); startRun({ address: c.address, borough: c.borough || '', unit: c.unit || '', mode: 'sample' });
    } }, c.label || c.address, el('small', { text: 'recorded demo' }))));
  }
  document.querySelectorAll('.seg').forEach((b) => b.addEventListener('click', () => setMode(b.dataset.mode)));
  $('#form').addEventListener('submit', submitForm);
  $('#again').addEventListener('click', () => {
    S.job = null; $('#case').hidden = true; $('#home').hidden = false; $('#again').hidden = true; $('#address').focus();
    setPill(S.mode === 'sample' ? 'sample' : 'live');
  });
  $('#onlyDecisions').addEventListener('change', (e) => $('#trace').classList.toggle('only', e.target.checked));
}
boot();