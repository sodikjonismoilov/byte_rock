# Legal retrieval and recoverable review loop — 2026-10-26

> **Historical development log.** This file records an earlier checkpoint. Its test counts, "not verified" statements and
> `reports/...` file references describe that moment only: `reports/` held local, gitignored captures that are not in this
> repository. Current status and verified results are in the [root README](../../../README.md).

## Reproduced before editing

Inspected the full saved 840 Second Avenue capture, imports, schemas, actual ModelAgents
calls, ReadOnlySearch, workflow outcome handling, catalog contents and existing tests.
Re-executed the captured plan through the original ModelAgents with a captured draft
and a search spy. Receipt: `reports/legal_retrieval_before.json`.

- Plan selected two `evidence_review` actions, no `legal_search`.
- `research` executed searches only when explicitly selected by that plan. It therefore
  supplied zero authorities even though LegalSearchTool existed.
- The plan schema accepted `mem-2`/`mem-3` in evidence_ids. F002 put them in factual
  dependencies and legal source_ids. There was no reference-domain schema separation.
- Reviews were INCONCLUSIVE → deterministic REVISE → merged INCONCLUSIVE; the workflow
  returned immediately at INCONCLUSIVE, before following the legal-search request.
- All 18 original catalog entries had excerpt=null. Returning a summary would not
  itself provide authoritative source text, even after the tool-selection defect was fixed.

## Changes to the existing subsystem

`agents/model_agents.py` describes actual available tools, provides substantive topics
from accepted records, enforces an authority lookup if model planning omits one, and
executes model-selected searches before interpretation. Model reasoning remains live;
the minimum lookup is an explicit retrieval precondition, not heuristic reasoning fallback.
Original source hits are attached by runtime, never trusted from model output.

Model payloads distinguish accepted evidence, retrieved legal authority IDs and memory
context IDs. Citation pairs give exact identifiers to copy. Full-diligence categories
come from the existing scope function; each needs a concise finding or explicit gap.
The Researcher must prioritize substantive duties supported by records and cannot
infer current unsafe conditions or liability from filings/administrative noncompliance.
The semantic Critic receives invalidated finding diagnostics too, rather than silently
omitting them from its draft view.

`models/schemas.py` keeps existing JSON ID strings and adds distinct reference types:
EvidenceId, AuthorityId and MemoryId. Optional memory_ids fields are context references
only. Schemas reject mem-* in authoritative fields, known catalog authority IDs in
factual evidence fields, and official record IDs in legal-authority fields. Runtime plan
membership checks independently require the actual accepted evidence/memory registries.
Unknown evidence dependencies are invalidated, not left valid in reusable findings.
These are additive legal-local contracts plus intentionally stricter invalid-reference
validation; root Critic and Keeper contracts were not replaced. Original bad run files
remain unchanged for audit and are not promoted to valid new model outputs.

`workflow.py` retains merged INCONCLUSIVE decisions, but may continue for a new actionable
legal/evidence repair. ModelAgents.queue_followups executes up to two concrete actions,
prioritizing legal authority lookup, and injects required follow-up tasks into the revised
plan. The same lookup string cannot manufacture repeated progress. Retrieved authorities
survive later model failures via the executed search cache. Revisions remain capped at
two, model calls at the configured maximum (at most nine), legal searches at the configured
maximum (at most ten), with unchanged aggregate deadlines and read-only tool permissions.

BLOCKED remains terminal before retrieval/research. Missing inspections, current conditions
and externally held facts do not automatically become legal-search retries. No Critic
outcome is rewritten to PASS/REVISE merely to continue. All earlier semantic, deterministic,
merged and root reviews remain retained. A valid dependency DAG can be topologically
ordered, including dependencies on injected required follow-up tasks; duplicate IDs,
unknown task references and cycles still stop execution.

`context.py` prioritizes contradictory records and violations, retains full conflict and
coverage information, deduplicates identical memory hints and authority references, and
advertises only the evidence/authority items actually included in the projection. Full
records and original legal text remain outside prompt compression. Existing byte/token
ceilings and explicit omission manifests remain enforced.

`tools/execution.py` now traces exact legal-search strings and returned authority IDs.
`InvestigationResult.citation_audit` separately records retrieved-source membership,
exact identifier matching, official excerpt availability, accepted evidence dependencies,
validity and historical-version verification. A verified source URL/ID is not a verified
legal conclusion or proof of historical applicability.

## Official source text

