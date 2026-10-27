> **Update:** integration.py now gives R5 a content signature, so distinct same-day records are no longer collapsed. critic.py is untouched; the owner's change described in this document is still the cleaner long-term fix.

# Root Critic owner handoff — no teammate code modified

Owner named in `critic-spec.md`: Crypto / Alif Cryptovan Sinaga. This document
records proposed changes for owner review; it is not approval or an implemented
rule change. No external message was sent on the owner's behalf.

## R5: same day is not a duplicate key

`critic.py:review_link` currently rejects a second record from the same dataset
with the same date and normalized address, regardless of distinct source record
IDs, different descriptions, separate conditions or agency event keys. The live
840 Second Avenue run illustrates the impact: multiple original records are held
under R5. They remain in the audit and cannot support published findings; this
integration never promotes them around the root gate.

Proposed owner tests before changing the rule:

1. Two HPD violation IDs on the same inspection date, including different notices
   or conditions: both should remain attributable unless a shared authoritative
   duplicate key establishes duplication. A shared NOV alone can still contain
   different violations.
2. Two DOB permits for the same date/address but different permit/work identifiers:
   retain both; count them as distinct agency records, not necessarily independent
   confirmation of a physical condition.
3. A repeated copy of the same original dataset/record ID: idempotent ingestion;
   do not count it twice or treat it as independent corroboration.
4. The same numeric ID in different datasets: use dataset-qualified IDs and do not
   conflate independent source namespaces.
5. An agency-provided duplicate flag or verified common origin event key: preserve
   the duplicate group and agency semantics rather than infer it from date alone.

`test_distinct_same_day_violations_remain_audited_and_r5_not_bypassed` documents
current behavior. `test_original_sample_record_ids_are_present_in_citywide_retrieval`
checks that expanding beyond the ZIP snapshot does not silently lose the original
records. The desired acceptance behavior above requires the root owner's change.

## R6 and identifier-only records

Some DOB ECB records carry BIN but no property address. Their respondent mailing
address is NOT the violation location. They are therefore held by the existing
address rule even when the query and local identifier check agree. No target
address was fabricated to force acceptance. The owner may consider a separately
tested strong-identifier path; this implementation leaves the veto intact.

## Routing and team boundaries

- R1/R2 attribution conflicts can trigger at most two source correction queries
  in total, using cross-identifier filters. Unchanged rows stop; new source IDs
  receive a fresh Matcher proposal and root review. Existing held rows are not
  silently replaced.
- R5 and unresolved scope remain held pending owner/data review, not automatic
  retries designed to manufacture success.
- Unsupported legal interpretation uses the specialist's existing bounded
  Researcher revision loop. Unknown legal versions remain unresolved.
- Keeper receives original evidence, factual findings, source coverage, Critic
  decisions and follow-up requests through the board projection. Reporter owns
  product verdict policy; no rental-safety certification is produced here.
