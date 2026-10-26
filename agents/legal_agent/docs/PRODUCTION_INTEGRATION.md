# Legal production integration checkpoint — 2026-10-25

> Latest provider and persistent-memory implementation: [Meterless Runtime v4 and H-MEM](METERLESS_RUNTIME.md).

> Latest: NVIDIA credentials are configured. A live smoke and all three model roles completed; see the follow-up below. Missing-configuration notes describe earlier captures.

## Dependency map and ownership

`investigate_address` coordinates address parsing → source plan → provider retrieval →
identity resolution → unchanged root record Critic → local scope/reconciliation →
`LegalResearchWorkflow.run` → local report and Keeper board proposal. The older
`investigate_property` remains a bounded two-dataset sample-selection entry point.
`integration.py` supplies the root-Critic bridge and optional Keeper adapter;
`workflow.py` owns the legal research loop. Neither becomes the global Planner.

The legal Planner chooses legal research questions and read-only tools. ModelAgents
can perform planning, interpretation and semantic critique. Deterministic identity,
source membership, scope, budgets and legal review gates remain authoritative.
The root Critic still owns record attribution and board membership. The global
Planner/Keeper must own cross-agent tasks, canonical state and transactions.

## Implemented safeguards

- Canonical package imports work from the repository root. Legacy imports remain
  supported for existing local demos/tests; CLIs now add the repository root.
- Review precedence is BLOCKED > INCONCLUSIVE > REVISE > PASS. A trusted upstream
  BLOCKED stops before tools/models. INCONCLUSIVE stops instead of repeated research.
  Semantic, deterministic and merged reviews are retained separately.
- One ExecutionBudget follows address retrieval and legal work. Defaults: 300 seconds,
  160 transport/tool attempts, nine model attempts, two revisions and one retry.
  Local search/model waits and retries remain bounded too. Cleanup has a separate
  15-second allowance, at most two owned-namespace deletion attempts.
- SQL is allowlisted at transport entry. Only generated official NYC REST tables,
  owned temporary namespaces and discovered read-only legacy tables are permitted.
- Cleanup runs after success/failure, uncertain CREATE acknowledgments and late
  completions. Real transports receive timeouts; waiting on injected transports is
  bounded. Python cannot forcibly terminate running threads or cancel server work.
- Default HTTP investigations are explicitly client-supplied samples. Clients cannot
  assert trusted identity, reviewed matches, reconciliation, upstream veto or live
  provenance. Production HTTP uses an injected server snapshot loader and rejects
  client context. Deployment authentication remains the team's responsibility.
- Raw agency status survives; normalized open/closed/corrected/unknown status is
  separate. Closed is not proof of correction. Original official record IDs survive.
- Root `critic.py` and all root policies remain unchanged. R5 may hold distinct
  same-day IDs. See ROOT_CRITIC_HANDOFF.md; no held evidence is promoted to bypass it.

## Model configuration and honest runtime status

The CLI defaults to model mode for live providers and deterministic mode for replay.
`--reasoning deterministic` is explicit; `--reasoning configured` follows environment
configuration. Missing/partial model settings return structured INCONCLUSIVE; there
is no model-to-heuristic fallback.

Use ignored `.env.local`, which the existing connector loader reads. Choose
`LLM_PROVIDER=nightshift` with `NIGHTSHIFT_BASE_URL`, `NIGHTSHIFT_MODEL`, and
`NIGHTSHIFT_API_KEY`, or `LLM_PROVIDER=nvidia` with `NVIDIA_MODEL`, `NVIDIA_API_KEY`
and optional `NVIDIA_BASE_URL`. Generic existing compatible configuration remains
available through `LLM_PROVIDER=compatible` and `LLM_BASE_URL/MODEL/API_KEY`.
Never put real keys in `.env.example` or reports.

NVIDIA's official hosted interface is `/v1/chat/completions`; no model is selected
by guesswork. JSON object mode is followed by Pydantic validation. The Nightshift
provider accepts loopback HTTP only, otherwise HTTPS, normalizes pasted endpoint
suffixes and sends the documented `meterless-app` and `meterless-scope` headers.
Placeholder `rt-local` is rejected. The Keeper/provider owner must confirm configured
routing IDs with authenticated `/v1/models`. A Nightshift routing mode is not proof
that the underlying fleet ran Nemotron. Actual response model and usage are logged
when the provider returns them. No routing/model discovery was possible without
credentials. Cold Nightshift loading can exceed our deliberately retained 60-second
maximum model wait; warm the runtime before a demo rather than remove hard limits.

