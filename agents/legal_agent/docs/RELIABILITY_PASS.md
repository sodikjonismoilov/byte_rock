# Bounded Researcher reliability pass

> **Historical development log.** This file records an earlier checkpoint. Its test counts, "not verified" statements and
> `reports/...` file references describe that moment only: `reports/` held local, gitignored captures that are not in this
> repository. Current status and verified results are in the [root README](../../../README.md).

## Scope and failure diagnosis

The previous full-address Researcher tried to cover seven global categories in a
2,048-token response. Duplicate quotation text, record references and coverage
observations contributed to truncation. This pass keeps the same model output
limit, deadlines, model/tool budgets, two-revision maximum, canonical citation
validation, root veto and publication gates.

The old `selection.max_bytes=60000` limited only `agent_context()`. Role fields,
instructions, example, plan and other payload fields were appended afterward;
`_pack()` capped that larger object at 64000, explaining the reported 62389-byte
Researcher payload. The system instructions and dynamic JSON schema were checked
under a different ceiling. That was not a complete 60000-byte request limit.

`tools.llm.model_request/request_size/request_budget` now build and measure the
actual serialized request, including system instructions, schema, user payload,
JSON escaping and 256 bytes of conservative chat framing. `_pack()` reserves that
space before selecting original context items. The complete ceiling is the minimum
of `LEGAL_CONTEXT_MAX_BYTES`, `LEGAL_MODEL_PAYLOAD_MAX_BYTES` and the existing
conservative `LEGAL_MODEL_MAX_TOKENS` byte ceiling. The separate
`LEGAL_CONTEXT_MAX_TOKENS` projection cap is retained. `context.request_built`
records actual request size, effective ceiling and projection budget without raw
prompts. Mandatory uncertainty cannot be dropped to fit; omissions are explicit.

## Changes

- The private model-facing ResearchDraft schema permits at most **three** initial
  observations, or **one** on a truncation retry. Public ResearchDraft contracts
  and canonical citation conversion remain compatible.
- Researcher instructions prioritize substantive supported concerns, cite registry
  IDs and short exact authority excerpts, and avoid repeating original records.
  Evidence classifications and used-ID lists come from selected registry references.
- `finish_reason=length` always rejects the response, even valid-looking JSON.
  `ModelAgents` permits **one truncation retry for the investigation**, within the
  existing call/time/tool budgets. Invalid JSON or an unknown citation ID without
  truncation is rejected, not repaired or retried. No provider fallback occurs.
- Global coverage gaps remain explicit and keep a full-address legal result
  INCONCLUSIVE. They are routed to the global Planner rather than spending legal
  research revisions on global scheduling. The legal Critic independently checks
  authority, applicability, quotations and evidence-to-claim support; root review
  remains authoritative for global attribution and vetoes.
- The CLI always attempts `renter_report.md`. If legal publication has not cleared,
  it is explicitly **PARTIAL — FACTUAL-ONLY**, preserving approved agency record
  facts, URLs, dates, statuses, scopes and coverage limits without draft legal claims.

## Shared investigation state inspection and handoff

There is **no running global Planner/Conductor or shared Meterless World Model
backend** in this checkout. Existing `LegalSnapshot`, `KeeperPort`,
`LegalSharedAdapter`, `legal_update` and `world_model_fact` are a proposed Keeper
boundary, mapping and tested handoff, not an implemented global state service.

`integration.SharedInvestigationState` minimally extends this same integration
module around `board_update()`; no new Planner, Critic, database or persistent memory
was introduced. A caller shares **one instance and task ID** between agents:

```python
state = SharedInvestigationState(existing_trace)
snapshot = state.read(task_id)
state.update(task_id, actor='planner', expected_version=snapshot.version,
             coverage_gaps=[{'source': 'court', 'reason': 'manual verification'}],
             status='running')
snapshot = state.read(task_id)
state.update(task_id, actor='legal', expected_version=snapshot.version,
             board=board_update(result, evidence), status=result.status.value)
```

Actors are `planner`, `conductor`, `legal` and `root_critic`; the same read/update
interface applies to each. A root actor can append a BLOCKED decision, which clears
publishable legal findings and retains evidence/review history. Reads return copies;
updates use a lock and expected-version check. Stale writes must reread and reapply,
never overwrite another agent's patch. Evidence references validate against the
board's original registry and accepted decisions. Legal findings require PASS,
accepted dependencies and known authority references. Coverage gaps, decisions and
per-agent statuses are merged; decisions are append-only. Raw records remain in the
original evidence registry. H-MEM is separate and has no methods on this adapter.

The CLI emits a **transient handoff snapshot** as `shared_context` in the existing
report JSON and uses the same `trace.jsonl` for all reads, updates and conflicts.
This is **adapter-only, awaiting the team's orchestrator/transport integration**,
not a claim that all agents are deployed against a live shared World Model. The
existing Keeper adapter/mapping remain available for that future integration.

## Single bounded investigation

See `reports/reliability_pass_verification.json` for the exact machine-readable
receipt and artifact paths. Command (repository root, credentials local):

```sh
PYTHONDONTWRITEBYTECODE=1 LEGAL_CONTEXT_MAX_BYTES=60000 LEGAL_CONTEXT_MAX_TOKENS=60000 LEGAL_MODEL_MAX_TOKENS=100000 .venv/bin/python -B scripts/investigate_address.py '840 Second Avenue, Manhattan, NY' --borough Manhattan --provider replay --replay reports/investigations/20261026T035040435638Z_d27bd49e-6969-42cd-b7aa-478930b1d4d3/investigation_report.json --reasoning nvidia --memory-dir .local/legal-memory-demo --model-timeout 60 --max-model-calls 9 --max-revisions 2 --output reports/reliability_pass_replays
```

Observed run `52b64c7f-06cd-4fc2-a5a4-59076adc65fd`: **45.9 seconds**, two live NVIDIA
calls, two H-MEM memories retrieved, one legal search returning eight authorities,
16 accepted factual findings. This is **saved Zetaris evidence with live NVIDIA and
local persistent H-MEM**, not a fresh Zetaris query. Current official authority
snapshots retain their version limits.

Planner request: **53821/60000 bytes**; Researcher: **59141/60000 bytes**, including
schema/instructions/framing. Researcher returned `finish_reason=stop`, not `length`,
but selected an authority ID outside the supplied enum. Strict validation rejected
that draft. No truncation retry was needed or used; invalid-ID repair was not added.
The legal Critic **did not run**. **Zero completed cited claims, zero citations
verified by the legal Critic, zero published legal findings**. H-MEM storage was
skipped. Root record review, factual report, shared handoff and trace were retained.
No full legal review success is claimed, and no second live run was performed.

Coverage remains a bounded recorded slice. Multiple agency sources reached page
caps; HCR/unit rent status and court sources require manual checks; historical law,
present conditions and unit applicability are unverified. `renter_report.md` contains
accepted records only, with these limits.

## Validation

**252 tests passed, 1 opt-in live test skipped**. Targeted cases cover initial/retry
observation limits, successful truncation retry, two truncations terminating, no
retry for malformed nontruncated JSON, rejection even of valid JSON marked `length`,
complete-request sizing including schema, canonical citation preservation, factual-only
failure reporting, one retry across revisions, concurrent agent patches with stale
version recovery, immutable reads, unknown evidence rejection and root BLOCKED.
Official H-MEM conformance: **13/13**; root Critic fixtures: **12/12**. Six generated
run/receipt files scanned against configured secrets: zero matches. No root Critic
policy edits, commit, push or second live investigation.
