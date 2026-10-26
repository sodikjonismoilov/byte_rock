# Dynamic multi-source tenant-risk investigations

## What works

The default address-driven command accepts a NYC street address, borough and
optional apartment. It does not select a sample property, filter a fixed ZIP,
or reuse the old 200-row demonstration as citywide data. It supports seven risk
categories and keeps three outputs separate: source retrieval/coverage, accepted
factual records, and legal assessment. A legally inconclusive result does not
suppress independently accepted facts.

```bash
python scripts/investigate_address.py '840 Second Avenue, Manhattan'
python scripts/investigate_address.py '102-15 1 Street' --borough Queens --goals habitability
python scripts/investigate_address.py '840 Second Avenue, Manhattan' --provider replay --replay reports/address_840_second_avenue/investigation_report.json --output /tmp/signsafe-replay
```

Outputs: `investigation_report.md` and `investigation_report.json` under the
selected `--output` directory. The JSON includes original records, source URLs,
agency IDs, scopes, event/status fields, exact paged query URLs, page timestamps,
held decisions, planning/retrieval activity, legal review and a Keeper board
projection. Original source statuses and descriptions are not reinterpreted as
present conditions or legal liability.

## Verified REST behavior and bounded lifecycle

The initial `signsafe_hpd_20261025` tables still exist as bounded historical demo
sources. They are not used by the new address-driven command. Their registered
REST request contains fixed ZIP/limit parameters. The actual filter probe in
`reports/zetaris_filter_probe.json` verified that querying a different building
ID downstream does not recover a record excluded by the registered request.
`SHOW CREATE TABLE` is not supported here; the original executed registration
SQL is preserved in the onboarding trace. No claim of undocumented SQL predicate
pushdown is made.

The new provider places all property filters, order, limit and offset explicitly
in the upstream NYC REST URL before registering a page. Current documented
`CREATE LIGHTNING REST TABLE ... REQUEST (...) HEADER () BODY ()` works through
the original `zetaris_api.zetaris_request` proxy. The older `REGISTER REST` syntax
was rejected. This is verified registration, not a renamed direct API result.

One unique `signsafe_run_<uuid>` Lightning namespace is owned per run. There is
a page/table cap (default 40, maximum 80), a per-source page cap (default 2), a
page size cap (maximum 500), and an active owned-namespace guard (3). Failed
registration/retrieval is reported, never replaced by fictional data. On exit,
the entire owned namespace is removed with `DROP LIGHTNING DATABASE`, which was
verified against this deployment. `DROP TABLE` was rejected for a REST table;
it is not used for cleanup. Existing teammate and original demo sources are not
altered. Cleanup errors remain visible and the namespace guard prevents unlimited
orphan accumulation.

## Identity and source selection

The existing normalizer/resolver is reused. The original input is retained.
Building Files is queried by source-supported house-number/range endpoints,
street variants and borough, without a ZIP restriction. Only official range
endpoints become aliases; intermediate addresses are not invented. Multiple
matching buildings or incomplete identity pagination remain unresolved. An
address missing from HPD coverage produces a structured identity gap and stops
record attribution; there is no claim that all NYC residences appear in HPD.
No new fuzzy geocoder or non-HPD identity service is claimed.

BIN, HPD building ID and BBL are cross-checked through existing identity rules.
BBL derived from Building Files uses its official borough/block/lot components,
whose provenance is preserved. A separate lot query records other HPD building
IDs. Lot-only evidence remains property-scoped even when the target building is
identified. Unit records require the requested unit; entity contacts require an
explicit registration-to-building join.

`agents/planner.py:plan_sources` keeps identity first and chooses source families
from the requested goals. The whole configurable source registry remains visible
in coverage, including disabled/not-selected/manual sources. Source filters use
the strongest available identifier. FDNY/OATH uses verified violation-location
borough/block/lot and its observed agency value, never respondent mailing
addresses. Unsupported linkage is disclosed rather than guessed.

All filters are encoded into a fixed official NYC host. Free-form renter addresses
never enter downstream SQL. Text literals are escaped for SoQL and identifiers
come from verified schema configuration. Socrata `:id` is used for legacy permit
paging because sorting by the agency key timed out; original agency permit IDs
remain the citation keys.

## Coverage, autonomy and safeguards

Short pages exhaust the exact current filter. Full last pages at the cap are
explicitly bounded, never silently complete. Shared request budgets apply across
all sources and follow-ups. Repeated/missing agency IDs fail a source closed;
their raw retrieval remains auditable. Live source changes during offset paging
are possible, so no transactional snapshot is promised. Dataset publisher history
descriptions are preserved, but exact full historical extents are not claimed.

Clear R1/R2 conflicts can request at most two cross-identifier correction queries
globally. New source IDs receive fresh matching and root review. Existing held
evidence is retained; unchanged attempts stop. No retry or failure is fabricated
in a live run. The legal workflow keeps its own existing bounded critique and
revision limits. R5's same-day false-duplicate risk is documented for its owner
in [ROOT_CRITIC_HANDOFF.md](ROOT_CRITIC_HANDOFF.md), without a rule bypass.

Complaints remain complaints, summonses remain administrative records rather than
automatic adjudications, permits/jobs are not findings of unsafe work, and
executed marshal actions are not eviction filings. HPD litigation is not a
complete WebCivil/NYSCEF court search. Unit rent status and present safety cannot
be inferred from building history. Verified source links and explicit applicability
limits accompany background legal references.

## Provider and state boundaries

The existing `PropertyDataProvider.fetch` interface remains available; paginated
`fetch_where` extends access for verified source filters. The Planner, legal
Investigator, resolver and Critics receive the same existing identity/evidence
contracts and do not call data providers. This is Conductor-facing integration,
not another Conductor, Critic or persistent memory service.

Direct NYC access requires explicit `--provider nyc-development-fallback`, and is
labelled in every retrieval and report. It never silently substitutes for Zetaris.
Replay requires `--provider replay --replay <report.json>` and exact recorded
queries; a new property cannot reuse another property's capture. Original source
timestamps are retained. Synthetic test providers remain labelled mock.

Keeper's World Model remains authoritative. The emitted board projection contains
identity provenance, source evidence, accepted facts, legal findings/reviews,
coverage, held decisions and follow-ups. It does not persist a competing memory
database or promote summaries into source evidence. The team's root Critic,
Reporter, original connector and public specialist entry point are preserved.

## Sources and verification artifacts

- [VERIFIED_SOURCE_INVENTORY.md](VERIFIED_SOURCE_INVENTORY.md): 17 actual
  machine-readable sources, three manual references, schema and coverage limits.
- `reports/source_runtime_inventory.json`: real source row-verification capture,
  distinct from property coverage.
- `reports/multi_borough_addresses.json`: actual address-resolution retrievals in
  all five boroughs, including ZIPs outside the original demo scope.
- `reports/address_840_second_avenue/`: genuine full multi-source run.
- `reports/address_queens_102_15_1_street/`: genuine focused run outside the old ZIPs.
- Original `reports/sample_report.*` and `recorded_hpd_investigation.json` remain
  available for the earlier bounded sample regression.

Official references: [Zetaris current SQL guide](https://kbase.zetaris.com/knowledge/sql-guide),
[REST example](https://kbase.zetaris.com/knowledge/sugarcrm),
[Socrata system fields](https://dev.socrata.com/docs/system-fields.html),
[HPD data documentation](https://www.nyc.gov/site/hpd/about/open-data.page),
[HCR reference](https://hcr.ny.gov/office-rent-administration-ora),
[court access limitations](https://www.nycourts.gov/e-courts/ecourts-contact-us).
