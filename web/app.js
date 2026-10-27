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
// Record ids arrive URL-encoded ("%7C" for "|"). Show them decoded and never wrapped; long ones get a middle ellipsis.
// The full raw id stays in the title so it can be copied or looked up.
const displayId = (id) => { const t = String(id ?? '').replace(/%7C/gi, '|'); return t.length > 30 ? `${t.slice(0, 14)}…${t.slice(-13)}` : t; };
const idCode = (id) => el('code', { class: 'rid', title: String(id ?? ''), text: displayId(id) });
// Model-written text is untrusted: control characters out, and it only ever reaches the page through el() as text nodes.
const cleanText = (t) => String(t ?? '').replace(/[\u0000-\u001f\u007f-\u009f]+/g, ' ').trim();
// Critic issue codes -> plain English. Unknown codes show as-is, in sentence case.
const ISSUE_PLAIN = { VIOLATION_STATUS_UNVERIFIED: 'Violation status not verified' };
const issuePlain = (code) => { const c = cleanText(code); return ISSUE_PLAIN[c] || c.toLowerCase().replace(/_/g, ' ').replace(/^./, (x) => x.toUpperCase()); };
// Recorded status -> open / closed / other, for ordering and for the quiet card style.
const CLOSED_RE = /\b(closed?|dismiss\w*|resolv\w*|signed[\s-]*off|complet\w*|rescind\w*|withdrawn|cured)\b/i;
const OPEN_RE = /\b(open|active|nov sent out|not complied|no access|in violation)\b/i;
const statusKind = (status) => (CLOSED_RE.test(status || '') ? 'closed' : OPEN_RE.test(status || '') ? 'open' : 'other');
const PERMIT_DATASETS = new Set(['ipu4-2q9a', 'ic3t-wcy2', 'rbx6-tga4', 'w9ak-ipjd']);  // DOB permits and job filings (routine paperwork)

