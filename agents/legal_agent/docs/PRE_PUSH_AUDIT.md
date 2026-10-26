# Legal Agent stabilization and pre-push audit

## Scope

Presentation-only renter report improvements plus documentation, safe synthetic test
inputs and Git hygiene. No model formatting call, pipeline redesign, new source,
Critic policy edit, citation-repair cycle or live service request was introduced.
`risk_reporting.write_renter_report()` groups already accepted observations, gives a
plain-language overview/summary, retains every record/date/status/link and consolidates
caveats. Closed/dismissed records are never presented as current conditions. Missing,
manual, unavailable, bounded and actual no-record outcomes remain distinct. Malformed
or unavailable legal review cannot populate the legal-context section.

The local example at `reports/final_polish_example/renter_report.md` is rendered
from the saved 840 Second Avenue evidence, not a fresh investigation. It preserves
16 accepted factual observations, including four historical DOB violation records
marked dismissed. It is PARTIAL and factual-only; no legal conclusion or risk score
is added. This generated report and its original capture are intentionally not staged.

## Integration-readiness findings

- **Address CLI:** `scripts/investigate_address.run_investigation` delegates to
  `address_investigation.investigate_address` and existing identity, evidence,
  reconciliation and `LegalResearchWorkflow`. Fresh run IDs/directories retain
  reports and traces on controlled failures. Offline replay is covered by a safe,
  explicitly synthetic fixture shipped with the tests.
- **NVIDIA:** `tools.llm.JSONModelAdapter` uses the configured actual model and
  validates structured output. Previous live Planner/Researcher/ Critic requests
  exist locally. Latest Critic response failed evidence-ID validation: invocation
  is demonstrated, successful full live legal publication is not. No silent fallback.
- **H-MEM:** `memory.LegalMemory` calls `scripts/hmem_bridge.mjs` and the vendored
  official engine. Real engine cold/warm persistence and validated storage are tested;
  prior address replays retrieved two memories. Failed/unapproved legal work does
  not become durable authoritative memory. Official conformance is checked locally.
- **Meterless/Nightshift provider:** Runtime v4 normalization, real authentication,
  routing IDs, discovery, plain text and failure states have transport-based tests.
  Nightshift configuration is a legacy alias to this contract. No live Nightshift
  or current HTTP Runtime success is claimed; endpoint availability/configuration
  remains an external prerequisite.
- **Shared context:** `integration.board_update` exports original evidence,
  authority refs, publication-filtered legal findings, coverage gaps, source/review
  limitations and status. `SharedInvestigationState.read/update` is a versioned
  in-process handoff; tests cover concurrent updates, stale writes, copy isolation
  and root BLOCKED. `LegalSharedAdapter`/`KeeperPort` and `world_model_fact` remain
  the Keeper boundary/mapping. Global orchestration, transport and a shared World
  Model service are **awaiting the team**, not implemented here. No memory database
  or competing Planner was added.
- **Root Critic/publication:** existing root functions are imported unchanged;
  source attribution, accepted dependencies and BLOCKED precedence are enforced.
  Local/model Critic histories and rejection diagnostics stay in the audit. Invalid
  Critic output cannot publish findings. Legal PASS is not required for a successful
  factual-report workflow.
- **Trace and execution:** `events.ActivityTrace`/`JSONLEventSink` append sanitized
  JSONL events; tests exercise credential redaction, revisions, errors and shared
  handoff. `ExecutionBudget`, bounded adapters and workflow enforce hard deadlines,
  tool/model limits, one truncation retry and the two-revision ceiling. Complete
  requests include schema/instruction overhead in their budget.

## True integration limits

The global orchestrator must own the shared adapter/transport; it is absent here.
The current provider may still return an invalid semantic Critic response, leaving
legal review INCONCLUSIVE and legal publication unavailable. Live gateway/dataset
registration and provider credentials must be supplied externally. Source page caps,
manual court/HCR/unit-history checks, unknown historical law applicability and current
property conditions prevent a complete safety or liability determination. These do
not block the independently validated factual-report path.

## Clean checkout and Git safety

The agent README supplies root-relative `.venv` setup, exact live and deterministic
commands, variable names without secret values and generated artifact locations.
Historical commands no longer require the previous temporary virtualenv. Local
captures referred to in historical audit notes are intentionally not included.
Tests formerly dependent on private generated reports now use minimal labeled
synthetic fixtures or synthetic transport scenarios instead. Five-borough and
held-dependency behavior are exercised directly rather than asserting local receipts. Original public legal-authority excerpts/provenance and
vendored H-MEM license/upstream hashes are included as necessary source assets.

Generated `reports/`, JSONL traces, `.env*` secrets, `.local/` memory/preferences,
bytecode, caches, virtualenvs, node_modules and private-key files are ignored. Only
necessary legal source, helper scripts, tests, safe fixtures, dependency declarations,
documentation and ignore/example configuration changes are staged. Root README,
BRIEF and root Critic/spec/fixtures are not changed. The complete staged file list
is [STAGED_FILES.txt](STAGED_FILES.txt). Validation/staged-diff results are appended
below after the final index and clean-export checks. No commit or push is authorized.

Recommended feature-branch commit message:
`feat(legal): integrate bounded NYC investigation and renter reports`

## Final validation results

- Workspace and isolated clean index export: **279 passed, 1 skipped, 0 failures**.
  The skip is the explicitly opt-in live-model smoke test. Focused renter-report,
  shared-handoff, append-only tracing/redaction and invalid-Critic publication
  regressions are included in this full suite.
- Official H-MEM conformance: **13/13**. Root Critic fixtures: **12/12**.
- Clean export: fresh virtualenv installed only the declared requirements, no local
  `.env.local`, generated captures or memory copied. The documented fictional-address
  replay ran with no credentials and generated the expected INCONCLUSIVE legal /
  factual-only report (exit 2). Root fixtures and official H-MEM also passed there.
- Example renter report regenerated offline from the existing accepted real-record
  capture; no NVIDIA, Runtime HTTP or Zetaris requests were made for this pass.
- **134 files staged**: all previously untracked legal implementation and required
  helpers, not merely this presentation patch. Generated reports/raw captures,
  persistent H-MEM, private provider settings, caches and virtualenvs are excluded.
  The staged manifest includes every staged path, including itself.
- Complete staged contents scanned against configured credential values and private
  key/API-key patterns: **zero matches**. No forbidden local artifacts staged.
  Root Critic/spec/fixtures and teammates' root project files remain unchanged.
- `git diff --cached --check` passes. No commit or push performed. The current
  feature branch is `captain/legal-reasoning`; human approval remains required.
