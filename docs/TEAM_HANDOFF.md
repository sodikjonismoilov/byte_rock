# Team Handoff — Final Integration and Submission Checks

**Audience:** the Planner's coding agent and component owners, not judges.
No runtime policy, application code, SQL, tests or deployed objects were changed by
this documentation pass. The judge-facing narrative is [SPONSOR_TECH.md](SPONSOR_TECH.md).

## Captain's completed work and exact paths

The Legal Agent was merged through `867106a` / merge `dc54a60`: bounded address-based
Zetaris retrieval, identity/reconciliation, model-backed legal stages, canonical
citations, review gates, H-MEM, versioned handoff, append-only traces and factual-only
reporting. H-MEM conformance is 13/13; root fixtures previously passed 12/12.

The USL is deployed independently at
`lightning.metastore.signsafe_usl_20261026.renter_records_v1.events`. The actual
2026-10-27 verification compiled/deployed and activated it, ran six exploratory and
three USL queries, and evaluated DQ at **240 total / 240 valid / 0 invalid**.
The [safe receipt](receipts/zetaris_usl_verification.md) contains exact source counts,
time, scope and SQL hashes; [the appendix](ZETARIS_USL.md) contains deployment details.

Sponsor-compliance additions currently present in the Captain's working tree:

```text
docs/SPONSOR_TECH.md
docs/ZETARIS_USL.md
docs/TEAM_HANDOFF.md
docs/receipts/zetaris_usl_verification.md
scripts/verify_zetaris_usl.py
sql/zetaris_usl/activate.sql
sql/zetaris_usl/dq.sql
sql/zetaris_usl/explore.sql
sql/zetaris_usl/model.sql
sql/zetaris_usl/sources.sql
sql/zetaris_usl/verify.sql
tests/test_zetaris_usl.py
```

These additions are **not yet committed**. Do not assume they are available remotely
until the Captain publishes an approved commit. The inspected Planner revision is
`origin/recovered/all-work` at `6df8fe7f5534beb068ef6cf6e0b1ded1752ba67b`.
There was no pending-path overlap in the read-only audit; semantic review still matters.

## Owners and acceptance checks

### Captain — evidence and documentation delivery

- Obtain human approval before committing/publishing the additions. Keep generated
  `reports/`, raw receipts, traces, `.env.local`, private tokens and `.local/` memory
  out of Git. The safe Markdown receipt contains no raw records or private endpoints.
- Verify all SQL hashes against the source files and recorded executed statements.
  Do not rerun setup or resume: the USL already exists. A future authorized check
  should use the documented `--verify` mode.
- Keep pinned Planner evidence links until the final integrated commit is known;
  then make repository-relative links where appropriate and recheck them.

**Acceptance:** a reviewable commit contains the twelve listed paths, safe evidence
is linked from both guides, and unrelated teammates' files remain unchanged.

### Planner — front door, routing, samples and real-data demo

The committed integration branch contains `run.py`, `webapp.py`, `web/`, synthetic
sample input, Docker configuration, and front-door/web tests. Live execution defaults
to `LLM_PROVIDER=meterless` and configured reasoning, with explicit overrides.
H-MEM defaults to `.local/legal-memory`; containers need a persistent `/app/.local`
volume, plus `/app/outputs` if artifacts must survive container replacement.

- Preserve CLI and web `SAMPLE_MODE`. Demonstrate the fictional recording through
  the final entry point, with explicit replay/provider labels and no credentials.
- Run a real-address investigation through the final front door using Zetaris and
  Nightshift. Use a real input, not the synthetic `1 Mock Street` fixture. Record
  data mode, provider, root attribution results, configured route, returned model
  identity, stage outcomes, final reports and source limitations in a sanitized
  application-level receipt. Never force legal PASS; a useful factual-only outcome
  can be valid when legal review is INCONCLUSIVE.
- The committed [Nightshift smoke receipt][smoke] already shows four aliases returning
  HTTP 200 and `nvidia/nemotron-3.5-bolt-e4b`. The [Planner README][planner-notes]
  separately documents three model calls during a synthetic Nightshift investigation;
  its full trace remains local. Do not substitute that smoke receipt or README
  statement for final real-Zetaris-plus-Nightshift execution evidence.
- Check startup configuration and defaults from both CLI and web, including empty
  optional variables and `.env.local` loading. Do not claim every call uses Nightshift
  when an explicit provider override was selected.

**Acceptance:** final synthetic CLI/web runs and one real-data run produce complete
artifacts and trustworthy provider/model traces. A failed Critic response publishes
no legal claims. Model identifiers alone do not prove the provider route.

### Planner / Records Clerk — USL consumption boundary