const CREW = [
  { id: 'surveyor', stage: 1, name: 'Surveyor', role: 'Identity resolution', engine: 'rules', hue: 210, blurb: 'Works out exactly which building you mean (BBL, BIN, HPD id).' },
  { id: 'archivist', stage: 1, name: 'Archivist', role: 'Records via Zetaris', engine: 'zetaris', hue: 188, blurb: 'Pulls the city’s records through the Zetaris data layer.' },
  { id: 'warden', stage: 2, name: 'Warden', role: 'Critic · rules R1–R10', engine: 'rules', hue: 6, blurb: 'Throws out any record that does not belong to this building.' },
  { id: 'pathfinder', stage: 3, name: 'Pathfinder', role: 'Planner', engine: 'model', hue: 265, blurb: 'Plans which legal and safety questions are worth asking.' },
  { id: 'bloodhound', stage: 3, name: 'Bloodhound', role: 'Researcher', engine: 'model', hue: 32, blurb: 'Chases the evidence behind each question, with citations.' },
  { id: 'magistrate', stage: 3, name: 'Magistrate', role: 'Legal Critic', engine: 'model', hue: 300, blurb: 'Sends weak drafts back, or refuses to conclude without proof.' },
  { id: 'assessor', stage: 4, name: 'Assessor', role: 'Verdict rules', engine: 'rules', hue: 145, blurb: 'Stamps the placard from fixed, checkable rules. Never says “safe”.' },
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

// Home page "how it works": generated from CREW so names, roles and engines live in one place.
const STAGES = ['Find the building', 'Throw out wrong records', 'Investigate', 'Stamp the verdict'];
function arrowIcon() {
  const ns = 'http://www.w3.org/2000/svg', svg = document.createElementNS(ns, 'svg'), path = document.createElementNS(ns, 'path');
  for (const [k, v] of Object.entries({ viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true', class: 'arrow' })) svg.setAttribute(k, v);
  path.setAttribute('d', 'M5 12h14M13 6l6 6-6 6');
  svg.append(path);
  return svg;
}
function renderCrewIntro() {
  $('#crewIntro').replaceChildren(...STAGES.map((title, i) => el('li', { class: 'stage-card' },
    el('h3', null, el('span', { class: 'sn', 'aria-hidden': 'true', text: String(i + 1) }), title),
    el('ul', { class: 'agents' }, CREW.filter((c) => c.stage === i + 1).map((c) => el('li', { title: c.blurb },
      el('div', { class: 'emblem', 'data-agent': c.id }, avatar(c)),
      el('div', { class: 'ident' }, el('div', { class: 'name', text: c.name }), el('div', { class: 'role', text: c.role }), engineTag(c))))),
    i < STAGES.length - 1 ? arrowIcon() : null)));
}
// "What the verdict can say": the copy comes straight from VERDICTS, so it cannot drift from the real placard.
function renderVerdictKey() {
  $('#verdictKey').replaceChildren(...Object.entries(VERDICTS).map(([name, v]) => el('li', { class: 'vk', 'data-level': v.level },
    el('div', { class: 'vk-stamp', text: name }), el('p', { text: v.line }))));
}

function renderStation(id) {
  const c = CREW_BY_ID[id], st = S.crew[id];
  const label = { waiting: 'waiting', working: 'working', done: 'done', stopped: 'stopped', skipped: 'did not run' }[st.status];
  const node = $(`#st-${id}`) || el('div', { class: 'station', id: `st-${id}`, role: 'listitem' });
  node.dataset.status = st.status;
  let note = st.note || c.blurb;
  // Display only: the state value stays "Outcome: INCONCLUSIVE". With no model in the run there was nothing to conclude.
  if (id === 'magistrate' && /^Outcome: INCONCLUSIVE/.test(st.note || '') && S.final && !S.final.models_used?.length) note = 'No AI model ran, so no legal conclusion.';
  const legal = S.final?.legal;  // what the reviewers produced (null for deterministic runs and replays)
  if (legal && id === 'bloodhound') note = `${legal.observations_cited ?? 0} cited ${legal.observations_cited === 1 ? 'observation' : 'observations'} (AI-written)`;
  if (legal && id === 'magistrate' && /^Outcome: INCONCLUSIVE/.test(st.note || '')) note = legal.critic_issues?.length ? `Would not sign off: ${issuePlain(legal.critic_issues[0].code)}` : 'Would not sign off';
  node.replaceChildren(
    el('div', { class: 'strip' }, el('span', { text: 'SignSafe crew' }), el('span', { text: `No. ${String(CREW.indexOf(c) + 1).padStart(2, '0')}` })),
    el('div', { class: 'who' },
      el('div', { class: 'emblem', 'data-agent': c.id }, avatar(c)),
      el('div', { class: 'ident' }, el('div', { class: 'name', text: c.name }), el('div', { class: 'role', title: c.role, text: c.role }), engineTag(c))),
    el('div', { class: 'status' }, el('i', { class: 'dot', 'aria-hidden': 'true' }), label),
    el('div', { class: `note${st.note ? '' : ' idle'}`, title: note, text: note }));
  return node;
}
function renderCrew() {
  $('#crew').replaceChildren(...CREW.map((c) => renderStation(c.id)));
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
    pill('rejected', String(S.warden.rejected)),
    pill('held for review', String(S.warden.held)),
    pill('model calls', String(S.modelCalls)),
    pill('elapsed', mmss(S.running ? (Date.now() - S.startedAt) / 1000 : S.elapsed || 0)));
  setPill();  // renderCounters already runs on model events and the 1 s tick, so the header chip stays live
}
let ledgerTimer = 0;
// Socrata dataset ids (VERIFIED_SOURCE_INVENTORY.md) -> what a renter would call the record. Unknown ids show as-is.
const DATASET_LABELS = {
  'kj4p-ruqc': 'HPD building', 'tesw-yqqr': 'HPD registration', 'feu5-w2e2': 'HPD registration contact', 'wvxf-dwi5': 'HPD violation',
  'ygpa-z7cr': 'HPD complaint', 'eabe-havv': 'DOB complaint', '3h2n-5cm9': 'DOB violation', '6bgk-3dad': 'DOB ECB violation',
  'ipu4-2q9a': 'DOB permit', 'ic3t-wcy2': 'DOB job filing', 'jz4z-kudi': 'OATH hearing', 'hcir-3275': 'HPD enforcement program (AEP)',
  '6z8x-wfk4': 'Eviction', 'bzxi-2tsw': 'Harassment-certification list', '59kj-x8nc': 'HPD litigation', 'rbx6-tga4': 'DOB NOW permit',
  'w9ak-ipjd': 'DOB NOW job filing',
};
// Critic rule ids -> plain English (critic-spec.md R1-R10; ROOT_CRITIC_HANDOFF.md for R5/R6). Unknown ids show as-is.
const RULE_REASONS = {
  R1: 'belongs to a different building (BBL mismatch)', R2: 'borough conflict', R3: 'recorded too far from this building',
  R4: 'dated before the building was built', R5: 'duplicate of a record already kept', R6: 'address differs from this building',
  R7: 'building class conflict', R8: 'low-confidence match, not corroborated', R9: 'no evidence cited', R10: 'cites a record that is not on the board',
};
const STATE_ICON = { accepted: '✓', rejected: '✗', held: '⏸' };
const STATE_WORD = { accepted: 'kept', rejected: 'rejected', held: 'held' };
function decisionLine(id, r) {
  const dataset = String(id).split(':')[0];
  const what = DATASET_LABELS[dataset] || String(id).replace(/%7C/gi, '|');
  let why;
  if (!r.rule) why = r.state === 'accepted' ? 'belongs to this building' : r.state === 'held' ? 'held for review' : 'rejected';
  else if (r.rule === 'R8' && dataset === 'wvxf-dwi5') why = 'apartment-level record';
  else why = RULE_REASONS[r.rule] || r.rule;
  return `${what} · ${STATE_WORD[r.state]} · ${why}`;
}
function renderLedger() {  // coalesced: a burst of decisions redraws the ledger once
  if (ledgerTimer) return;
  ledgerTimer = setTimeout(() => { ledgerTimer = 0; drawLedger(); }, 150);
}
function clearLedger() {
  for (const id of ['ledgerBar', 'ledgerLegend', 'ledgerLatest', 'ledgerList']) $(`#${id}`).replaceChildren();
  $('#ledgerAllLabel').textContent = 'All 0 records'; $('#ledgerAll').open = false; $('#ledger').hidden = true;
}
function drawLedger() {
  const all = [...S.records.entries()];
  $('#ledger').hidden = !all.length;
  const { accepted: a, rejected: r, held: h } = S.warden, total = a + r + h;
  const bar = $('#ledgerBar');
  bar.setAttribute('aria-label', `${a} accepted, ${r} rejected, ${h} held for review`);
  bar.replaceChildren(...[['accepted', a], ['rejected', r], ['held', h]].filter(([, n]) => n > 0)
    .map(([state, n]) => el('span', { class: `seg-${state}`, style: `flex:${n} 1 0` })));
  $('#ledgerLegend').replaceChildren(
    el('span', { class: 'accepted' }, el('b', { text: String(a) }), ' accepted'),
    el('span', { class: 'rejected' }, el('b', { text: String(r) }), ' rejected'),
    el('span', { class: 'held' }, el('b', { text: String(h) }), ' held for review'));
  $('#ledgerLatest').replaceChildren(...all.slice(-5).reverse().map(([id, rec]) =>
    el('li', { class: rec.state, title: String(id).replace(/%7C/gi, '|') }, el('i', { 'aria-hidden': 'true', text: STATE_ICON[rec.state] }), decisionLine(id, rec))));
  $('#ledgerAllLabel').textContent = `All ${total || all.length} records`;
  const details = $('#ledgerAll');
  if (!details.open) return;  // the long list is only built while someone is reading it
  const list = $('#ledgerList'), top = list.scrollTop;
  list.replaceChildren(...all.map(([id, rec]) => el('li', { class: rec.state, title: String(id).replace(/%7C/gi, '|') }, el('i', { 'aria-hidden': 'true', text: STATE_ICON[rec.state] }), decisionLine(id, rec))));
  list.scrollTop = top;
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
  $('#trace').replaceChildren(); clearLedger(); $('#toasts').replaceChildren(); $('#stage').classList.remove('done'); clearTimeout(S.presentTimer);
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
  $('#hudSub').textContent = `${payload.borough || 'Borough not given'}${payload.unit ? ` · unit ${payload.unit}` : ''} · ${payload.mode === 'sample' ? 'offline replay' : 'live city data'}`;
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
  presentResult();
}

// Run finished: the board shrinks to a strip (the scene keeps running) and the placard sits directly beneath it.
function presentResult() {
  const board = $('#boardWrap'), stage = $('#stage');
  stage.classList.add('done');
  clearTimeout(S.presentTimer);
  let scrolled = false;
  const reveal = () => {  // measure once the board has finished shrinking, so the scroll target is the final one
    if (scrolled) return;
    scrolled = true; clearTimeout(S.presentTimer); board.removeEventListener('transitionend', onEnd);
    const card = $('#result .placard') || $('#result');
    const top = card.getBoundingClientRect().top;
    if (top < 0 || top > innerHeight * 0.55) window.scrollTo({ top: Math.max(0, top + scrollY - innerHeight * 0.38), behavior: 'smooth' });
  };
  const onEnd = (e) => { if (e.propertyName === 'height') reveal(); };
  board.addEventListener('transitionend', onEnd);
  S.presentTimer = setTimeout(reveal, 1200);  // no transition (reduced motion) or it never fired
}

// Developer-flavoured caveats from the report, matched by substring and shown in plain English. Anything else shows unchanged.
const CAVEAT_PLAIN = [
  ['R5 holds records that are identical apart from their own IDs', 'Records that look identical apart from their own IDs are treated as possible duplicates; distinct records from the same day are kept.'],
  ['Paginated live datasets may change during a run', 'City data can change while a run is in progress, so this is not a snapshot.'],
];
const plainCaveat = (x) => (CAVEAT_PLAIN.find(([key]) => String(x).includes(key)) || [])[1] || String(x);

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
    el('div', null, ...(rule.evidence_ids || []).map((id) => idCode(id)), ' ',
      ...(rule.source_urls || []).filter(safeUrl).slice(0, 3).map((u, i) => el('a', { href: u, target: '_blank', rel: 'noopener', text: `record ${i + 1} ↗` }), ' '))));
  const reasons = v?.basis?.not_enough_data_reasons || [];
  const cov = v?.basis?.coverage;
  const covText = cov && (cov.checked ?? cov.sources_checked) != null ? `Checked ${cov.checked ?? cov.sources_checked} of ${cov.machine_readable ?? cov.machine_readable_sources ?? '?'} machine-readable sources. ` : '';

  const also = (Array.isArray(v?.basis?.also_on_record) ? v.basis.also_on_record : []).filter((x) => typeof x === 'string' && x);
  const titleOf = new Map((r.coverage || []).map((c) => [c.source, c.title || c.source]));
  const partial = (Array.isArray(v?.basis?.partial_sources) ? v.basis.partial_sources : []).map((k) => titleOf.get(k) || String(k));

  // Source ids in agency prose ("Sources not checked: fdny_oath") become the titles the coverage list carries.
  const humanSources = (text) => String(text).replace(/\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b/g, (id) => titleOf.get(id) || id);
  const tryLine = v?.verdict === 'NOT ENOUGH DATA'
    ? (r.data_mode === 'recorded_replay' ? 'This offline replay only knows 1 Mock Street. Switch to Live city data.'
      : r.identity_status !== 'verified' ? 'We couldn’t match this to one building. Check the borough and the spelling.'
      : 'Some sources couldn’t be reached. Running it again sometimes helps.')
    : null;

  const placard = el('article', { class: 'placard', 'data-level': info?.level || 'none' },
    el('header', null, el('span', { text: 'NYC renter inspection' }), el('span', { text: `Case ${String(r.run_id).slice(0, 8)}` })),
    el('div', { class: 'place', text: place }),
    el('div', { class: `stamp${(v ? v.verdict : 'Facts only').length > 11 ? ' long' : ''}`, text: v ? v.verdict : 'Facts only' }),
    el('p', { class: 'vline', text: info ? info.line : 'This build has no verdict rules installed, so you are looking at the checked records without a rating.' }),
    rules.length ? el('ul', { class: 'rules' }, rules) : null,
    reasons.length ? el('ul', { class: 'rules' }, reasons.map((x) => el('li', { 'data-level': 'NOTE', text: String(x) }))) : null,
    tryLine ? el('p', { class: 'try' }, el('b', { text: 'Try: ' }), tryLine) : null,
    also.length ? el('div', { class: 'also' }, el('h4', { text: 'Also on record' }), el('ul', null, also.map((x) => el('li', { text: String(x) })))) : null,
    el('footer', null, covText, humanSources(v?.disclaimer || 'Not a safety guarantee. Based only on recorded agency data; missing data is not good news.'),
      partial.length ? el('div', { text: `Some results were truncated (${partial.join(', ')}), so counts may be higher than shown.` }) : null,
      r.data_mode === 'recorded_replay' ? el('div', { text: 'Data source: recorded replay (not live agency data).' }) : null));

  const groups = new Map();
  for (const f of r.findings || []) {
    const key = (f.categories || [])[0] || 'other';
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(f);
  }
  const isCounted = (f) => (f.evidence_ids || []).some((id) => counted.has(id));
  const rank = (f) => [isCounted(f) ? 0 : 1, { open: 0, other: 1, closed: 2 }[statusKind(f.recorded_status)], SEV_RANK[String(f.severity || '').toUpperCase()] ?? 3];
  const byRank = (a, b) => { const x = rank(a), y = rank(b); for (let i = 0; i < 3; i++) if (x[i] !== y[i]) return x[i] - y[i]; return String(b.event_date || '').localeCompare(String(a.event_date || '')); };
  const ordered = [...groups.entries()].map(([key, list]) => [key, [...list].sort(byRank)])
    .sort((a, b) => (QUIET_GROUPS.has(a[0]) - QUIET_GROUPS.has(b[0])) || ((GROUP_ORDER.indexOf(a[0]) + 99) % 99 - (GROUP_ORDER.indexOf(b[0]) + 99) % 99) || b[1].length - a[1].length);
  const SHOW = 12;
  const cardsOf = (list) => {  // first SHOW cards, then the rest behind a "Show the other N" fold
    const cards = list.map((f) => findingCard(f, isCounted(f)));
    const rest = cards.length > SHOW ? el('details', { class: 'more' }, el('summary', { text: `Show the other ${cards.length - SHOW}` }), el('div', { class: 'finds' }, cards.slice(SHOW))) : null;
    return [el('div', { class: 'finds' }, cards.slice(0, SHOW)), rest];
  };
  const isRoutine = (f) => (PERMIT_DATASETS.has(f.dataset) || f.kind === 'permit') && !isCounted(f);
  const groupNode = ([key, list]) => {
    // Building safety: violations first; routine permits and job filings fold into their own sub-group below them.
    const routine = key === 'building_safety' ? list.filter(isRoutine) : [];
    const main = routine.length ? list.filter((f) => !isRoutine(f)) : list;
    const open = main.filter((f) => statusKind(f.recorded_status) === 'open').length, closed = main.filter((f) => statusKind(f.recorded_status) === 'closed').length;
    const tail = open + closed ? ` · ${open} open · ${closed} closed` : '';
    const head = `${prettyKey(key)} · ${main.length || list.length}${tail}`;
    const permits = routine.length ? el('details', { class: 'group quiet permits' }, el('summary', { text: `Permits and filings · ${routine.length}` }), ...cardsOf(routine)) : null;
    if (QUIET_GROUPS.has(key)) return el('details', { class: 'group quiet' }, el('summary', { text: head }), ...cardsOf(main), permits);
    return el('div', { class: 'group' }, el('h3', { text: head }), ...(main.length ? cardsOf(main) : []), permits);
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
  buckets.retrieved.sort((a, b) => (b.records_returned || 0) - (a.records_returned || 0));
  const srcRow = (c, s) => el('div', { class: 'src', 'data-s': s, title: c.reason || '' }, el('span', { class: 'nm', text: c.title || c.source }),
    el('span', { class: 'st' }, s === 'retrieved' ? [el('b', { text: String(c.records_returned ?? '') }), ' found'] : s === 'no_records' ? 'none found' : s === 'manual_only' ? 'CHECK MANUALLY' : 'COULD NOT CHECK'));
  const checked = el('section', { class: 'card' }, el('h2', { text: 'What we checked' }),
    el('p', { class: 'sub', text: 'Every source is listed, including the ones we could not reach. Unchecked is unknown, never safe.' }),
    el('div', { class: 'checked-grid' }, buckets.retrieved.map((c) => srcRow(c, 'retrieved')), buckets.no_records.map((c) => srcRow(c, 'no_records')), buckets.manual_only.map((c) => srcRow(c, 'manual_only')), buckets.unavailable.map((c) => srcRow(c, 'unavailable'))));

  const total = (r.coverage || []).length, ok = buckets.retrieved.length + buckets.no_records.length;
  const stat = (label, value) => el('div', { class: 'stat' }, el('b', { text: value }), label);
  const glance = el('section', { class: 'card' }, el('h2', { text: 'At a glance' }),
    el('div', { class: 'stats' },
      stat('sources checked', total ? `${ok} of ${total}` : '–'),
      stat('records about this building', String(r.findings?.length ?? 0)),
      stat('rejected by the Warden', String(S.warden.rejected)),
      stat('held for review', String(S.warden.held)),
      stat('decided by', 'fixed rules'),
      stat('model calls', String(S.modelCalls))),
    r.limitations?.length ? el('details', { class: 'group quiet caveats' }, el('summary', { text: `Caveats (${r.limitations.length})` }), el('div', { class: 'note-box' }, r.limitations.map((x) => el('p', { text: plainCaveat(x) })))) : null);

  const wrap = $('#result');
  wrap.replaceChildren(el('div', { class: 'placard-wrap' }, placard, glance), r.legal ? legalSection(r.legal, evidence) : null, evidence, checked);
  wrap.hidden = false;
}

// "What the AI reviewers did": the Pathfinder / Bloodhound / Magistrate output from legal_assessment, shown as unverified AI text.
function legalSection(L, evidence) {
  const cardById = new Map();  // evidence id -> its card in the evidence list, so a chip can jump to it
  for (const card of evidence.querySelectorAll('.find')) for (const code of card.querySelectorAll('.rid')) cardById.set(code.title, card);
  const chip = (id) => {
    const node = idCode(cleanText(id)), card = cardById.get(cleanText(id));
    if (!card) return node;  // no matching card: the chip stays plain
    const go = () => {
      for (let n = card.parentElement; n; n = n.parentElement) if (n.tagName === 'DETAILS') n.open = true;
      card.scrollIntoView({ block: 'center', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
      card.classList.add('ping'); setTimeout(() => card.classList.remove('ping'), 1800);
    };
    node.classList.add('jump'); node.setAttribute('role', 'button'); node.tabIndex = 0;
    node.addEventListener('click', go); node.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } });
    return node;
  };
  const chips = (ids) => (ids || []).length ? el('div', { class: 'idchips' }, ids.map(chip)) : null;
  const outcome = cleanText(L.critic_outcome).toUpperCase(), published = L.published || 0, cited = L.observations_cited ?? 0;
  const summary = [`Pathfinder planned ${plural(L.planner_questions || 0, 'question')}`, `Bloodhound returned ${cited} cited ${cited === 1 ? 'observation' : 'observations'}`,
    `Magistrate: ${outcome || 'no outcome'}${L.reviews ? ` after ${plural(L.reviews, 'review')}` : ''}`, `${published} published`].join(' · ');
  const total = L.observation_total ?? (L.observations || []).length;
  const left = el('div', { class: 'legal-col' },
    el('h3', null, published ? 'Published findings' : 'Bloodhound’s observations', published ? null : el('span', { class: 'quiet-tag', text: 'AI-written · not verified · not published' })),
    ...(L.observations || []).map((o) => el('article', { class: 'ob' },
      el('p', { text: cleanText(o.summary) || 'No summary given.' }),
      o.sufficiency ? el('div', { class: 'meta', text: `Sufficiency: ${cleanText(o.sufficiency)}` }) : null,
      (o.evidence_ids || []).length ? chips(o.evidence_ids) : el('div', { class: 'meta', text: 'No records cited.' }),
      (o.missing_information || []).length ? el('div', { class: 'meta' }, el('b', { text: 'Missing: ' }), o.missing_information.map(cleanText).join('; ')) : null)),
    (L.observations || []).length ? null : el('p', { class: 'meta', text: 'No observations returned.' }),
    total > (L.observations || []).length ? el('p', { class: 'meta', text: `Showing ${(L.observations || []).length} of ${total}.` }) : null);
  const right = el('div', { class: 'legal-col' }, el('h3', { text: 'Magistrate’s objections' }),
    ...(L.critic_issues || []).map((i) => el('article', { class: 'ob' },
      el('b', { class: 'ob-title', text: issuePlain(i.code) }), el('p', { text: cleanText(i.message) }), chips(i.evidence_ids))),
    (L.critic_issues || []).length ? null : el('p', { class: 'meta', text: 'No objections recorded.' }),
    (L.follow_ups || []).length ? el('div', { class: 'asked' }, el('b', { text: 'Asked for:' }), el('ul', null, L.follow_ups.map((x) => el('li', { text: cleanText(x) })))) : null);
  return el('section', { class: 'card legal' }, el('h2', { text: 'What the AI reviewers did' }), el('p', { class: 'sub', text: summary }),
    el('div', { class: 'legal-cols' }, left, right),
    published ? null : el('p', { class: 'legal-foot', text: !outcome ? 'The verdict above comes from fixed rules. The Magistrate returned no outcome, so none are shown as findings.'
      : outcome === 'PASS' ? 'The verdict above comes from fixed rules. None of these observations are shown as findings.'
      : 'The verdict above comes from fixed rules. The Magistrate would not sign off on these observations, so none are shown as findings.' }));
}

