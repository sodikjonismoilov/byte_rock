# Historical one-dataset setup proposal (superseded)

The REST onboarding path has now succeeded for both HPD Building Files and
violations. The sections below record the pre-onboarding proposal, not current
status. Use [TEAM_INTEGRATION.md](TEAM_INTEGRATION.md) for the verified live run,
actual table names, reproduction commands and remaining limitations.


## Verified discovery

The original connector works. `ZETARIS_ENGINE_ID` is unset after loading the
ignored `.env.local`, so the query body omits `engineId`. The server chooses the
backend. The engine registry (`/compute/engines`, found in the deployed frontend)
returns an empty list, and SQL responses do not expose an engine ID or name.
Do not equate SQL's database name with the engine name or invent an engine ID.

Actual SQL context: `current_catalog()` = `spark_catalog`, `current_database()` =
`default`. `SHOW TABLES IN default` succeeds with no tables. `SHOW DATASOURCES`
and `SHOW UNITY CATALOG` both succeed with zero rows. The frontend's registered
sources, lakehouse, Unity Catalog and metastore-database APIs also return empty
lists. Unqualified SHOW TABLES/SHOW DATABASES are disabled by this deployment.
There are no discoverable NYC records in this configured organization/account
and SQL context. This is not a claim about other accounts, engines or permissions.
See `reports/zetaris_discovery.json` for the captured authenticated responses.

## Recommended minimum (no registration executed)

Use only NYC HPD **Housing Maintenance Code Violations**, dataset `wvxf-dwi5`:
[official dataset](https://data.cityofnewyork.us/Housing-Development/Housing-Maintenance-Code-Violations/wvxf-dwi5),
[column metadata](https://data.cityofnewyork.us/api/views/wvxf-dwi5.json).
The official metadata was read successfully; no property records were fetched
directly by the legal agent. Registering one source is enough for a scoped first
investigation, but not the brief's final multi-dataset reconciliation demo.

1. **Clerk prepares one bounded real snapshot for ingestion.** Export rows for
   ZIP 10017 or 11103 from the official dataset. Retain original field names and
   all original rows. Record the source URL/filter, export timestamp, row count,
   pagination/truncation and time window in a manifest. This is data-layer
   preparation, not an agent-side substitute for querying Zetaris. A bounded
   snapshot cannot establish that no other violations or complaints exist.
2. **Upload and register through the existing Zetaris UI.** Its documented File
   System supports file upload, followed by registration as a File Source.
   Register that snapshot with a deliberately NEW source/table name chosen at
   creation time. No existing table name or local-to-cloud filesystem path is
   assumed here. Keep identifiers as strings when defining the schema, preserve
   leading zeros, and preserve nulls/dates/status text. If the cloud File System
   is unavailable, use the same UI's documented REST API connection against the
   official dataset endpoint instead; verify pagination before claiming coverage.
   These are proposed setup actions, not completed registration or ingestion.
3. **Verify before using the data.** Rerun `scripts/discover_zetaris.py`. Discover
   the actual new table and inspect its schema. Through the ORIGINAL connector,
   read a bounded set of rows from that exact discovered table. Use read-only
   credentials. The proxy has no verified bind-parameter contract: retrieve a
   reviewed fixed batch and filter the address in Python rather than interpolating
   renter input into SQL. Preserve its snapshot/export timestamp separately from
   the time it was queried through Zetaris.
4. **Select the sample from returned data.** Choose an actual supported address
   in 10017/11103 with a consistent HPD building ID and available BIN/BBL. Do not
   select a fictional fixture or manufacture a missing identifier. Consolidate
   one provenance-backed candidate for that building. Mixed building IDs or
   uncertain address ranges remain unresolved. For an address-only run, prefer
   building-scoped records; unit records remain held unless the task targets the
   same unit. Unknown present status remains a limitation.
5. **Use the existing integration.** Pass Zetaris row dictionaries to
   `tools.zetaris.map_hpd_rows(rows, retrieved_at=...)`, then use the existing
   identity resolver, root-Critic bridge, legal workflow and report renderer.
   Preserve Matcher confidence in metadata when available; no confidence is
   invented by the HPD mapper. Write a real capture/replay only after this path
   succeeds. No reporter verdict or legal-review PASS certifies rental safety.

Zetaris setup references:
[File System upload and registration](https://kbase.zetaris.com/knowledge/file-system-overview),
[connection wizard](https://kbase.zetaris.com/knowledge/connect),
[SQL discovery/registration reference](https://kbase.zetaris.com/knowledge/sql-manual).
File upload avoids building a fresh infrastructure service or resolving REST
pagination inside the agent before the first demonstration.

## Ready independently of registration

`map_hpd_rows` uses verified NYC column names: `violationid`, `buildingid`, `bin`,
`bbl`, `housenumber`, `streetname`, `inspectiondate`, `currentstatus`, `class`,
`novdescription`, `apartment`, plus original borough/ZIP/status metadata.
It emits `wvxf-dwi5:<violationid>`, retains the original ID, source-record URL,
retrieval timestamp, date/status/class and scope. A closed HPD violation remains
a historical violation record; it is not an open-condition assertion. Missing
dates/identifiers remain missing. Duplicate source IDs fail closed.

`identity_candidate` and the resolver already accept HPD/BIN/BBL provenance;
`authoritative=True` is a trusted Clerk assertion, not an independently performed
government identity lookup. Root rules and local scope safeguards exclude held
records. Legal applicability remains unresolved until operative authority versions
are checked. Shared-board payloads, report rendering and labelled mock feedback
loops remain usable without a live dataset. No second memory system was added.

The mapper is tested with explicitly synthetic rows, not presented as live data.
No paid service, new database, registration, committed secret, or fake property
report is needed to complete this setup proposal.
