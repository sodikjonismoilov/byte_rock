# The Critic — build spec (Crypto's agent)

> **Status (see the [root README](README.md)):** rules R1-R10 are implemented in `critic.py` and all 12
> fixtures pass (`python critic.py critic-fixtures.json`). The LLM gray-zone pass described below
> (`llm_review`) is a placeholder and is **not wired in**; the Warden is rules-only. The Matcher and
> Investigator named in this spec are not built as separate agents, and there is no World Model board
> service; records reach the Critic through `integration.py`. This file is the original spec, kept as written.

Two jobs, both are vetoes:
1. **Match veto** — reject/quarantine suspicious record→building links
   from the Matcher before they reach the Investigator.
2. **Evidence veto** — reject any Investigator finding that carries no
   record IDs. No evidence, no finding. Non-negotiable.

## Contract

Input (one candidate link):
```json
{ "record_id": "…", "dataset": "violations|complaints311|permits|evictions",
  "address_raw": "…", "bbl": "1013570031", "bin": "…",
  "lat": 40.76, "lon": -73.99, "building_class": "C1",
  "year_built": 1920, "record_date": "2024-01-15",
  "matcher_confidence": 0.87 }
```
Plus the building card it claims to belong to (same fields, from the
World Model board / Clerk's view).

Output (one decision, ALWAYS written to the trace):
```json
{ "record_id": "…", "decision": "accept|reject|quarantine",
  "rule": "R1…R8 or null", "reason": "one line, human-readable",
  "decided_by": "rule|llm", "model": "nightshift model name or null" }
```

## Decision order — rules first, LLM only for the gray zone

Deterministic rules run first: fast, free, auditable. The LLM (via
LLM.generate() → Nightshift, judge class / Nemotron) is called ONLY on
quarantined items, to promote (→accept) or demote (→reject) with a
written reason. The trace records which path decided — judges love this.

REJECT (hard):
- **R1 BBL mismatch** — record BBL ≠ building BBL.
- **R2 Borough conflict** — BBL/borough code differs.
- **R3 Geo distance** — record coords > 150 m from building coords
  (> 500 m is not even the same neighborhood).
- **R4 Temporal impossibility** — record_date before year_built.
- **R5 Same-dataset collision** — a record from the same dataset already
  pinned to this building under a different record ID for the same event.

QUARANTINE (held out of the verdict; LLM reviews):
- **R6 Address divergence** — normalized addresses differ beyond the
  house number (apt/unit artifacts, "123A vs 123", suffix errors).
- **R7 Class mismatch** — building_class conflicts with the building
  card and no permits record bridges the change.
- **R8 Low confidence, uncorroborated** — matcher_confidence < 0.6 and
  no second dataset confirms the link.

ACCEPT everything else.

## Evidence veto (for Investigator findings)
Finding arrives as {claim, record_ids[], …}. If record_ids is empty →
reject, rule **R9 NO_EVIDENCE**. If any record_id is not on the board →
reject, rule **R10 PHANTOM_SOURCE**.

## Done when
- All 12 fixture cases in critic-fixtures.json pass.
- One trace shows: a match rejected by rule → Matcher retry accepted →
  finding with no evidence vetoed by R9.
- Runs standalone against fixtures with no Zetaris/Nightshift
  (rules path), so it demos even in SAMPLE_MODE.