// Agency text arrives as "novdescription: ALL CAPS SENTENCE; job_type: A2; work_type: Plumbing". Drop the field labels and the
// machine-only fields, keep work_type / filing_reason / violation_type as a quiet second line, and show shouty text in sentence case.
const KEEP_KEYS = new Set(['work_type', 'filing_reason', 'violation_type']);
const KEY_VALUE = /^\s*([a-z][a-z0-9_]*):\s+(?=\S)/;
const sentenceCase = (text) => (text.length > 12 && !/[a-z]/.test(text) && /[A-Z]/.test(text)
  ? text.toLowerCase().replace(/(^\s*|[.!?]\s+)([a-z])/g, (m, lead, ch) => lead + ch.toUpperCase()) : text);
function cleanDescription(raw) {
  let main = '';
  const keep = [];
  String(raw ?? '').split(/;\s+(?=[a-z][a-z0-9_]*:\s)/).forEach((part, i) => {
    const m = part.match(KEY_VALUE);
    const value = (m ? part.slice(m[0].length) : part).replace(/\s+/g, ' ').trim();
    if (m && KEEP_KEYS.has(m[1])) { if (value) keep.push(sentenceCase(value)); }
    else if (i === 0) main = sentenceCase(value);
  });
  if (main.length > 220) {
    const cut = main.slice(0, 220), space = cut.lastIndexOf(' ');
    main = `${(space > 120 ? cut.slice(0, space) : cut).replace(/[\s,;:.\-–]+$/, '')}…`;
  }
  return { text: main, meta: [...new Set(keep)].join(' · ') };
}

