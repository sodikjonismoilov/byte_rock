# One-command observable address investigation

Use the existing address CLI. It calls `address_investigation.investigate_address`;
agent execution remains in the existing workflow, identity resolver, reconciler and
local/root Critic adapters. No alternate orchestrator or global state store was added.

From `/Users/yawen/Desktop/projects/byte_rock`, the exact verified command is:

```bash
PYTHONDONTWRITEBYTECODE=1 LEGAL_CONTEXT_MAX_BYTES=60000 LEGAL_CONTEXT_MAX_TOKENS=60000 LEGAL_MODEL_MAX_TOKENS=100000 .venv/bin/python -B scripts/investigate_address.py '840 Second Avenue, Manhattan, NY' --borough Manhattan --reasoning nvidia --memory-dir .local/legal-memory-demo --page-size 5 --max-pages 1 --model-timeout 60 --output reports/investigations
```

The three context variables explicitly configure the already supported prompt bounds
for the full source-family run. Context still has a 60,000-byte ceiling; complete
payloads retain their separate 64,000-byte guard and complete messages have a
100,000-byte conservative token ceiling. The defaults are deliberately smaller and
can stop a broad investigation before inference. These settings do not change the
300-second aggregate deadline, tool/model attempt budgets or Critic gates. Five rows
per page and one page bound retrieval; coverage gaps remain visible. No safety or
complete-history conclusion is implied by completing the pipeline.

Every invocation creates a new private timestamp/UUID child of `--output` (also
`--output-root`). The default parent is `reports/investigations`. Run IDs and task IDs
are shared by all stages. Repeating a command does not overwrite earlier artifacts.
`--unit 4B` is optional; borough may be supplied separately or inferred conservatively.

## Modes and configuration

- `--reasoning nvidia`: explicitly chooses the existing direct NVIDIA adapter,
  irrespective of another environment default. Requires real NVIDIA settings.
- `--reasoning nightshift`: explicitly chooses the existing Meterless Runtime alias,
  with authenticated model discovery, real runtime token and a discovered routing ID.
  Its 180-second per-call wait is still constrained by the aggregate deadline.
  No local runtime was available at the prior integration checkpoint.
- `--reasoning deterministic`: existing labeled heuristic agents, no model calls.
- Legacy `model` and `configured` choices remain available. Model/provider errors
  produce structured incomplete/error outcomes; they never switch to deterministic.

Live retrieval defaults to the existing Zetaris connector and its ignored `.env.local`
configuration. Missing credentials yield visible unavailable/error status; they do not
activate direct NYC API access. `--provider nyc-development-fallback` is an explicit,
separately labeled development option. `--memory-dir` opts into persistent legal-local
H-MEM; `LEGAL_MEMORY_DIR` also enables it. Only completed/PASS validated findings become
long-term memory. Inconclusive runs can persist review feedback, not their draft claims.

Existing limits can be selected explicitly with `--deadline-seconds`, `--max-tool-calls`,
`--max-model-calls`, `--max-revisions`, `--model-timeout`; Pydantic retains all existing
hard maximums. Defaults come from ExecutionLimits/from_env. Invalid configuration still
produces diagnostic artifacts when the output directory can be created.

## Four artifacts per run

- `investigation_report.md`: identity, accepted factual records, coverage, reviewed legal
  findings only, uncertainty, termination errors and review history.
- `investigation_report.json`: existing schema 2.0 report and compatible board_update,
  plus additive run ID, root review history, execution and activity fields. Full source
  records remain here; unapproved model drafts are audit diagnostics, not findings.
- `trace.jsonl`: always-on, append-only events with run/task/event IDs and UTC times.
  Includes source/tool calls, root decisions on every pass, reconciliation, agent starts,
  context selection, model metadata/durations, memory operations, revisions and termination.
  No prompts, raw records, credentials or unnecessary address/unit data are emitted.
- `run_summary.json`: status/exit code, termination reason, provider/model metadata,
  durations, coverage, budgets, errors and absolute artifact paths. This is operational
  metadata, not another team investigation-state contract.

