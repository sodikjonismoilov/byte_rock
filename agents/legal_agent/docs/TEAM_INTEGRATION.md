# Hackathon integration boundary

> Current safeguard/model/context/tracing status: [production integration checkpoint](PRODUCTION_INTEGRATION.md).
> Earlier deterministic-only execution notes below describe the original captures.

## Current execution status

A genuine Zetaris-backed investigation now works. The original connector and
root Critic were not modified. The newly created physical source is
`signsafe_hpd_20261025`, with verified REST tables `hpd_buildings` (official
Building Files `kj4p-ruqc`) and `hpd_violations` (`wvxf-dwi5`). Actual table
listings and row queries confirm both; no preexisting NYC tables were assumed.

Important discovery correction: `SHOW DATASOURCES` lists logical sources and can
remain empty while physical REST databases exist. Use `SHOW LIGHTNING DATABASES`
and `SHOW TABLES IN <actually discovered source>`. The older `REGISTER REST`
syntax was rejected. Current documented `CREATE LIGHTNING REST TABLE ...
REQUEST (...) HEADER () BODY ()` succeeded. See the failed/successful attempt
trace and separate successful verification in `reports/zetaris_onboarding*.json`.

The real sample is **840 2 AVENUE, Manhattan 10017**: HPD building ID **1571**,
BIN **1038763**, BBL **1013370050**. BBL is deterministically formed from the
Building Files borough/block/lot fields, with those inputs preserved, then
cross-checked against supplied violation BBLs. Eight real violation rows were
retrieved for this building; two passed the unchanged root Critic, five were
held by its broad R5 collision rule, and one was quarantined. Held records are
retained in the audit but never support published findings. R5's same-day/address
heuristic is not proof that the distinct violation IDs are duplicates.

The sourced report is **inconclusive**: local curated legal authorities have not
been version-verified for operative applicability. Data retrieval and identity
are live; legal planning/research/critique are explicitly deterministic, with no
live model claim. General background authorities are not property liability
findings. The initial source endpoints are bounded to ZIP 10017: buildings cap
5000, violations cap 200 ordered by descending violation ID. This is not complete
building/city history or a present-condition inspection.

Configuration is loaded from ignored `.env.local`: `ZETARIS_BASE_URL`, numeric
`ZETARIS_ORG_ID`, and API key or username/password. `ZETARIS_ENGINE_ID` is unset;
server-side routing selects the backend, whose identity remains unexposed.
No credentials were printed, copied into reports, committed or pushed.

## Reproduce the working path

From the repository root, with the legal agent requirements installed:

```bash
python scripts/onboard_hpd.py --source signsafe_hpd_20261025
python scripts/investigate_hpd.py --provider zetaris --source signsafe_hpd_20261025
python agents/legal_agent/examples/replay_investigation.py reports/recorded_hpd_investigation.json --output /tmp/signsafe-hpd-replay
```

Onboarding preserves existing tables and verifies actual rows. The investigation
checks actual discovery before querying configured table identifiers. Numeric
building IDs are validated before entering SQL; address text never enters SQL.
No undocumented bind API, engine ID or existing table is invented.

`PropertyDataProvider.fetch` is the provider boundary. `RecordBatch` carries raw
rows, dataset ID, provider, timestamp, query reference and bounded-coverage flag.
The coordinator maps those rows into the existing identity/evidence contracts;
the Planner, Investigator, resolver and Critics do not make provider calls.
`investigate_legal_issue(task, context)` remains the public specialist interface;
the coordinator uses `LegalResearchWorkflow` for explicit deterministic mode or
an injected workflow/model adapter. The team Reporter still owns verdict policy.

An explicitly selected development fallback is available via
`--provider nyc-development-fallback`. It never silently replaces failed Zetaris
calls and labels source strings, result `data_mode` and `data_provider` as a
fallback. It was unit-tested with synthetic transports, not used in the live
sample. Captured real records are labelled `recorded_replay` when reused.

## Responsibility matrix: actual implementation