function findingCard(f, isCounted, apartment) {
  const cls = String(f.severity || '').toUpperCase();
  const kind = statusKind(f.recorded_status);
  const quiet = kind === 'closed' && !isCounted;
  const raw = String(f.description || '');
  const body = cleanDescription(raw);
  const text = body.text || DATASET_LABELS[f.dataset] || prettyKey(f.kind || 'agency record');
  const link = safeUrl(f.source_url);
  const word = /dismiss/i.test(f.recorded_status) ? 'dismissed' : /signed/i.test(f.recorded_status) ? 'signed off' : 'closed';
  const loud = cls && !quiet && (cls === 'B' || cls === 'C');  // only open Class B/C get the colored chip
  return el('article', { class: `find${isCounted ? ' counted' : ''}${quiet ? ' quiet' : ''}`, title: raw || null },
    isCounted ? el('span', { class: 'badge-counted', text: 'COUNTED' }) : null,
    el('div', { class: 'row' },
      cls ? el('span', { class: `chip ${loud ? cls.toLowerCase() : quiet ? 'quiet' : ''}`, title: quiet ? String(f.recorded_status) : null, text: quiet ? `Class ${cls} · ${word}` : `Class ${cls}` }) : null,
      f.recorded_status && !(quiet && cls) ? el('span', { class: `chip${kind === 'open' ? ' open' : quiet ? ' quiet' : ''}`, text: String(f.recorded_status).toUpperCase() }) : null,
      f.event_date ? el('span', { class: 'chip', text: String(f.event_date).slice(0, 10) }) : null,
      apartment ? el('span', { class: 'chip apt', text: `Apt ${apartment}` }) : null),
    el('p', { text }),
    body.meta ? el('div', { class: 'meta', text: body.meta }) : null,
    el('div', { class: 'evid' }, el('span', null, f.agency ? `${String(f.agency).replace(/^Department of /, '')} · ` : '', idCode((f.evidence_ids || [])[0] || f.finding_id)),
      link ? el('a', { href: link, target: '_blank', rel: 'noopener', text: 'View city record ↗' }) : null));
}