The narrow **real Zetaris** readiness capture is in
`reports/production_model_readiness/`: eight actual returned rows across the selected
queries, one identity row, six mapped audit records, two accepted factual findings,
verified identity, successful temporary namespace deletion. Coverage is partial.
The configured-model run stopped before inference because no model credentials/model
settings exist locally. It reports **zero model calls**, not autonomous legal reasoning.
No direct NYC API fallback was used in that capture. Existing replay reports remain
recorded data; mock tests remain fixtures. Original multi-source reports are retained.

## Context and activity

`context.py` ranks evidence for relevance and deduplicates authority references.
It excludes raw metadata records, held evidence, invalid findings and superseded or
invalidated memory. It preserves original descriptions, exact authoritative excerpts,
identifiers, source URLs, agency status, timestamps, match status, contradictions,
coverage, unresolved questions and latest Critic feedback. Whole items are selected
or explicitly omitted; no unsupported legal summaries replace authoritative text.
`original_context_items` permits trusted focused original lookup; held items remain
in the audit only. The deterministic Critic receives the complete accepted registry
and executed source hits, independent of prompt selection.

Defaults: context 40,000 bytes with a conservative 16,000-byte token ceiling;
complete model payload 64,000 bytes, complete messages plus schema/instructions and
framing allowance a conservative 32,000-byte token ceiling. These are conservative
UTF-8 byte bounds, not tokenizer-specific counts; actual usage comes from the provider.
Oversized mandatory uncertainty/provenance fails explicitly. Schema/plan/draft
additions cannot bypass the final adapter guard. Full original records remain in
existing workflow/provider reports, outside the prompt.

`events.py` provides EventSink, ActivityTrace, in-memory and append-only JSONL sinks.
Run/task/event IDs and UTC timestamps connect source selection/retrieval, identity,
evidence decisions, plans, reviews/revisions, model outcomes, stops, reports, cleanup
and optional memory operations. JSONL also keeps an in-memory report projection.
Events exclude raw records/prompts/private reasoning and redact credentials, bearer
values and sensitive fields. Original evidence reports intentionally retain official
records; activity logs are not a replacement evidence registry. JSONL is a local
single-process debug sink, not a transactional distributed event service.

## Proposed Keeper boundary; no shared contract adopted

`integration.LegalSnapshot` reuses LegalIssueTask, InvestigationContext and canonical
evidence references. `LegalSharedAdapter` uses a caller-supplied KeeperPort:
load_snapshot, publish_legal, retrieve_context, persist_memory, invalidate_memory and
read_events. `run(..., publish=False)` is dry-run by default. It stores no global state.

Proposed update shape:

```json
{
  "schema_version": "legal.keeper.proposal.v1",
  "task_id": "keeper-owned-task",
  "expected_version": 4,
  "idempotency_key": "sha256-of-stable-update",
  "canonical_identity_ref": {"bin": "canonical-reference"},
  "evidence_refs": {},
  "authority_refs": {},
  "legal_findings": [],
  "source_coverage": [],
  "critic_outcome": "INCONCLUSIVE",
  "critic_reviews": [],
  "status": "inconclusive",
  "follow_up_requests": [],
  "limitations": [],
  "summary_is_evidence": false
}
```

Only valid, accepted-reference findings after completed/PASS may be proposed for
publication or durable legal memory. Typed follow-up requests preserve existing
string interfaces in public results. Missing/stale evidence cannot be upgraded by
memory. Keeper publish must atomically enforce expected_version and idempotency_key,
then authorize memory persistence. Repeating an operation must not duplicate state.
These guarantees are tested with a Keeper contract double; a production Keeper
implementation does not exist here. Memory invalidation/supersession and event reads
are delegated to the same owner. No new evidence DB, scheduler or framework exists.

## Meterless: actual proof versus preparation

Inspected both official repositories and actual reference contracts:

- https://github.com/Meterless/Meterless
- https://github.com/Meterless/World-Model/blob/main/AGENTS.md
- https://github.com/Meterless/Meterless/tree/main/engines/world-model/reference
- https://github.com/Meterless/Meterless/tree/main/engines/hmem/reference
- https://github.com/Meterless/Meterless/blob/main/docs/agent-ready/add-meterless-provider.md
- https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3-nano-30b-a3b-infer

The engines are implementation specs with private TypeScript reference packages,
not assumed pip packages. `world_model_fact` maps to real WorldModel.assertFact
input with observation time/provenance; `hmem_add_input` maps to real HMEM.add input
with source/confidence/provenance/lineage. Keeper must deduplicate H-MEM writes:
the upstream reference allocates sequential memory IDs, not idempotency keys.

