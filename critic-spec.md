# The Critic — build spec (Crypto's agent)

The Critic has two jobs, and both of them are vetoes:

1. Match veto — reject or quarantine record→building links from the
   Matcher that look wrong, before they ever reach the Investigator.
2. Evidence veto — reject any Investigator finding that carries no
   record IDs. No evidence, no finding. This one is not negotiable.

## Contract

What comes in (one candidate link):

```json
{ "record_id": "…", "dataset": "violations|complaints311|permits|evictions",
  "address_raw": "…", "bbl": "1013570031", "bin": "…",
  "lat": 40.76, "lon": -73.99, "building_class": "C1",
  "year_built": 1920, "record_date": "2024-01-15",
  "matcher_confidence": 0.87 }
```

It also gets the building card the link claims to belong to — same
fields, pulled from the World Model board / Clerk's view.

What goes out (one decision, and it ALWAYS gets written to the trace):

```json
{ "record_id": "…", "decision": "accept|reject|quarantine",
  "rule": "R1…R8 or null", "reason": "one line, human-readable",
  "decided_by": "rule|llm", "model": "nightshift model name or null" }
```

## How a decision gets made — rules first, LLM only for the gray zone

The deterministic rules run first: they're fast, free, and anyone can
audit them. The LLM (through LLM.generate() → Nightshift, judge class /
Nemotron) only gets called on quarantined items, to either promote them
(→ accept) or demote them (→ reject), with a written reason. The trace
records which path made the call — the judges like seeing that split.

REJECT — hard no:

- R1, BBL mismatch: the record's BBL is not the building's BBL.
- R2, borough conflict: the BBL / borough code doesn't match.
- R3, geo distance: the record's coordinates are more than 150 m from
  the building's. (Over 500 m and it's not even the same neighborhood.)
- R4, temporal impossibility: record_date is before year_built. A
  building can't have a violation before it exists.
- R5, same-dataset collision: a record from the same dataset is already
  pinned to this building under a different record ID for the same event.

QUARANTINE — held out of the verdict, the LLM takes a look:

- R6, address divergence: the normalized addresses differ by more than
  the house number — apt/unit artifacts, "123A vs 123", suffix errors.
- R7, class mismatch: building_class disagrees with the building card
  and there's no permits record that explains the change.
- R8, low confidence and uncorroborated: matcher_confidence under 0.6
  and no second dataset backs the link up.

Everything else gets accepted.

## Evidence veto (for Investigator findings)

A finding shows up as {claim, record_ids[], …}. Two ways it dies:

- record_ids is empty → reject, rule R9 NO_EVIDENCE.
- Any record_id on it isn't actually on the board → reject, rule
  R10 PHANTOM_SOURCE.

## Done when

- All 12 fixture cases in critic-fixtures.json pass.
- One trace shows the whole story: a match rejected by rule, the Matcher
  retries and gets accepted, then a finding with no evidence gets vetoed
  by R9.
- It runs standalone against the fixtures with no Zetaris and no
  Nightshift (rules path only), so it still demos in SAMPLE_MODE.
