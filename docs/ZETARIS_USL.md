# Zetaris USL — deployed and verified

**Overall: PASS for this bounded three-source USL demonstration.** On
**2026-10-27 03:20:12 UTC**, the resumed live attempt compiled/deployed
`renter_records_v1`, activated `events`, executed all three prepared queries, and
registered/executed `source_identity_integrity`. This is an actual Zetaris USL,
not an ordinary view or a substituted direct API result. The application pipeline
and its citation/property-matching safeguards remain unchanged.

A [sanitized execution summary](receipts/zetaris_usl_verification.md) publishes the
verified milestones, aggregate counts and SQL template hashes for submission.

## Verified milestones and receipts

- **PASS — namespace:** authenticated SQL listed
  `lightning.metastore.signsafe_usl_20261026`, initially empty. The user had created
  this namespace manually in the Gateway UI after the earlier missing-parent error.
- **PASS — real source schemas:** all three existing REST tables were described
  again. HPD exposes 39 columns, the bounded DOB projection 7, OATH 6. Required
  source columns were present and reported as string. Activation explicitly casts
  to string-compatible model types; original identifier/date/status values remain.
- **PASS — exploratory queries:** two SELECTs per source succeeded again (six total).
- **PASS — compile/deploy:** the unchanged [model DDL](../sql/zetaris_usl/model.sql)
  was sent intact with `COMPILE USL ... DEPLOY` into the existing namespace.
- **PASS — activation:** the unchanged [activation SQL](../sql/zetaris_usl/activate.sql)
  bound the model to the three existing sources. Working USL SELECTs prove activation,
  beyond merely accepting a DDL response.
- **PASS — three USL queries:** counts by dataset, counts by original status, and
  original record/identifier/date/provenance inspection all returned actual rows.
- **PASS — DQ:** the unchanged [rule](../sql/zetaris_usl/dq.sql) was registered, listed,
  then executed: **240 total / 240 valid / 0 invalid** for this rule and bounded slice.

The single resume deployment used **23 SQL requests in 31.321 seconds**, under the
40-request / 420-second bounds. It issued **zero** source-registration commands,
namespace-creation commands, UPDATEs, REMOVEs or DROPs. An empty-namespace check was
repeated immediately before deployment to avoid overwriting existing USLs.

Actual ignored receipts:

- `reports/sponsor_compliance/usl_resume_namespace_check.json`: the two preliminary
  read-only namespace visibility/empty-child checks.
- `reports/sponsor_compliance/usl_resume_verification.json`: exact SQL, statuses,
  timings, source schemas, exploration results, USL query results and DQ counts.
  DDL responses retain result metadata/hashes rather than arbitrary server bodies.
- `reports/sponsor_compliance/usl_verification.json`: preserved **historical** initial
  attempt, which stopped at namespace creation with
  `parent namespace : metastore is not existing`. Its failure was not overwritten
  or relabeled as a success. The namespace prerequisite is now resolved.

## Business use case and source scope

Renters need consistent record IDs, raw property identifiers, event dates, statuses
and official citations across agency datasets. The semantic model exposes those
columns through one contract. It deliberately uses **UNION ALL, not property joins**:
identity resolution, reconciliation and root Critic decisions remain in the existing
application. No property match, current condition or legal liability is inferred.

Existing objects used unchanged:

- HPD violations (`wvxf-dwi5`):
  `signsafe_hpd_20261025.hpd_violations`, bounded ZIP 10017 source, cap 200.
- DOB permits (`ipu4-2q9a`):
  `signsafe_usl_20261026_sources.dob_permits`, ZIP 10017, cap 20.
- OATH (`jz4z-kudi`):
  `signsafe_usl_20261026_sources.oath_fdny`, ZIP 10017, FDNY subset, cap 20.

The two latter sources were registered in the earlier attempt, not recreated by
resume. Their [reusable source definitions](../sql/zetaris_usl/sources.sql) remain
available for a fresh separately owned setup. REST data is accessed through Zetaris;
no new direct NYC API application path was introduced.

## SQL, model and observed results

Parameters used:

```text
namespace = signsafe_usl_20261026
source_db = signsafe_usl_20261026_sources
hpd_table = signsafe_hpd_20261025.hpd_violations
```

