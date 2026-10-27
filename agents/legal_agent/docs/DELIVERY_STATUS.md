# Delivery status — dynamic NYC tenant-risk investigation

> **Historical development log.** This file records an earlier checkpoint. Its test counts, "not verified" statements and
> `reports/...` file references describe that moment only: `reports/` held local, gitignored captures that are not in this
> repository. Current status and verified results are in the [root README](../../../README.md).

## Actual verification

- Machine-readable sources with genuine Zetaris row retrieval: 17. HCR/court references: three manual-only capabilities.
- Real address-resolution captures succeeded in all five boroughs, including ZIP 10009, 10466, 11223, 11414 and 10305.
- Full Manhattan run: 30 accepted factual findings for 840 Second Avenue. Legal assessment: inconclusive.
- Focused Queens run: 1 accepted factual finding for 102-15 1 Street. Legal assessment: inconclusive.
- Both report provider=zetaris, mode=live. Exact-query offline replays succeeded with mode=recorded_replay and no network calls. Development fallback is explicit and mock-tested; it was not used for these runs.
- Final tests: 123 passed, one explicitly opt-in live-model test skipped; root Critic fixtures 12/12 passed. Existing original sample tests were preserved.
- Actual credential-value scan: clean. Generated JSON parses. Final active temporary namespace count: zero. Original bounded demonstration source preserved. Nothing committed or pushed.

## Limitations and team dependencies

- Legacy DOB permits returned a row in the source capability probe and in an earlier property run, but timed out in the final Manhattan run. The final report marks that source unavailable and does not reuse its earlier results.
- Exact historical extents are not claimed. Publisher scope descriptions/update frequencies are retained; paging exhaustion applies only to the current exact filter. Live datasets can change between offset pages.
- General DOB NOW Build data excludes some specialty Electrical/Elevator/LAA records; FDNY coverage is the official FDNY subset of OATH, not all fire inspections.
- HCR unit rent history and WebCivil Local/Supreme/NYSCEF remain manual-only. No court cases or unrestricted APIs were fabricated, no restrictions bypassed, and no de-identified statistics were attributed to an address.
- R5 holds records identical apart from their own IDs as possible duplicates; `integration.py` gives it a content signature so distinct same-day records are kept (see ROOT_CRITIC_HANDOFF.md). Source IDs remain in the audit and no root rule was changed or bypassed.
- Legal applicability/version retrieval and live Nightshift model validation remain unverified. Deterministic planning/research/review is explicitly labelled. The report does not certify safety or liability.
- Keeper must persist the emitted board projection in World Model; the team Conductor/Matcher/Reporter must connect their runtime and product-verdict policy. No competing memory database was created.

## Changed implementation files for this expansion

- `identity.py`: street ordinal normalization, retaining the existing resolver.
- `agents/planner.py`: provider-neutral source selection by goals, identity first, disabled-source handling.
- `integration.py`: held/missing registration-parent dependency veto; no change to root Critic.
- `data/source_registry.json`: configurable verified schemas, IDs, publisher/update/coverage metadata, classification and manual capabilities.
- `tools/source_registry.py`: registry validation.
- `tools/address_data.py`: compatible paginated provider interface, bounded temporary Zetaris REST namespaces, explicit fallback/replay, budgets, cleanup and sanitized error categories.
- `tools/risk_mapping.py`: agency-preserving evidence mapping, scope/stage distinctions and source-qualified IDs.
- `address_investigation.py`: address/borough/unit resolution, lot cross-check, strongest-identifier retrieval, bounded correction requests, factual/legal separation and Keeper board projection.
- `risk_reporting.py`: seven-category renter report with citations, source coverage, held audit, patterns and legal uncertainty.
- `scripts/investigate_address.py`: live/fallback/replay CLI.
- `scripts/verify_risk_sources.py`: genuine source capability probes.
- `scripts/verify_nyc_addresses.py`: real multi-borough identity retrieval checks.
- `tests/test_address_investigation.py`: new synthetic safeguards, pagination/budget tests, original sample regression and recorded real-data tests.
- `README.md` and `docs/DYNAMIC_ADDRESS_INTEGRATION.md`, `docs/VERIFIED_SOURCE_INVENTORY.md`, `docs/ROOT_CRITIC_HANDOFF.md`: usage, source inventory, limitations and ownership handoff.

## New real verification artifacts

- `reports/zetaris_filter_probe.json`: fixed REST request/SQL filter and cleanup proof.
- `reports/source_metadata.json`: public official source schemas and publisher metadata.
- `reports/source_runtime_inventory.json`: actual source capability statuses/agency ID samples.
- `reports/multi_borough_addresses.json`: actual source-selected/resolved addresses.
- `reports/address_840_second_avenue/investigation_report.json` and `.md`: full real multi-source investigation, raw retrievals, provenance and board update.
- `reports/address_queens_102_15_1_street/investigation_report.json` and `.md`: focused real investigation beyond the old ZIPs.
- Earlier `reports/sample_report.*` and the original recorded HPD capture remain unchanged as the bounded-demo regression baseline.
