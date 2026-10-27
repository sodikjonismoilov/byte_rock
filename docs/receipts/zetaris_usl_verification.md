# Zetaris USL — sanitized live verification

This is a publication-safe summary of an actual authenticated Zetaris execution,
derived from the saved local verification receipts. It is not mock output or a new
execution performed during documentation preparation. Raw records and private service
configuration are intentionally excluded.

## Deployment identity and time

- Semantic namespace: `lightning.metastore.signsafe_usl_20261026`.
- USL model: `renter_records_v1`.
- Activated table: `lightning.metastore.signsafe_usl_20261026.renter_records_v1.events`.
- Successful verification began: **2026-10-27T03:20:12.746992+00:00** (UTC).
- Single resumed deployment: **23 SQL requests / 31.321 seconds**.
- Platform response identified Zetaris **2.4.3.1**.
- The existing namespace was visible and empty before deployment; the three sources
  already existed. No sources or namespaces were recreated. No pre-existing object
  was overwritten or deleted.

## Sources and verified record counts

- **HPD Housing Maintenance Code violations — `wvxf-dwi5`: 200 records.**
- **DOB permit issuance — `ipu4-2q9a`: 20 records.**
- **FDNY-subset OATH administrative records — `jz4z-kudi`: 20 records.**

These are bounded ZIP 10017 source slices: HPD cap 200, DOB cap 20, OATH cap 20.
They are not complete citywide histories, a representative statistical sample or
verified records for one building.

## Successfully executed milestones

1. **Actual schemas inspected:** HPD 39 columns, DOB projection 7, OATH projection 6;
   required source columns were present.
2. **Six exploratory queries succeeded:** two per source, comprising an original-ID /
   date / status sample (`LIMIT 3`) and a status/count grouping. Each sample returned
   three rows. Status groupings totaled 200 HPD, 20 DOB and 20 OATH records.
3. **Compilation and deployment succeeded:** `COMPILE USL renter_records_v1 DEPLOY`
   used the existing semantic namespace and the linked model definition.
4. **Activation succeeded:** the linked activation query bound `events` to the three
   registered sources, preserving original IDs, raw identifiers, date/status text
   and official per-record provenance URLs. Missing identifiers remain NULL.
5. **Three USL verification queries succeeded:**
   - Dataset counts returned three groups: HPD 200, DOB 20, OATH 20.
   - Dataset/original-status counts returned 15 groups.
   - Original-record/identifier/date/provenance inspection returned three rows;
     their raw contents are intentionally not reproduced here.
6. **Data-quality rule registered and listed:** `source_identity_integrity`, table
   `events`, type `Custom Data Quality`.
7. **Data-quality execution succeeded:** **240 total / 240 valid / 0 invalid**.

The executed DQ command was:

```sql
RUN DQ source_identity_integrity TABLE lightning.metastore.signsafe_usl_20261026.renter_records_v1.events
```

## Scope of the data-quality result

The rule checks nonempty original record IDs, the expected dataset IDs, an official
source-URL prefix and correctly formatted BIN/BBL values **when present**. It does
not certify uniqueness, ownership or property matching, event truth, historical legal
applicability, current safety, legal compliance, complete citation semantics or
coverage beyond these 240 rows. Missing OATH BIN/BBL remains explicitly missing.

The semantic model uses `UNION ALL`, not inferred property joins. The deployment is
independent of the application's Investigator; adopting it into the existing query
path requires a separate integration decision and regression check.

## SQL references and SHA-256 hashes

Hashes below cover the exact SQL **template file bytes**, including their newline
formatting, at documentation preparation. Parameter-substituted model, activation,
exploration, verification and rule statements were checked against the successful
commands in the live receipt. Source definitions match the earlier successful source
registration; source registration was **not rerun** during resumed deployment.

- [sources.sql](../../sql/zetaris_usl/sources.sql)
  - SHA-256: `3655b1441883faf39d5d819a947cc4f1f997659350d446fdc43d7dfac246c7ee`
- [explore.sql](../../sql/zetaris_usl/explore.sql)
  - SHA-256: `265475a58fdd3b512b2863ea1030f195792b1c28f74db49f2203597c5f960397`
- [model.sql](../../sql/zetaris_usl/model.sql)
  - SHA-256: `72dc43621852a203da0bba6fc04252aada99b7b338b24531a4623a2b5a3548fe`
- [activate.sql](../../sql/zetaris_usl/activate.sql)
  - SHA-256: `d035171faca6c725c5ecc802d7e540a7d9bc12aad6741d6a7827cbe071f95888`
- [verify.sql](../../sql/zetaris_usl/verify.sql)
  - SHA-256: `5927e53fd647e3b93316d048c22beba5a29facfe3bb260bcdd54c33376325481`
- [dq.sql](../../sql/zetaris_usl/dq.sql)
  - SHA-256: `531f362025a29eac98a87abbb969ed4b134c2c28abdbcda15774f4e61b9189ee`

## Provenance and reproduction

The source of this summary is the existing ignored local
`reports/sponsor_compliance/usl_resume_verification.json`; the earlier source-registration
receipt was used only to check `sources.sql`. Original failure evidence is retained
separately and has not been relabeled as success. No private endpoint URLs, engine or
organization configuration, credentials, respondent data or full records appear here.

See the [deployment appendix](../ZETARIS_USL.md) for SQL parameters and the
[bounded runner](../../scripts/verify_zetaris_usl.py). The USL already exists: do not
rerun setup or `--resume` to recreate it. The appendix documents a future read-only
`--verify` recheck; no live recheck was performed for this documentation-only pass.
