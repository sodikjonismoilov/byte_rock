# SignSafe — GenAI.Works Open Agent Hackathon 2026

**Team:** ByteRock
**Track:** Track 1 — Solving Fragmented Intelligence
**Event:** Oct 22–27, 2026, online, teams 1–5, up to $20K prize pool
**One-liner:** You're about to sign a lease in NYC. Is this building actually okay to live in?
SignSafe reconciles NYC Open Data sources that identify the same building
different ways, and issues a sourced verdict: SIGN / CAUTION / WALK AWAY.

## Why this can win
- Real user, real consequence, explained in 10 seconds.
- The multi-agent loop is the demo: Matcher links records across datasets,
  Critic rejects bad links, Investigator finds patterns (e.g., repeated heat
  complaints that never became a violation), Reporter writes a verdict where
  every claim carries its source (dataset + record ID + date).
- NYC housing data is rich, free, and largely untouched by other teams.

## Sponsor technology — REQUIRED (official Welcome Guide)
Sponsor Tech is 10 pts; "mentioning a sponsor, copying a prompt, or adding
an unused dependency does NOT meet the requirements — the integration must
work in your project."
- **Zetaris (required — must be THE data layer):** serve the NYC Open Data
  sources through Zetaris; the agents query Zetaris, not raw APIs. Runs in
  Docker locally or on AWS.
- **Meterless (required, two parts):**
  (a) **Nightshift = the primary AI provider** for the product's model
  calls (the NVIDIA API key goes in Nightshift's Providers tab, NOT the repo).
  (b) **Implement at least one Meterless Engine in a working feature**,
  with a test showing it works. Our pick: **World Model** (shared state
  between agents) = the evidence board that all four agents read and write.
- **Cursor: OPTIONAL** per the guide ("recommended; you can build with any
  coding tool").
- **NVIDIA:** connect NVIDIA models through Nightshift. Route at least one
  agent (Critic or Reporter) through a **Nemotron** model — best use of
  Nemotron wins an NVIDIA DGX Spark, a separate prize.
- **GitHub repo must be PUBLIC for submission.**

## Judging facts (official rubric)
Impact 30 / Technical 20 / Innovation 15 / Demo 15 / Product & UX 10 /
Sponsor Tech 10. Track 1 cash prizes: 1st $2,000, 2nd $1,350, 3rd $1,000
(split equally among the team unless the team files a different split).
Ties break on Impact, then on SUBMISSION TIMESTAMP — submit early.
Judges explicitly reject linear pipelines (A→B→C with no feedback) and
hardcoded demo paths. Our Critic→Matcher rejection/retry loop + visible
trace logs are the core asset. Required extras: logs/traces of agent
reasoning, sample inputs/outputs (more than one case), SAMPLE_MODE
fallback, repo runs from clean setup, .env.example, no committed secrets,
pre-existing components declared in the submission form.

## Submission deadline
**Tue Oct 27, 23:45 UTC = 7:45 PM ET.** Team target: package Monday night,
submit Tuesday by noon ET. Components: demo video (1–4 min), slide deck,
public GitHub repo + README, sponsor-technology explanation.

## Scope (locked — do not expand)
- Neighborhoods (cache only): ZIP 10017 (Midtown East) + ZIP 11103 (Astoria)
- Datasets (verified live against the Socrata catalog, Oct 22, 2026):
  1. HPD Housing Maintenance Code Violations — `wvxf-dwi5`
     https://data.cityofnewyork.us/resource/wvxf-dwi5.json
  2. 311 Service Requests (2020–present) — `erm2-nwe9`
     https://data.cityofnewyork.us/resource/erm2-nwe9.json
  3. DOB Permit Issuance — `ipu4-2q9a`
     https://data.cityofnewyork.us/resource/ipu4-2q9a.json
  4. Evictions — `6z8x-wfk4`
     https://data.cityofnewyork.us/resource/6z8x-wfk4.json
- Address normalization: NYC Geosearch API (free, no key)
  https://geosearch.planninglabs.nyc/v2/search?text=<address>
- Matching spine: BBL (Borough-Block-Lot). Exact BBL first; Geosearch /
  normalized address is the fallback, and every fallback link is audited by
  the Critic and labeled as such in the report.

## Agents
1. **Matcher** — proposes record→building links (BBL exact, then address),
   each with a confidence score.
2. **Critic** — rejects links that look like address-matching mistakes
   (different BBL, wrong borough, distance, era, duplicate collisions);
   also rejects any finding with no record IDs behind it. Every decision
   is written to the trace with its rule and reason.
3. **Investigator** — runs the Clerk's SQL and writes findings: complaint
   bursts with no violation, repeat violation classes, eviction trend,
   severity mix, permit activity. Each finding carries its record IDs.
4. **Reporter** — verdict + report.json from approved findings only,
   including a "what we could not check" list. "No data found" is reported
   as unknown, NEVER as "safe."
Plus the **Conductor**: runs the loop, max 3 retries, timeouts, clean
errors instead of hangs.

## Schedule (team game plan — see the team doc for the full version)
- **Fri night:** Zetaris answering queries; repo public with .gitignore +
  .env.example; LLM.generate() calling Nightshift once with the model
  logged. **Gate 1 (midnight):** SAMPLE_MODE run works end to end.
- **Sat:** datasets registered, building_events view, 6–8 queries, three
  cold-case files; Matcher + Critic on fake data with a rejection+retry
  in the trace; World Model board + load-twice test. **Gate 2 (9 PM):**
  one real address → real report.
- **Sun:** Investigator + Reporter finished; loops capped; three sample
  inputs with real outputs. **Gate 3 (9 PM):** feature freeze.
- **Mon:** README, demo video (1–4 min, from a real run), slide deck,
  sponsor-tech explanation. **Gate 4 (10 PM):** clean-clone test passes.
- **Tue:** roster confirmed, submission in by noon ET.

## Demo outline (~3 min)
1. Type a real address → verdict card: WALK AWAY, e.g. 14 heat/hot-water
   complaints in 2 winters, 0 resulting violations, 3 open Class C
   violations, 1 eviction filing. Every line sourced.
2. Show the Critic in the trace: record links it rejected and why, and
   the Matcher's retry.
3. Contrast building: CAUTION or SIGN, thin but clean record — and the
   Reporter explicitly saying what the data cannot prove.
