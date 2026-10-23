# SignSafe — GenAI.Works Open Agent Hackathon 2026

**Track:** Track 1 — Fragmented Intelligence
**Event:** Oct 22–27, 2026, online, teams 1–5, up to $20K prize pool
**One-liner:** You're about to sign a lease in NYC. Is this building actually okay to live in?
SignSafe reconciles four NYC Open Data sources that identify the same building
different ways, and issues a sourced verdict: SIGN / CAUTION / WALK AWAY.

## Why this can win
- Real user, real consequence, explained in 10 seconds.
- The multi-agent loop is the demo: Matcher links records across datasets,
  Critic rejects bad links, Investigator finds patterns (e.g., repeated heat
  complaints that never became a violation), Reporter writes a verdict where
  every claim carries its source (dataset + record + date).
- NYC housing data is rich, free, and almost untouched by other teams.

## Sponsor technology — REQUIRED (official Welcome Guide specifics, Oct 22)
Sponsor Tech is 10 pts; "mentioning a sponsor, copying a prompt, or adding
an unused dependency does NOT meet the requirements — the integration must
work in your project."
- **Zetaris (required — must be THE data layer):** serve the four NYC Open
  Data sources through Zetaris; the Matcher queries Zetaris, not raw APIs.
  Setup: runs locally in Docker from Zetaris Cloud; first download/startup
  takes 30–45 min; needs a 16GB+ RAM machine. START THIS INSTALL FIRST.
- **Meterless (required, two parts):**
  (a) **Nightshift = the primary AI provider** for the product's model
  calls (NVIDIA API key goes in Nightshift's Providers tab, NOT the repo).
  (b) **Implement at least one Meterless Engine in a working feature**,
  with a test showing it works. Engine pick for SignSafe: **World Model**
  (shared state between agents) = the shared Building Dossier that
  Matcher/Critic/Investigator/Reporter all read and write. Optional
  second: Scout Intent to route the address lookup. One engine done well
  beats two half-done.
- **Cursor: OPTIONAL** per this guide ("recommended; you can build with
  any coding tool") — supersedes the earlier PDFs that called it required.
  Use it if the team likes it; don't burn time migrating editors.
- **NVIDIA:** connect NVIDIA models through Nightshift. Route at least
  one agent (Critic or Reporter) through a **Nemotron** model — the best
  use of Nemotron wins an **NVIDIA DGX Spark**, a separate prize.
- **GitHub repo must be PUBLIC for submission** (so byte_rock goes public
  regardless — which also unblocks Max's read access).
- Note: the docs disagree on the cash/in-kind split ($13K/$7K here vs
  $15K/$5K in the overview). Total is $20K either way; Track 1 cash prizes
  per the overview: $2,000 / $1,350 / $1,000.

## Judging facts (official rubric)
Impact 30 / Technical 20 / Innovation 15 / Demo 15 / Product & UX 10 /
Sponsor Tech 10. Track 1 prizes: 1st $2,000, 2nd $1,350, 3rd $1,000
(split equally among the team unless the team files a different split).
Ties break on Impact, then on SUBMISSION TIMESTAMP — submit early.
Judges explicitly reject linear pipelines (A→B→C with no feedback) and
hardcoded demo paths. Our Critic→Matcher re-retrieval loop + visible
trace logs are the core asset. Required extras: logs/traces of agent
reasoning, sample inputs/outputs (more than one case), SAMPLE_MODE
fallback, repo runs from clean setup, .env.example, no committed secrets,
pre-existing components declared in the submission form.

## Submission deadline — CORRECTED
**Tue Oct 27, 23:45 UTC = 7:45 PM ET.** Crypto is in Programming lab
5:30–9:10 PM ET that evening, so either a teammate submits, or the team
submits before 5:30 PM ET. Plan: submission packaged Mon night,
submitted Tue afternoon. Components: demo video (1–4 min), slide deck,
GitHub repo + README, sponsor-technology explanation.

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
1. **Matcher** — proposes record→building links (BBL exact, then address).
2. **Critic** — rejects links that look like address-matching mistakes
   (different BBL, tower vs. walk-up mismatch, wrong borough); keeps a
   visible rejection log (demo gold: show 2 rejected links in the UI).
3. **Investigator** — pattern rules over the linked records: complaint bursts
   with no violation, repeat violation classes, eviction filings trend,
   violation severity mix, permit activity (renovation vs. neglect signal).
4. **Reporter** — verdict card + narrative. Every claim cites its source.
   "No data found" is reported as unknown, NEVER as "safe."

## 6-day plan (built around Crypto's classes/homework)
- **Thu Oct 22 (tonight, ≤30 min):** register on the board, create team,
  pick Track 1. Run the data pull script. Then Calc §3.1 homework.
- **Fri Oct 23:** Calc §3.1 due 11:59 PM — homework first. Then: cache the
  4 datasets for the 2 ZIPs; BBL-join prototype on 5 hand-picked buildings.
- **Sat Oct 24:** Matcher + Critic end-to-end. (FOUND Halloween party 8–10 PM.)
- **Sun Oct 25:** Appendix D Part 1 due 11:59 PM — homework first. Then:
  Investigator patterns + Reporter verdict card.
- **Mon Oct 26:** classes 9 AM–3:20 PM. Gaps: UI polish, pick the hero demo
  building (heat complaints, zero violations) + one clean contrast building.
- **Tue Oct 27:** §3.2 + App D Part 2 due 11:59 PM AND hackathon ends —
  record demo and submit FIRST (afternoon), homework after. Do not invert.

## Demo script (target ~3 min)
1. Type a real address from the cached set → verdict card: WALK AWAY,
   14 heat/hot-water complaints in 2 winters, 0 resulting violations,
   3 open Class C violations, 1 eviction filing. Every line sourced.
2. Show the Critic panel: 2 record links it rejected and why.
3. Contrast building: CAUTION or SIGN, thin but clean record — and the
   Reporter explicitly saying what the data cannot prove.