The catalog now contains exact excerpts for seven authorities, with URL, retrieval time,
excerpt hash, method and version limitations. Five NYC pages were fetched and captured
with raw-page hashes and normalized page text. NY Senate direct HTTP returned 403; its
RPP 235-B and MDW 78 statutory paragraphs were inspected through the official-page web
reader and are labeled as such. No successful direct fetch or raw-page hash is invented.
Snapshots: `data/legal_authority_snapshots.json`; catalog: `data/legal_sources.json`.

- HPD heat/hot water, indoor allergens, clearing violations
- DOB occupancy and boiler guidance
- NY Real Property Law §235-b and Multiple Dwelling Law §78

The DOB boiler authority addresses accepted boiler-related records; no investigation
datasets or infrastructure were added. Other catalog entries remain explicitly summary-only
where authoritative text was not captured. Current-page text is not asserted to be the
operative law for an older incident. historical_version_verified remains false. The
local search tool cannot supply missing historical legislation simply because a query
requests it; that gap still needs qualified external verification.

## One bounded live-model replay

Command executed from the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 LEGAL_CONTEXT_MAX_BYTES=60000 LEGAL_CONTEXT_MAX_TOKENS=60000 LEGAL_MODEL_MAX_TOKENS=100000 .venv/bin/python -B scripts/investigate_address.py '840 Second Avenue, Manhattan, NY' --borough Manhattan --provider replay --replay reports/investigations/20261026T035040435638Z_d27bd49e-6969-42cd-b7aa-478930b1d4d3/investigation_report.json --reasoning nvidia --memory-dir .local/legal-memory-demo --model-timeout 60 --max-model-calls 9 --max-revisions 2 --output reports/legal_retrieval_replays
```

Output directory:
`reports/legal_retrieval_replays/20261026T042556265473Z_6dc25e28-f718-44ff-9a98-3924a66f3b25/`.
Exact action/citation/decision receipt: `reports/legal_retrieval_verification.json`.

Recorded NYC rows were replayed: **no fresh Zetaris query**. NVIDIA inference was live
using `nvidia/nemotron-3.5-bolt-e4b`; H-MEM was the actual local reference engine. The
legal tool retrieved the curated official-text snapshots, not a historical-law web service.

Observed: seven model calls, four legal_search calls, 15 retained authorities, two
revision cycles, approximately 152 seconds. Two complete Planner/Researcher/Critic
rounds occurred; the seventh model call returned a revision plan that failed dependency
validation. No memory IDs appeared as factual evidence or legal authority citations.

Exact legal_search strings:

1. `What are the relevant New York City Housing Maintenance Code (HMC) duties pertaining to boilers, heat, and hot water for a building registered under HPD jurisdiction (HPD Building ID 1571)? HMC Boiler Heat Hot Water`
2. `Retrieve the operative version of NYC Administrative Code § 27-2031 and RPL § 235-b effective as of 2009-01-01, 1992-03-03, and 2020-02-19.`
3. `Verify exact legal authority identifiers and source text boiler heat hot water water`
4. `Retrieve the operative version of NY Real Property Law § 235-b and relevant NYC Administrative Code sections (e.g., 27-2029, 27-2031) as they were in effect on the dates of the recorded violations (e.g., 2009-01-01, 1992-03-03, 2020-02-19).`

Both review rounds: semantic INCONCLUSIVE, deterministic REVISE, merged INCONCLUSIVE.
Critic follow-ups actually executed despite that outcome. Final draft citation audit:
four references had retrieved, excerpt-backed source IDs (three hpd-heat-hot-water,
one dob-boilers); **zero** had matching supplied authority identifiers; one finding
put an authority ID in its factual evidence field. Historical applicability remained
unverified. Zero legal findings were published. This proves retrieval and targeted
follow-up, not model accuracy or resolved legal liability.

After observing this replay, schema checks were tightened to reject that authority-as-
evidence mistake, unknown dependencies were invalidated, valid forward DAGs were ordered,
and category/citation instructions were clarified. Those additional hardening changes
are pytest-verified, not claimed to have a second live replay. Unknown/cyclic dependency
plans still stop. The original replay report and trace remain untouched.

## Validation and remaining limits

Full pytest: **221 passed, one live opt-in test skipped**. Separately executed live replay
above verifies real calls. Official H-MEM conformance: **13/13**; unchanged root Critic
fixtures: **12/12**. Tests cover required authority retrieval and exact text/provenance,
memory/cross-domain ID rejection, different Critic-triggered searches, model/revision
bounds, no retry on external gaps or BLOCKED, contradictions and deduplication, and
acyclic/unknown dependency handling. Existing Zetaris and H-MEM tests remain passing.

No root Critic policy was changed. No citation requirement or publication gate was weakened.
Current/historical law applicability and model citation reliability remain unresolved where
identified by review. No commits or pushes were made.
