# SignSafe — GenAI.Works Open Agent Hackathon 2026

SignSafe is the product. ByteRock is the team building it
(Alif, Sodikjon, Yawen).

Track: Track 1 — Solving Fragmented Intelligence
Event: Oct 22–27, 2026, online. Teams of 1–5, prize pool up to $20K.

The idea in one line: you're about to sign a lease in NYC — is the building
actually okay to live in? SignSafe pulls together NYC Open Data sources that
all identify the same building in different ways, and gives you a verdict
with sources behind it: SIGN / CAUTION / WALK AWAY.

## Why we think this can win

- There's a real user with real money on the line, and anyone gets the
  pitch in about 10 seconds.
- The agent loop is the demo, not a sideshow. The Matcher links records
  across datasets, the Critic throws out bad links, the Investigator looks
  for patterns (like heat complaints that keep coming in but never turn
  into a violation), and the Reporter writes the verdict — every claim
  carries its source: dataset, record ID, date.
- NYC housing data is rich, free, and most teams won't touch it.

## Sponsor stuff — REQUIRED (from the official Welcome Guide)

Sponsor Tech is worth 10 points and they mean it: just mentioning a sponsor,
copying a prompt, or adding a dependency we never use does NOT count. It has
to actually work in the project.

- Zetaris (required, and it has to be THE data layer): the NYC Open Data
  sources get served through Zetaris, and the agents query Zetaris — not
  the raw APIs. It runs in Docker locally or on AWS.
- Meterless (required, two parts):
  (a) Nightshift is the primary AI provider for the product's model calls.
  The NVIDIA API key goes in Nightshift's Providers tab, NOT in the repo.
  (b) We also have to implement at least one Meterless Engine as a working
  feature, with a test proving it works. Our pick: the World Model — the
  shared evidence board all four agents read from and write to.
- Cursor is OPTIONAL. The guide says it's recommended but we can build
  with whatever tools we want.
- NVIDIA: models get connected through Nightshift. If we route at least
  one agent (Critic or Reporter) through a Nemotron model, we're in the
  running for best use of Nemotron, which wins an NVIDIA DGX Spark.
- The GitHub repo has to be PUBLIC for the submission.

## Judging (official rubric)

Impact 30 / Technical 20 / Innovation 15 / Demo 15 / Product & UX 10 /
Sponsor Tech 10.

Track 1 cash: 1st $2,000, 2nd $1,350, 3rd $1,000, split equally between
the team unless we file a different split. Ties break on Impact first,
then on submission timestamp — so submitting early genuinely matters.

Judges have said they reject straight-line pipelines (A→B→C, no feedback
loop) and hardcoded demos. Our Critic→Matcher rejection/retry loop and the
visible trace logs are the strongest thing we have. Also required:
logs/traces of the agents' reasoning, sample inputs and outputs (more than
one case), a SAMPLE_MODE fallback, a repo that runs from a clean setup,
.env.example, no committed secrets, and any pre-existing components
declared on the submission form.

## Deadline

Tue Oct 27, 23:45 UTC = 7:45 PM ET. Team plan: package everything Monday
night, submit Tuesday by noon ET. The submission is: demo video (1–4 min),
slide deck, public GitHub repo + README, and the sponsor-technology
explanation.

## Scope (locked — don't grow it)

- Neighborhoods, cache only: ZIP 10017 (Midtown East) + ZIP 11103 (Astoria)
- Datasets (checked live against the Socrata catalog on Oct 22, 2026):
  1. HPD Housing Maintenance Code Violations — wvxf-dwi5
     https://data.cityofnewyork.us/resource/wvxf-dwi5.json
  2. 311 Service Requests (2020–present) — erm2-nwe9
     https://data.cityofnewyork.us/resource/erm2-nwe9.json
  3. DOB Permit Issuance — ipu4-2q9a
     https://data.cityofnewyork.us/resource/ipu4-2q9a.json
  4. Evictions — 6z8x-wfk4
     https://data.cityofnewyork.us/resource/6z8x-wfk4.json
- Address cleanup: NYC Geosearch API (free, no key)
  https://geosearch.planninglabs.nyc/v2/search?text=<address>
- Matching spine is the BBL (Borough-Block-Lot). Exact BBL match first.
  Geosearch / normalized address is the fallback, and every fallback link
  gets audited by the Critic and labeled as a fallback in the report.

## The agents

1. Matcher — proposes links between records and buildings (exact BBL
   first, then address), with a confidence score on each one.
2. Critic — rejects links that smell like address-matching mistakes:
   different BBL, wrong borough, too far away, wrong era, duplicate
   collisions. Also rejects any finding that has no record IDs behind it.
   Every decision lands in the trace with the rule and the reason.
3. Investigator — runs the Clerk's SQL and writes findings: complaint
   bursts that never became violations, repeat violation classes,
   eviction trend, severity mix, permit activity. Findings carry their
   record IDs.
4. Reporter — builds the verdict and report.json out of approved findings
   only, including a "what we could not check" section. If there's no
   data, that's reported as unknown. Never dress it up as "safe."

Plus the Conductor, which runs the loop: max 3 retries, timeouts, and
clean errors instead of hangs.

## Schedule (short version — full plan is in the team doc)

- Fri night: Zetaris answering queries; repo public with .gitignore and
  .env.example; LLM.generate() calling Nightshift once, with the model
  logged. Gate 1 (midnight): SAMPLE_MODE runs end to end.
- Sat: datasets registered, building_events view, 6–8 queries, three
  cold-case files; Matcher + Critic running on fake data with a
  rejection+retry visible in the trace; World Model board plus the
  load-twice test. Gate 2 (9 PM): one real address in, one real report out.
- Sun: Investigator + Reporter done; loops capped; three sample inputs
  with real outputs. Gate 3 (9 PM): feature freeze.
- Mon: README, demo video (1–4 min, filmed from a real run), slide deck,
  sponsor-tech write-up. Gate 4 (10 PM): a clean clone of the repo passes.
- Tue: roster confirmed, submission in by noon ET.

## Demo outline (~3 min)

1. Type in a real address, get the verdict card: WALK AWAY — e.g. 14
   heat/hot-water complaints across 2 winters, 0 violations came out of
   them, 3 open Class C violations, 1 eviction filing. Every line sourced.
2. Open the trace and show the Critic at work: links it rejected, why,
   and the Matcher retrying.
3. Contrast building: CAUTION or SIGN — a thin but clean record, with the
   Reporter saying out loud what the data can't prove.