The runner substitutes validated identifiers into `${...}` templates; do not paste
unresolved template variables into the SQL editor. Supported compilation, activation
and DQ syntax follows the [official Zetaris reference](https://github.com/zetaris/getting-started/blob/main/docs/guides/zetaris-lightning-sql-commands.md#13-unified-semantic-layer).

[Exploration](../sql/zetaris_usl/explore.sql) executes a `LIMIT 3` original-ID/date/status
sample and a status/count grouping for **each** source. All six succeeded. HPD returned
11 original status groups totaling 200; DOB returned 19 `ISSUED` and 1 `RE-ISSUED`;
OATH returned 19 `NEW ISSUANCE` and 1 `HEARING COMPLETED`. A hearing status is not an
adjudicated violation finding; a historical/dismissed record does not prove a current
condition. No respondent names or addresses were selected for these demonstrations.

The [full DDL](../sql/zetaris_usl/model.sql) declares twelve nullable scalar columns:
`dataset_id`, `record_id`, `bin`, `bbl`, `hpd_building_id`, `borough`, `block`, `lot`,
`event_date`, `record_status`, `source_url`, `scope_note`.
The [activation](../sql/zetaris_usl/activate.sql) retains original record IDs and raw
identifiers, constructs official per-record URLs from original agency IDs, and records
source caps/link limitations. Missing identifiers are NULL, never invented. OATH raw
borough/block/lot values are not represented as verified building links. Original
heterogeneous date/status text is retained without claiming normalized chronology.

[The three executed USL queries](../sql/zetaris_usl/verify.sql) target:
`lightning.metastore.signsafe_usl_20261026.renter_records_v1.events`.

1. Dataset counts: `ipu4-2q9a` **20**, `jz4z-kudi` **20**, `wvxf-dwi5` **200**.
2. Dataset/original-status counts: **15 groups**, retaining the same source labels
   and totals as exploration.
3. Original record/provenance inspection: **3 actual rows**, including original HPD
   violation IDs, raw BIN/BBL/building ID, event dates/statuses and source-record URLs.
   Detailed rows remain in the ignored receipt rather than committed raw evidence.

## Registered and executed data quality

`source_identity_integrity` checks a nonempty original ID, one of the three allowed
dataset IDs, an official source-URL prefix, and correctly shaped BIN/BBL when present.
Missing OATH BIN/BBL is allowed; it is not replaced by a guessed property identity.
It does **not** certify ownership/linkage, record truth, uniqueness, date applicability,
current safety, complete provenance semantics or legal compliance.

The receipt confirms the named rule appeared in `LIST DQ USL`, followed by:

```sql
RUN DQ source_identity_integrity TABLE lightning.metastore.signsafe_usl_20261026.renter_records_v1.events
```

Returned columns: `name`, `table`, `type`, `total_record`, `valid_record`,
`invalid_record`. Actual result: `source_identity_integrity`, `events`,
`Custom Data Quality`, **240**, **240**, **0**. This is not a mock result or a
claim that the complete citywide datasets have no data-quality issues.

## Safe resume and read-only recheck

The helper uses the existing ignored `.env.local` connector. No credentials or
private origins belong in SQL or command arguments. Source setup is once-only per
fresh owned source namespace; the normal setup path refuses existing objects.

The following was the **single executed resume deployment command**:

```sh
.venv/bin/python scripts/verify_zetaris_usl.py --resume --namespace signsafe_usl_20261026 --hpd-table signsafe_hpd_20261025.hpd_violations --output reports/sponsor_compliance/usl_resume_verification.json
```

`--resume` requires a visible existing **empty** semantic namespace and existing
source database, verifies actual source schemas/rows, and skips source/namespace
creation. It rechecks emptiness before compile and stops on the first failure.
**Do not repeat resume now:** this namespace contains the deployed USL and should
be refused rather than overwritten. No second deployment attempt was made.

For a future **read-only** recheck of the deployed objects:

```sh
.venv/bin/python scripts/verify_zetaris_usl.py --namespace signsafe_usl_20261026 --verify --output reports/sponsor_compliance/usl_readonly_recheck.json
```

This option does not create/overwrite/activate/register objects. It reissues source
exploration, USL SELECTs and the already registered DQ evaluation. The mode is covered
by unit tests; a separate post-success live recheck was not needed or performed.

## Benefits, future use and product requirement

Without a shared model, each consumer repeats three source projections, heterogeneous
ID/date/status names and provenance construction. The active USL now centralizes that
mapping; identity reconciliation remains separate. **Estimate, not benchmark:** a
subsequent developer query could save roughly 10–20 minutes of mapping/validation
work. This excludes initial setup, schema maintenance and incident resolution. No
query-latency/storage saving was measured; federation can still read bounded REST data.

Future use: let the Records Clerk query the canonical event contract for multiple
addresses, then pass exact IDs and scope limits to the existing Matcher/root Critic.
Adopt it only after regression comparison with the working source path; this pass
intentionally leaves that application path unchanged. Source caps, manual court/HCR
checks, unverified property linkage, historical law and present conditions remain limits.

**Proposed Zetaris enhancement:** an authorized USL preflight API should report
missing versus hidden namespace parents, required privileges, and structured per-table
compile/activation/DQ state. Acceptance: the earlier missing-parent scenario identifies
an actionable administrator step without a stack trace or partial mutation, exposes a
read-only activation check, and never auto-creates global namespaces or grants rights.
Manual UI provisioning resolved the prerequisite here; it does not remove the value
of clearer preflight diagnostics.
