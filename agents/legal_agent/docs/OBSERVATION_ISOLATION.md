# Strict observation isolation

The model-facing `CanonicalResearchDraft.findings` is a list of independently
validated observations. Each observation cites property evidence and retrieved
legal authorities directly; the wire schema does not define finding-to-finding
support. The existing public ResearchDraft and citation contracts remain unchanged.

`citations.validate_observations()` now handles only complete nontruncated
Researcher responses. The full original schema validates first. If failures are
strictly inside individual observations, the unchanged envelope and original array
limit are checked, each observation is validated with the same retrieved-ID schema,
and every invalid observation is discarded **in full**. A valid citation inside a
rejected observation does not rescue part of it. Ambiguous duplicate observation IDs
prevent isolation. Malformed JSON, envelope errors, unknown global evidence references
and oversized arrays remain fatal. Survivors are validated again as a complete draft.

The parser never substitutes IDs, generates citations, fills required fields or
turns a valid source identity into a supported legal claim. Original records and
executed search results remain authoritative. Canonical metadata grounding and
independent legal Critic support/topic/jurisdiction/applicability gates still apply.
Root accepted factual findings are separate; root BLOCKED precedence is unchanged.

Rejected observations emit `research.observation_rejected` with index, safe finding
ID, content hash, validation paths/types and `accepted_as_claim=false`. Raw rejected
claims, unknown IDs and response text are not put in activity logs. Counts emit as
`research.observations_validated`. A caveat tells the Critic that observations were
discarded. Existing agent/Critic trace events record actual reviews and outcomes.

If all observations are invalid, `legal.review_unavailable` records the reason and
execution ends INCONCLUSIVE without calling the legal Critic on an empty rescued
draft. The CLI's existing `renter_report.md` remains PARTIAL — FACTUAL-ONLY, with
accepted official-record observations and coverage limits. Truncation handling,
complete-request budgets, H-MEM separation, shared-state handoff and append-only
trace operations are unchanged.

## Validation

**263 tests passed, 1 opt-in live test skipped**. Targeted tests cover mixed
observations, rejecting the whole bad observation, all-invalid termination, successful
Critic execution and independent support verification for a retained observation,
factual-only reporting, root BLOCKED, malformed/envelope/global-reference failures,
original array limits and ambiguous IDs. Official H-MEM conformance **13/13**; root
Critic fixtures **12/12**. Root policy files were not changed.

One bounded live NVIDIA replay uses the original 840 Second Avenue Zetaris capture,
with local persistent H-MEM, the same 60000-byte complete-request cap, 2048 output
tokens, at most nine model calls, two revisions and the existing hard deadline.
It is recorded-data replay with live reasoning, not a new Zetaris data refresh.
Exact sequence, results and artifact paths are recorded in
`reports/observation_isolation_verification.json`. No second live replay, commit or
push is part of this pass.

## Observed single replay

Run `128e7353-e2fd-428d-b197-446738002802` took **54.0 seconds**. Both Researcher
observations passed the original retrieved-ID schema, so zero observations were
rejected in this live sample. Isolation itself was demonstrated by the mixed and
all-invalid regression tests, not claimed as a live event that did not happen.

The live model Critic **was invoked**, after successful planning and Researcher
validation. Its response then failed the existing evidence-ID validation at
`issues[1].evidence_ids[0..2]`. No Critic decision was accepted; the deterministic
Critic stage after that model response did not run. No publication gate was bypassed,
and no further replay or unrelated Critic-schema repair was attempted.

The independent grounding/audit checks recorded **2 valid source identities** and
**2 verified exact source-text claims**, citing current HPD heat guidance
(`hpd-heat-hot-water`) and the provided RPL §235-b excerpt (`rpl-235-b`). This is
**not** a completed Critic review: Critic-verified citations **0**, published legal
findings **0**, historical applicability **unverified**. Both original sources and
provenance remain in the JSON audit. All three complete model requests were below
60000 bytes (53822, 59285 and 59561 respectively).

Sixteen accepted factual findings, two retrieved H-MEM memories, the existing shared
handoff and append-only trace were preserved. H-MEM storage was skipped. The final
`renter_report.md` is explicitly PARTIAL — FACTUAL-ONLY. Recorded source pagination,
manual HCR/unit rent-history and court checks, present conditions, and historical
law remain limitations. Six run/receipt files passed the configured-secret scan.