The optional old `--trace-jsonl` writes an additional sink; the canonical run-directory
trace is always present. Semantic, deterministic and merged legal reviews accumulate.
`root_critic_history` retains each attribution pass while `record_decisions` remains
the final decision list expected by existing consumers. Root Critic policy is unchanged.

Exit codes: **0** completed legal assessment; **2** inconclusive/incomplete (including
veto/budget stops); **1** operational error. Exit 2 still saves all artifacts. The CLI
saves diagnostic reports on setup errors, processing exceptions, interrupts and normal
renderer failures when feasible. Hard process kills or an unwritable/full filesystem
cannot guarantee final artifacts. Python cannot kill running transport threads; late
cleanup events may append after termination when a remote operation finishes late.

## Verified live run

Run ID: `d27bd49e-6969-42cd-b7aa-478930b1d4d3`.
Directory:
`reports/investigations/20261026T035040435638Z_d27bd49e-6969-42cd-b7aa-478930b1d4d3/`.

Observed sequence:

1. Run/configuration → official Building Files identity lookup and lot cross-check.
2. All 20 configured source entries considered: 17 automatic families plus three
   manual-only entries. Coverage: five retrieved, eight bounded, four no-record
   slices, three manual-only. No-record slices are not proof of clean history.
3. 54 returned rows across queries; 48 distinct mapped audit records. Root review
   performed two attribution rounds after a cross-identifier follow-up. All earlier
   decisions were retained. Sixteen factual findings passed membership/scope gates.
4. Reconciliation → H-MEM recall of two non-authoritative review hints → context selection.
5. Three real NVIDIA calls returned ResearchPlan, ResearchDraft and CriticReport using
   `nvidia/nemotron-3.5-bolt-e4b`. Legal search executes only if selected in the model plan.
6. Semantic review INCONCLUSIVE, deterministic gate REVISE, merged INCONCLUSIVE.
   Unsupported/citation/evidence-classification issues remain visible; zero legal
   findings were published. The terminal inconclusive did not trigger another revision.
7. H-MEM stored review feedback only → namespace cleanup removed → report/summary written
   → run.finished. Approximately 94 seconds, 42 tool attempts and three model attempts;
   457 events. The process returned exit 2 with useful reports, not a fabricated success.

The recorded model outputs establish live invocation, not model accuracy. Meterless
Runtime inference was not used in this run; H-MEM is the actual local reference engine.

## Deterministic offline replay

No live credential files or model endpoints are loaded for this mode. From the repo root:

```bash
.venv/bin/python -B scripts/investigate_address.py '840 Second Avenue, Manhattan, NY' --borough Manhattan --provider replay --replay reports/investigations/20261026T035040435638Z_d27bd49e-6969-42cd-b7aa-478930b1d4d3/investigation_report.json --reasoning deterministic --output reports/offline_investigations
```

Replay uses exact captured query filters. A different address, unit or source plan may
produce explicit capture gaps. Replay artifacts say `recorded_replay`; they are not fresh
Zetaris retrieval. Omit `--memory-dir` to keep replay independent of Node/H-MEM too.

## Tests

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider
.venv/bin/python -B critic.py critic-fixtures.json
```

The CLI tests cover mocked full-stage execution, model invocation metadata, revision
history, root rechecks, actual H-MEM operations, hard-stop reasons, failure reports,
renderer fallback, secret redaction, unique consecutive runs and offline replay.
The separately executed live run above verifies real NVIDIA and Zetaris wiring.
No commits or pushes were made.

Final regression result: **205 pytest passed, one opt-in live-model test skipped**;
root fixtures **12/12**. The live run's 457 JSONL events exactly match the report's
activity projection and share one run/task ID, with unique event IDs. A configured-
secret scan found no matches in its four artifacts. The documented offline replay
also ran successfully without loading credentials and produced its own new directory:
`reports/offline_investigations/20261026T035657761934Z_984b94c8-8425-448f-9a12-92d1e210555b/`.