The active USL is a standalone verified model. Neither inspected `run.py`, `webapp.py`
nor the existing data provider consumes it. Keep that boundary explicit in README
and demo, or implement adoption as separately reviewed work with regression evidence.
Do not replace arbitrary-address retrieval with a ZIP-limited 240-record slice.

**Acceptance:** the demo identifies what actually queries the USL. If the Investigator
adopts it later, original agency IDs, provenance, NULL identifiers, scope/caps and
root matching behavior are retained and compared with the working source path.

### Root Critic developer + Legal owner — R5 and verdict policy

The Planner's `agents/legal_agent/integration.py` appends a content signature to
`record_date` before root review, changing effective R5 collision behavior while
`critic.py` itself remains unchanged. Review this input-contract change, its excluded
ID fields, same-day duplicate semantics and date/year handling. Tests exist in
`test_review_records_r5.py` and the revised address tests; tests do not replace owner
approval of the policy.

The new `verdict.py` also counts selected R8-quarantined `unit_mismatch` apartment
records after checking identifiers, separately from accepted factual findings.
`compute_verdict()` does not explicitly inspect BLOCKED. Decide and document whether
and how this separate verdict may use held evidence; keep legal publication distinct.

**Acceptance:** R1/R2/R4 and agreed R5 behavior remain correct; held/rejected evidence
is not silently promoted into accepted legal claims; another apartment's condition
is not asserted for the requested unit. Test BLOCKED precedence through verdict,
report and UI. A policy veto must not become an unqualified confident recommendation.

### Planner + Legal owner — persistent-memory scope isolation

`SAMPLE_MODE` uses a synthetic `recorded_replay`, but `LegalMemory._scope()` currently
classifies only `sample` / `mock` as sample and otherwise uses `official`. Both modes
share a default storage directory. Review the scope key before making a sample/live
isolation claim; distinguish fictional replay from replay of genuine agency records.
Do not make a blanket change treating every recorded replay as synthetic.

**Acceptance:** separate-process cold/warm application runs show persistence and
idempotency, while fictional/sample context cannot be recalled as live context or
vice versa. Retain provenance and memory/evidence separation. H-MEM's official
conformance alone does not prove this application-level boundary.

### Planner / QA — final combined verification

Captain validation recorded **290 passed, 1 skipped** (including 11 USL helper tests).
The inspected Planner README separately reports **384 passed, 1 skipped**.
Neither is a result for the final combined tree. Run and record the actual new total:

```sh
.venv/bin/python -m pytest -q agents/legal_agent/tests tests/test_zetaris_usl.py
HMEM_IMPL="$PWD/agents/legal_agent/vendor/hmem/src/index.ts" node --experimental-transform-types agents/legal_agent/vendor/hmem/conformance/runner.ts
.venv/bin/python critic.py critic-fixtures.json
SAMPLE_MODE=true .venv/bin/python run.py input_examples/1.json
```

Also exercise the browser sample flow, trace polling, source links/downloads,
credential redaction, partial/failure reporting, model schema failures, cold/warm
memory and the actual deployment environment. The live-model smoke test is opt-in;
offline passing tests are not a live provider demonstration.

**Acceptance:** exact commit/environment/test totals and sanitized demo evidence are
recorded; no private local capture is required for clean-checkout sample execution.

### Team / submission owner — README, demo and declarations

Add links to both sponsor documents and the safe receipt without overstating USL
adoption or real-data model execution. Suggested root README text:

```markdown
## Sponsor technology

See [Sponsor Technology Integration](docs/SPONSOR_TECH.md) for implementation and
verification evidence, and [Zetaris USL](docs/ZETARIS_USL.md) for SQL and deployment.
The [sanitized USL receipt](docs/receipts/zetaris_usl_verification.md) records the
actual bounded execution and data-quality result.
```

Confirm actual Cursor use with teammates; the supplied Legal Agent history includes
Codex and does not establish exclusive Cursor development. Declare the pre-existing
H-MEM engine/license, public datasets/legal texts and any pre-build prepared assets.
Complete the demo video, slide deck, required examples/outputs, final repository
links/visibility and submission form. Keep the distinct deterministic functions and
three model-backed legal stages clear rather than presenting seven UI roles as seven
autonomous model agents.

**Acceptance:** README and demo match the final source/receipts, required sponsor
claims have appropriate evidence, and owners sign off before submission.

[smoke]: https://github.com/sodikjonismoilov/byte_rock/blob/6df8fe7f5534beb068ef6cf6e0b1ded1752ba67b/docs/receipts/nightshift_smoke.json
[planner-notes]: https://github.com/sodikjonismoilov/byte_rock/blob/6df8fe7f5534beb068ef6cf6e0b1ded1752ba67b/README.md#nightshift--nvidia