function renderDownloads(body) {
  const r = body.result;
  $('#downloads').replaceChildren(...(r.files || []).filter((n) => ['trace.jsonl', 'renter_report.md', 'run_summary.json', 'investigation_report.json'].includes(n))
    .map((name) => el('a', { href: `/api/runs/${body.id}/files/${name}?download=1`, text: name })));
  $('#underMeta').textContent = `Provider: ${r.provider} · data: ${r.data_mode} · models: ${r.models_used?.length ? r.models_used.map(shortModel).join(', ') : 'none (deterministic reasoning)'} · ${r.duration_seconds != null ? `${Math.round(r.duration_seconds)}s` : ''}`;
}

/* ---------- home ---------- */
// The hidden <select id="borough"> is the single source of truth; the segmented control reads and writes it.
function syncBorough() {
  const value = $('#borough').value;
  document.querySelectorAll('.bseg').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.borough === value)));
}
function setBorough(value) {
  $('#borough').value = value;
  $('#borough').dispatchEvent(new Event('change', { bubbles: true }));
}
// Tags come from our own test runs, not live data, and can go stale. Keep them short and factual.
const REAL_BUILDINGS = [
  { address: '686 3 AVENUE', tag: 'open Class C, older records' },
  { address: '840 2 AVENUE', tag: 'open Class C, recent' },
  { address: '150 EAST 44 STREET', tag: 'no flags in testing' },
  { address: '337 EAST 49 STREET', tag: 'open Class C, recent' },
];  // all Manhattan
// ---- header status chip: says what actually ran. Computed only from the finished result and the counters/trace the page already keeps. ----
// Has a model.failed row reached the trace? Scanned incrementally, so the 1 s tick and per-event redraws stay cheap.
const pillScan = { n: 0, first: null, failed: false };
function modelFailedSeen() {
  const box = $('#trace'), rows = box.children;
  if (pillScan.first !== box.firstElementChild || rows.length < pillScan.n) Object.assign(pillScan, { n: 0, first: box.firstElementChild, failed: false });
  for (; pillScan.n < rows.length; pillScan.n++) {
    const row = rows[pillScan.n];
    if (!pillScan.failed && row.classList.contains('bad') && row.querySelector('.ty')?.textContent === 'model.failed') pillScan.failed = true;
  }
  return pillScan.failed;
}
function pillState() {
  const r = S.job && !S.running ? S.final : null;  // the finished run's result, never a previous run's
  if (r ? r.data_mode === 'recorded_replay' : S.mode === 'sample') {
    return { kind: 'sample', text: 'Offline replay · recorded data', dot: 'amber', title: 'Replays a saved capture. Not live city data and no model call.' };
  }
  if (!S.job) return { kind: 'live', text: 'Live · Zetaris', dot: 'green', title: 'City records come through Zetaris. Whether an AI model is used is shown once a run starts.' };
  const names = r?.models_used?.length ? r.models_used : [...S.models];
  const calls = S.modelCalls, model = names.length ? shortModel(names[0]) : null;
  if (!model && !calls) {
    return { kind: 'rules', text: 'Live · Zetaris · fixed rules this run', dot: 'green', title: 'City records came through Zetaris. The verdict comes from fixed rules. No AI model was called in this run.' };
  }
  const label = model || 'AI model';
  const ended = !S.running, errored = ended && (!S.final || /error|fail|budget|timeout|exceed/i.test(S.final.termination_reason || ''));
  // The Critic's outcome (REVISE / BLOCKED / INCONCLUSIVE) means the review ran and answered, so it is never "unfinished".
  // PASS is the normal completed review and keeps the plain "via Nightshift · N calls" chip.
  const outcome = (S.crew.magistrate?.note || '').match(/^Outcome:\s*(\w+)/)?.[1]?.toUpperCase();
  if (outcome && outcome !== 'PASS') {
    return { kind: 'reviewer', text: `Live · Zetaris + ${label} · AI reviewer: ${outcome.toLowerCase()}`, dot: 'green',
      title: 'The AI reviewer examined cited records and returned this outcome. The verdict still comes from fixed rules.' };
  }
  if (!outcome && (errored || modelFailedSeen())) {
    return { kind: 'unfinished', text: `Live · Zetaris + ${label} · AI review unfinished`, dot: 'amber', title: 'A model was called but its legal review did not finish, so no AI findings are shown.' };
  }
  return { kind: 'model', text: `Live · Zetaris + ${label} via Nightshift${calls ? ` · ${plural(calls, 'call')}` : ''}`, dot: S.running ? 'green pulse' : 'green',
    title: 'The model name is the one Nightshift reports for this run. The verdict still comes from fixed rules.' };
}
function setPill() {
  const st = pillState(), pill = $('#modePill'), key = `${st.kind}|${st.text}|${st.dot}`;
  if (pill.dataset.key === key) return;  // unchanged: leave the DOM (and the pulse animation) alone
  pill.dataset.key = key; pill.dataset.kind = st.kind; pill.title = st.title; pill.setAttribute('aria-label', `${st.text}. ${st.title}`);
  // On phones the part after " via " / " · N calls" is hidden; for the AI-review states the model name goes instead, so the warning stays visible.
  const split = st.text.match(/^(.*?)( via .*| · \d+ calls?)$/), unfinished = /^(unfinished|reviewer)$/.test(st.kind) && st.text.match(/^(Live · Zetaris)( \+ .+?)( · AI review.*)$/);
  const parts = unfinished ? [unfinished[1], el('span', { class: 'more', text: unfinished[2] }), unfinished[3]] : split ? [split[1], el('span', { class: 'more', text: split[2] })] : st.text;
  pill.replaceChildren(el('i', { class: `sdot ${st.dot}`, 'aria-hidden': 'true' }), el('span', { class: 'txt' }, parts));
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
  const real = $('#realCases');
  real.replaceChildren(...REAL_BUILDINGS.map(({ address, tag }) => el('button', { type: 'button', class: 'chip-btn', onclick: () => {
    $('#address').value = address; setBorough('Manhattan'); setMode('live');  // fills the form; the person still presses Investigate
  } }, address, el('small', { text: tag }))));
  document.querySelectorAll('.bseg').forEach((b) => b.addEventListener('click', () => setBorough(b.dataset.borough)));
  $('#borough').addEventListener('change', syncBorough);
  syncBorough();
  renderVerdictKey();
  if (S.cfg.cases?.length) {
    const box = $('#cases'); box.hidden = false;
    box.replaceChildren(...S.cfg.cases.map((c) => el('button', { type: 'button', class: 'chip-btn sample', onclick: () => {
      $('#address').value = c.address; setBorough(c.borough || ''); $('#unit').value = c.unit || '';
      setMode('sample'); startRun({ address: c.address, borough: c.borough || '', unit: c.unit || '', mode: 'sample' });
    } }, `Offline replay · ${c.label || c.address}`)));
  }
  document.querySelectorAll('.seg').forEach((b) => b.addEventListener('click', () => setMode(b.dataset.mode)));
  $('#form').addEventListener('submit', submitForm);
  $('#again').addEventListener('click', () => {
    S.job = null; $('#case').hidden = true; $('#home').hidden = false; $('#again').hidden = true; $('#address').focus();
    setPill(S.mode === 'sample' ? 'sample' : 'live');
  });
  $('#ledgerAll').addEventListener('toggle', drawLedger);
  $('#onlyDecisions').addEventListener('change', (e) => $('#trace').classList.toggle('only', e.target.checked));
}
boot();