| Check | Root Critic | Legal specialist | Evidence/tests |
|---|---|---|---|
| BBL/borough/geo/era attribution | `review_link`, R1–R4 | Existing identifier conflict checks retained; external matches consumed | Root fixtures T02–T05; `test_record_identifiers_win_over_address` |
| Same-dataset collision | R5: same date/address, not a semantic duplicate proof | Reconciliation groups shared origin keys | T06; `test_disagreement_duplicates_and_history` |
| Address/class/confidence | R6–R8 quarantine; `llm_review` remains a placeholder | No second geo/confidence adjudicator; retain scope veto | T07–T10; `test_root_bridge_keeps_quarantined_records_out` |
| Source membership | `review_finding`, R9–R10; membership, not semantic entailment | Existing standalone accepted-registry checks retained; bridge calls root gate before publication | T11–T12; `test_external_rejections_cannot_support_findings` |
| Complaint/inspection/violation distinction | No legal classification check | `critique_draft` compares evidence kinds and rejects complaint-as-violation | `test_researcher_distinguishes_complaints_and_violations`; `test_unsupported_interpretations` |
| Legal citation identity and retrieval | No legal authority check | `critique_draft` checks retrieved IDs and corresponding identifiers | `test_source_identifier_mismatch`; `test_critic_rejects_unsupported_legal_conclusion` |
| Jurisdiction/effective dates | No legal applicability check | Known NY/NYC/date bounds checked; unknown operative version/date is unresolved outside legacy sample mode | `test_effective_dates_checked_at_incident`; `test_real_mode_unknown_source_version_is_unresolved` |
| Building/lot/unit/entity scope | No explicit scope check | Existing scope rules; external review cannot upgrade BBL-only building links; selected lot-to-unit claims flagged | `test_bbl_review_does_not_upgrade_scope`; `test_missing_unrelated_and_unit` |
| Liability, unit rent status, eviction stage | No semantic legal check | Selected phrase guards and classification checks; not comprehensive natural-language proof | `test_unsupported_interpretations`; `test_legal_critique_revises_actual_bad_draft` |
| Critique/revision | Returns veto; no Matcher/Conductor implementation | Changed plans, bounded local revisions, deterministic review after model critique, review history | `test_model_workflow_replans_and_preserves_unaffected_findings`; new mock legal loop |

The existing registry-membership guards are retained for standalone compatibility;
no duplicate persistent state or new general Critic was introduced. New integration
delegates team membership decisions to `review_finding`. Semantic support remains
limited: nonempty source IDs and regex guards cannot prove arbitrary prose.
Unknown applicability yields INCONCLUSIVE, not repeated impossible revisions.
Selected unsafe assertions request REVISE with finding IDs and corrections.

## Contracts and state ownership

Additive fields preserve existing required JSON fields: `data_mode` in context
and result, plus result `caveats` and `review_history`. JSON schemas regenerated.
Default mode remains `sample` for existing callers; real callers must explicitly
set `live`. Non-sample runs disable fixture lookup and reject explicitly supplied
sample identities. Unreviewed runs retain existing local matching. Reviewed runs
require complete, unique coverage of the snapshot; missing decisions fail closed.
Do not expose external-review acceptance as a public trust bypass: the local Flask
routes are still unauthenticated hackathon endpoints, for trusted orchestration.

`integration.board_update` is a JSON projection for the Keeper, not a Meterless
API implementation. It carries original source evidence separately from legal
findings, identity, root decisions, legal review history and follow-up requests.
Evidence-free category findings become coverage gaps. Findings with unavailable
or rejected IDs are withheld using root R9/R10 against legally accepted IDs.
Original evidence is preserved for audit, including rejected records; it is not
automatically an approved claim source. Keeper must preserve these distinctions.
No World Model client exists in this checkout. Existing `MemoryAdapter` is an
unwired H-MEM protocol, not proof of World Model integration. Do not add another
memory database. Summary text is not source evidence.

## Validation and teammate dependencies

91 legal tests passed, one live-model smoke test skipped; root fixtures pass 12/12.
New scenarios are explicitly MOCK, including root reject/corrected-retry and legal
REVISE/changed-plan/PASS. No failures or retries were fabricated in a live run.
Test dependencies were installed in a temporary environment outside the repo.

Pending: Clerk expansion beyond bounded HPD REST sources and full coverage verification;
Matcher verified card/confidence and correction loop; Conductor global retry and
timeout budget; Reporter verdict and product rendering; Nightshift adapter/live
model validation; Keeper World Model persistence and load-twice test. Catalog
legal authorities remain curated background sources with unverified operative
versions. No new substantive legal advice was asserted from them. No real
sample address, legal finding or safety verdict can be claimed yet.