A genuine isolated upstream H-MEM reference engine proof ran successfully at commit
`1742dec56a66e58eef9dda2d2b865823758ca8cd` on Node v22.22.2: add → disk persistence →
new-instance hydration → query → audited store.update invalidation. Input was an
explicit **development fixture**, not a validated NYC finding. Temporary storage
was removed afterwards. Receipt: `reports/meterless_reference_smoke.json`.
This proves the reference engine operates; it does not establish production/shared
Meterless integration. World Model adoption awaits Keeper approval. Planner/Keeper
must choose the authoritative store, conflict policy, transport/auth, atomic version
checks, event cursors, invalidation propagation and production storage/conformance.
Do not use a last-write-wins attribute to silently override Critic vetoes or identity.

## Reproduction

From the repository root, using the already installed integration virtualenv:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B critic.py critic-fixtures.json
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/investigate_address.py '840 Second Avenue' --borough Manhattan --goals property_identity --reasoning model --max-pages 1 --max-requests 8 --output reports/production_model_readiness --trace-jsonl reports/production_model_readiness/activity.jsonl
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/investigate_address.py '840 Second Avenue' --borough Manhattan --provider replay --replay reports/production_model_readiness/investigation_report.json --goals property_identity --reasoning deterministic --output /tmp/byte-rock-production-replay
node --experimental-transform-types scripts/smoke_meterless_reference.mjs /tmp/byte-rock-meterless-reference
```

The last command requires the inspected official checkout. Restore it with
`git clone https://github.com/Meterless/Meterless.git /tmp/byte-rock-meterless-reference`
and check out the recorded commit for exact reproducibility. No npm runtime packages
were installed. The Node type-transform flag is experimental and only used by this
isolated proof, never by the Python production path. Live-model pytest remains opt-in
and requires model environment settings; the address command provides the real-run
proof once valid settings exist. No commits or pushes were made.

Validation checkpoint: **160 pytest passed, one opt-in live-model test skipped**;
**12/12 unchanged root-Critic fixtures passed**. Canonical package import, an injected
three-role model address run, deterministic replay of the real capture, and the
upstream H-MEM proof also passed. The final real capture has one shared run ID/task
ID across 67 trace events and records successful cleanup. Fixture and injected-model
tests establish wiring and contracts, not live model accuracy. Model accuracy,
provider JSON-mode support and underlying Nightshift fleet identity still need a
credentialed live smoke test before the demo claims Nemotron reasoning.

## Credentialed live-model follow-up

NVIDIA configuration was found in ignored `.env.local`. A bounded structured smoke
passed with configured and API-returned model `nvidia/nemotron-3.5-bolt-e4b`.
Receipt: `reports/nvidia_live_smoke.json`.

A fresh real Zetaris investigation of 840 Second Avenue, Manhattan completed
ResearchPlan, ResearchDraft and CriticReport through that model: three actual model
calls, eight returned source rows, verified identity, two accepted factual findings
and successful namespace cleanup. Duration: approximately 89 seconds. Capture:
`reports/nvidia_live_identity/`. Structured receipt: `reports/nvidia_live_verification.json`.

Legal review remained INCONCLUSIVE: semantic review was INCONCLUSIVE; deterministic
review requested REVISE for unsupported legal conclusions, unknown/invalid evidence
dependencies, false evidence classification and citation mismatches. The terminal
merge remained INCONCLUSIVE. This proves live inference, not reliable legal conclusions.

The live run exposed the older board adapter allowing an INCONCLUSIVE draft through
on record membership alone. Publication now requires completed/PASS, matching the
new Keeper adapter. Root Critic policy is unchanged. The saved model captures were
re-rendered through the corrected gate, without further inference: zero legal
findings are published. Original model drafts and reviews remain available for audit.
A regression covers this gate; the earlier replay test now explicitly expects
inconclusive findings to be withheld.

The broader habitability attempt retrieved 74 real rows and 14 accepted facts, but
mandatory provenance/uncertainty exceeded the context budget before inference.
`reports/nvidia_live_address/` preserves that scaling limitation. The narrower run
kept all existing context limits. No fallback or revision cycles were used.

Reproduce from the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 LEGAL_MAX_REVISIONS=0 LEGAL_MAX_MODEL_CALLS=3 LLM_TIMEOUT=60 .venv/bin/python -B scripts/investigate_address.py '840 Second Avenue' --borough Manhattan --goals property_identity --reasoning model --max-pages 1 --max-requests 8 --output reports/nvidia_live_identity --trace-jsonl reports/nvidia_live_identity/activity.jsonl
```

No configured secrets were found in the new NVIDIA artifacts. No commits or pushes
were made. Shared Meterless adoption and broader-context scaling remain open.
