# SignSafe

**Team ByteRock · Track 1 (Solving Fragmented Intelligence) · GenAI.Works Open Agent Hackathon 2026**

SignSafe takes a New York City address and checks what the city's own records say about the building before you sign a lease. NYC records name the same building in different ways, so SignSafe first resolves the building's identity, then pulls the records through Zetaris, has a rule-based root Critic throw out records that do not belong to this building, and applies fixed rules to what is left. The result is a verdict with the rule that fired and the evidence IDs (agency dataset + record ID) behind it, plus a list of what could not be checked. Three AI roles (Planner, Researcher, legal Critic) run on a Nemotron model through Meterless Nightshift to look for legal context. **They are advisory: they cannot change the verdict, and in every saved run they stopped at INCONCLUSIVE and published nothing.**

**Scope:** it reports what agency records say, not what a building is like. It does not certify a building as safe, give legal advice, or establish liability. Missing or unchecked data is reported as unchecked, never as good news.

## Quick start for judges

### a. Docker, offline replay (no credentials, no network)

```sh
docker build -t byte-rock .
docker run --rm byte-rock                       # SAMPLE_MODE=true by default
docker run --rm --network none byte-rock        # same, with the network disabled
```

This runs `python run.py input_examples/1.json` against a recorded capture of one fictional address, "1 Mock Street, Manhattan". Expected: a JSON object with `"data_mode": "recorded_replay"`, `"status": "inconclusive"`, `"verdict": "NOT ENOUGH DATA"`, `"factual_findings": 1`, `"models_used": []`, and process exit code 2 (an honest partial result, not an error). The same command run locally (below) gave exactly this output. The image itself was not rebuilt while writing this README; `Dockerfile` pins Node 22 and Python 3.11.

Web page (same code path, replay mode): `docker run --rm -p 5050:5050 byte-rock python webapp.py --host 0.0.0.0`, then open http://127.0.0.1:5050.

Local equivalent without Docker (Python 3.11+, **Node.js 22**):

```sh
python3 -m venv .venv && source .venv/bin/activate
pip install -r agents/legal_agent/requirements.txt
SAMPLE_MODE=true python run.py input_examples/1.json     # exit code 2 is expected
SAMPLE_MODE=true python webapp.py                        # http://127.0.0.1:5050
```

Node 22 matters: the vendored H-MEM memory engine starts with `node --experimental-transform-types`, which newer Node versions reject. With a newer Node the run still completes, but the trace shows `memory.failed` events and no memory is used (observed with Node 26 while checking this README).

### b. Live local run (Zetaris + Nightshift)

Prerequisites:

1. Python 3.11+ and Node.js 22 (see above).
2. A Zetaris instance. Put these in `.env.local` (the CLI reads `.env.local`, not `.env`; never commit it): `ZETARIS_BASE_URL`, a numeric `ZETARIS_ORG_ID`, and either `ZETARIS_API_KEY` or `ZETARIS_USERNAME` + `ZETARIS_PASSWORD` (`ZETARIS_ENGINE_ID` is optional).
3. The Meterless Nightshift app running locally (default `http://127.0.0.1:8088/v1`), with the NVIDIA key added inside Nightshift (Providers). The key never goes in this repo. Save the runtime token privately with `python scripts/meterless_runtime.py configure` (hidden prompt, stored under `.local/`, gitignored), then check with `python scripts/meterless_runtime.py detect`.

Run:

```sh
echo '{"address": "686 3 Avenue", "borough": "Manhattan"}' > /tmp/case.json
python run.py /tmp/case.json          # SAMPLE_MODE unset: live Zetaris + model-backed legal review
python webapp.py                      # web page; choose "Live city data"
```

In live mode `run.py` applies larger defaults than `.env.example` (see [Configuration](#configuration)); your own environment variables win. A model-backed run takes about 3 to 7 minutes (the two saved runs took 220 s and 429 s). Live mode through Docker has not been tested.

## What you get

**Four verdict states**, computed by `agents/legal_agent/verdict.py` (a pure function: no model, no network):

| Verdict | When |
|---|---|
| **NOT ENOUGH DATA** | The building's identity is not verified, **or** no rule fired and either `hpd_violations` / `hpd_complaints` were not fully checked or fewer than 50% of the machine-readable sources were checked. |
| **WALK AWAY** | W1: 3 or more open Class C HPD violations. W2: the building is in the HPD Alternative Enforcement Program (discharged records are not counted). |
| **CAUTION** | C1: at least 1 open Class C violation. C2: 5 or more open Class B violations dated in the last 12 months. C3: 5 or more HPD complaints in the last 12 months and no HPD violations in that window. C4: any HPD litigation or executed eviction record in the last 2 years. |
| **NO FLAGS FOUND** | No rule fired and coverage is sufficient. This means no flag was found in the records checked. It is not a statement that the building is safe. |

Details that matter:

- Windows are measured back from the investigation date.
- **Apartment-level violations**: when no unit is requested, HPD violations for individual apartments that the root Critic holds (R8, unit mismatch) are still counted by the verdict, labelled separately ("N for the building, M for individual apartments"). The hold stays in the audit. A record whose identifiers conflict with the building's is never counted. Records for a specific unit are only counted when that unit was requested.
- **Partial coverage**: rules can still fire on partial data, and the gaps are listed in the verdict basis (`data_gaps`, `sources_unavailable`, `partial_sources`). If a source was truncated by page caps, counts are shown as "at least N". "Nothing found" always needs the required sources.
- **What a fired rule shows**: `rule_id`, `level`, a plain-language `summary`, the `evidence_ids` it counted (format `dataset:record-id`, for example `wvxf-dwi5:2319319`), and the `source_urls`. The report also lists sub-threshold facts under "also on record" so a calm verdict never hides them.

Each run writes `outputs/<timestamp>_<run-id>/` with `renter_report.md`, `investigation_report.md`, `investigation_report.json` (full audit), `trace.jsonl` (append-only event trace) and `run_summary.json`. All are gitignored.

Input is `{"address": "...", "borough": "...", "unit": "..."}` (`address` required). `run.py` prints one JSON object (`run_id`, `status`, `exit_code`, `termination_reason`, `data_mode`, `provider`, `identity_status`, `factual_findings`, `verdict`, `verdict_rules`, `models_used`, paths). Exit codes: 0 completed, 2 inconclusive (partial factual report), 1 error or bad input.

## Agent workflow

The web page shows seven named specialists. They are presentation names for real components:

| Presentation name | Real component | Runs on |
|---|---|---|
| Surveyor | Identity resolution (BBL / BIN / HPD building ID, borough, unit): `agents/legal_agent/identity.py`, `address_investigation.py` | Rules |
| Archivist | Record retrieval through Zetaris: `tools/address_data.py` | Zetaris (deterministic code) |
| Warden | Root Critic rules R1-R10: `critic.py`, bridged by `integration.py` | Rules |
| Pathfinder | Planner (`ResearchPlan`): `agents/legal_agent/agents/` | **Model-backed** |
| Bloodhound | Researcher (`ResearchDraft`) | **Model-backed** |
| Magistrate | Legal Critic (`CriticReport`), followed by a deterministic gate that merges with it | **Model-backed** (plus rules) |
| Assessor | Verdict rules W1, W2, C1-C4: `verdict.py` | Rules |

The Warden's rules: hard rejects R1 BBL mismatch, R2 borough conflict, R3 geo distance, R4 temporal impossibility, R5 same-dataset collision; quarantines R6 address divergence, R7 class mismatch, R8 low-confidence uncorroborated; R9 finding with no evidence, R10 phantom source. `python critic.py critic-fixtures.json` runs its 12 fixtures standalone (12/12 pass). Its model "gray zone" pass (`llm_review` in `critic.py`) is a placeholder and is not wired in.

The three model roles run in a bounded loop (at most 2 revisions). If the legal review cannot be completed, the factual report and the rule-based verdict are still delivered. In offline replay (`--reasoning deterministic`) the three roles are scripted stand-ins and no model runs.

## How it works

```
address JSON
  -> Surveyor: identity (HPD buildings record -> BBL/BIN/building ID)      [rules]
  -> Archivist: records via Zetaris (20 registered sources)                 [Zetaris]
  -> reconciliation (duplicates, stale/conflicting records, lot/building/unit scope)
  -> Warden: root Critic R1-R10, accept / quarantine / reject each record   [rules]
  -> Pathfinder -> Bloodhound -> Magistrate (<= 2 revisions)                [model]
  -> Assessor: verdict from accepted records only                           [rules]
  -> renter report + audit JSON + trace.jsonl
```

**Zetaris data layer.** `tools/address_data.py` creates one temporary Zetaris Lightning database per run (`signsafe_run_<16 hex>`), registers each bounded, filtered request to an official NYC Open Data endpoint as a Lightning REST table, and reads it back with SQL. Paging and table counts are capped. The temporary database is removed at the end of the run (`zetaris.cleanup` in the trace). The provider allows at most 3 active `signsafe_run_*` databases; the code refuses to start a fourth. The source registry (`agents/legal_agent/data/source_registry.json`) lists **20 sources: 17 machine-readable and 3 manual-only** (`hcr_rent_regulation`, `webcivil_local`, `webcivil_supreme`). Manual-only sources are listed as not checked; nothing is scraped around access restrictions.

**Meterless Nightshift + Nemotron model layer.** `tools/meterless.py` talks to the local Nightshift runtime (default `http://127.0.0.1:8088/v1`) using the aliases `meterless/auto` (default), `fast`, `cheap` and `deep`. All four returned `nvidia/nemotron-3.5-bolt-e4b` in the saved smoke test, and every model call in the saved runs reports that model as `returned_model`. Structured output is requested in JSON mode and validated against Pydantic schemas (`tools/llm.py`); an invalid output gets one repair retry. Failures never fall back silently to deterministic reasoning.

**H-MEM memory.** `agents/legal_agent/memory.py` and `scripts/hmem_bridge.mjs` run the vendored Meterless H-MEM engine locally (no Meterless HTTP service needed). Before the model roles run, up to 3 recalled hints can be added to their context, always flagged `trusted_as_evidence: false`. After a run, only validated findings, or review feedback on an inconclusive run, can be stored. Memory is never evidence and never changes a Critic decision. `run.py` enables it by default (`LEGAL_MEMORY_DIR=.local/legal-memory`, gitignored). Observed in replay mode: the first run logs `memory.retrieved` count 0 and `memory.stored` count 1; a second run retrieves count 1.

**Compact model context.** The full evidence stays server-side. `agents/legal_agent/context.py` builds a bounded view for the model: at most 30 records shown, conflicts grouped without losing the underlying IDs, a manifest of omitted IDs, and a hard size guard (`LEGAL_CONTEXT_MAX_BYTES`, `LEGAL_CONTEXT_MAX_TOKENS`). Model-written observations may only cite evidence IDs from the retrieved set; observations that cite anything else are rejected individually (`research.observation_rejected` in the trace; see `agents/legal_agent/docs/OBSERVATION_ISOLATION.md`).

**Page and CLI modes.**

| Mode | Data | Reasoning | Notes |
|---|---|---|---|
| Live (`python run.py`, web "Live city data") | Zetaris | Model-backed (`--reasoning configured`) | Any NYC borough. 3-7 min |
| Offline replay (`SAMPLE_MODE=true`, web "Offline replay") | Recorded capture of "1 Mock Street" | Deterministic stand-ins, no model | Other addresses come back mostly unavailable |

The web path (`run.py`, `webapp.py`) accepts any NYC borough. The ZIP 10017 / 11103 restriction applies only to the older `investigate_property` path (`scripts/investigate_hpd.py`), which the web app does not call.

## Sponsor technology

| Sponsor | What it does here | Where |
|---|---|---|
| **Zetaris** | The data layer. Every city record the product uses is read through a temporary per-run Zetaris database, not by calling the NYC API directly. (A separately labelled development fallback, `--provider nyc-development-fallback`, exists in the CLI and is not used by `run.py` or the web page.) | `agents/legal_agent/tools/address_data.py`, `tools/zetaris.py`, `scripts/zetaris_api.py`, `scripts/zetaris_sql.py` |
| **Meterless** | (a) Nightshift is the model provider for the three model roles. (b) The H-MEM engine is used for legal-research memory, with a test and the official conformance suite. | `tools/meterless.py`, `tools/llm.py`, `scripts/meterless_runtime.py`, `scripts/nightshift_smoke.py`; `memory.py`, `scripts/hmem_bridge.mjs`, `vendor/hmem/` |
| **NVIDIA** | The model behind Nightshift is `nvidia/nemotron-3.5-bolt-e4b`, used by Pathfinder, Bloodhound and Magistrate. A direct-NVIDIA adapter (`--reasoning nvidia`) also exists but is not the default and was not part of the saved runs. | `tools/llm.py`; receipts below |

No separate `SPONSOR_TECH.md` exists in this repo; this section is the sponsor-technology explanation. The Meterless World Model engine is **not** used (see [Future enhancements](#limitations)).

## Evidence

Receipts are in [`docs/receipts/`](docs/receipts/). Numbers below come only from the saved `run_summary.json` and `trace.jsonl` files there (absolute local paths were replaced by `outputs/...` in the copied `run_summary.json`).

| | Run `26b939f3-...-91956988ab81` | Run `87722527-...-561b5180053d` |
|---|---|---|
| Address | 686 3 AVENUE, Manhattan (identity verified, HPD building ID 2342) | same |
| Data / reasoning | `provider=zetaris`, `data_mode=live`, `llm:meterless` | same |
| Total time | 428.8 s | 220.3 s |
| Tool calls / model calls | 45 / 6 (one revision) | 44 / 3 |
| Model returned | `nvidia/nemotron-3.5-bolt-e4b` for all 6 calls | same, all 3 calls |
| Sources | 17 machine-readable checked (12 retrieved, 5 no records), 3 manual-only | same |
| Root Critic | 150 accepted, 83 quarantined, 10 rejected | same |
| Verdict (rules) | **WALK AWAY**: W1, C1, each citing 15 open Class C HPD violation IDs | same |
| Legal Critic | **INCONCLUSIVE** (model review, deterministic gate, merged) | **INCONCLUSIVE** |
| Published legal findings | **0** | **0** |
| Zetaris cleanup | `removed` | `removed` |
| Exit | 2 (`legal_inconclusive`) | 2 |

How to read this honestly:

- The verdict came from the Assessor's fixed rules on accepted agency records. The model roles did not produce or change it.
- The legal Critic returned INCONCLUSIVE in both runs. Its reasons include that a "NOV SENT OUT" status is not an adjudicated status and needs external verification (HPDONLINE), and that building-level records do not establish unit-specific rent history. So no legal finding was published.
- 686 3 AVENUE is the only address that has been run model-backed end to end (all saved runs with completed model calls are for it). These two are the complete ones with a full receipt.
- "Open" is the agency's recorded status. The receipts do not carry record dates; the full report lists them. Read the verdict as "what is on file", not as current conditions.
- The Nightshift smoke test (`docs/receipts/nightshift_smoke.json`, 2026-10-26) sent one tiny request per alias; all four returned `nvidia/nemotron-3.5-bolt-e4b`. It has no request IDs because the runtime did not send that header.
- `trace.jsonl` is matched by the repo's `*.jsonl` ignore rule. If you commit the receipts, add them with `git add -f`.

## Tests

```sh
export PATH="/opt/homebrew/opt/node@22/bin:$PATH"     # or any Node 22 on PATH; H-MEM tests need it
python -m pytest -q
```

Results from this audit, on Node 22.23: **418 passed, 1 skipped** in the working tree (the skip is the opt-in live-model test, `RUN_LIVE_MODEL_TESTS=1`). From a clean export of tracked files (also what the Docker image contains, since `outputs/` is excluded) the same suite gives **410 passed, 9 skipped**: 8 extra skips are tests in `test_compact_context.py` that replay saved local runs and skip when `outputs/` is absent.

Also: root Critic fixtures `python critic.py critic-fixtures.json` (12/12), and the vendored H-MEM conformance runner (13/13):

```sh
HMEM_IMPL="$PWD/agents/legal_agent/vendor/hmem/src/index.ts" node --experimental-transform-types agents/legal_agent/vendor/hmem/conformance/runner.ts
```

## Configuration

Real defaults read from the code. `run.py` sets the "live mode" values with `setdefault` only when `SAMPLE_MODE` is not true, so your own environment always wins.

| Variable | Code default | `run.py` live default | Meaning |
|---|---|---|---|
| `SAMPLE_MODE` | unset (off) | n/a (Docker image sets `true`) | `true`/`1`/`yes` replays the recording, no network |
| `RUN_REASONING` | n/a | `configured` | `--reasoning` mode for live runs |
| `RUN_OUTPUT` | `./outputs` | n/a | Output root |
| `LLM_PROVIDER` | empty | `meterless` | Model provider |
| `LEGAL_CONTEXT_MAX_BYTES` | 40000 | 60000 | Model context size guard (bytes) |
| `LEGAL_CONTEXT_MAX_TOKENS` | 16000 | 60000 | Model context size guard (tokens) |
| `LEGAL_MODEL_PAYLOAD_MAX_BYTES` | 64000 | not set | Cap on a single request payload |
| `LEGAL_MODEL_MAX_TOKENS` | 32000 | 100000 | Model request token ceiling |
| `INVESTIGATION_TIMEOUT` | 300 (seconds) | 480 | Aggregate run deadline |
| `LEGAL_MEMORY_DIR` | unset | `.local/legal-memory` (both modes) | H-MEM directory |
| `ZETARIS_BASE_URL`, `ZETARIS_ORG_ID`, `ZETARIS_API_KEY` or `ZETARIS_USERNAME` + `ZETARIS_PASSWORD`, `ZETARIS_ENGINE_ID` (optional) | n/a | n/a | Zetaris connection (`.env.local`) |
| `METERLESS_BASE_URL`, `METERLESS_MODEL`, `METERLESS_RUNTIME_TOKEN`, `METERLESS_STATE_DIR` | `http://127.0.0.1:8088/v1`, `meterless/auto` | n/a | Nightshift connection; token can also be saved via `scripts/meterless_runtime.py configure` |
| `WEB_HOST`, `WEB_PORT`, `WEB_OUTPUT` | `127.0.0.1`, `5050`, `outputs/web` | n/a | Web page |

The defaults in `.env.example` (`LEGAL_CONTEXT_MAX_BYTES=40000`, `LEGAL_CONTEXT_MAX_TOKENS=16000`) are too small for a full model-backed run: it stops in the Planner with "Mandatory identity, uncertainty and provenance context exceeds budget". `run.py` avoids this. If you call `scripts/investigate_address.py` directly, set the larger values yourself.

## Limitations

- **Identity only resolves for buildings in HPD's jurisdiction dataset** ("Buildings Subject to HPD Jurisdiction"). Addresses outside it, such as non-residential, small 1-2 family, unregistered or new-construction buildings, come back NOT ENOUGH DATA.
- **Address matching can use a number range as an alias.** A typed house number can match a building's range (in a saved run, "350 5TH AVENUE" resolved to the building at "338 5 AVE", whose range ends at 350). The report shows the resolved address, so check it.
- **3 of 20 sources are manual-only** (HCR rent history, WebCivil local and Supreme/NYSCEF). They are listed as not checked.
- **Partial coverage is listed in the verdict basis.** Retrieval is bounded by page caps and exact filters; a completed query is not proof of complete history, and "no records" is not "no problems".
- **Zetaris allows at most 3 active `signsafe_run_*` databases**; cleanup runs after each run, and only one web investigation runs at a time.
- **Model-backed runs take about 3 to 7 minutes.** (The web page's "Live city data · 1-3 min" button label predates the model-backed path and underestimates this.)
- **No completed legal review is claimed.** In both saved live runs the legal Critic returned INCONCLUSIVE and published 0 legal findings; the verdict came from rules. Only 686 3 AVENUE has been run model-backed end to end.
- Offline replay knows one fictional address. Other addresses come back mostly unavailable.
- The report is not a safety certification, liability determination or legal advice.

### Future enhancements

These were planned in `BRIEF.md` and are **not built**: separate Matcher, Investigator, Reporter and Conductor agents, and a Meterless World Model service as the shared evidence board. Today, identity resolution plus reconciliation covers the Matcher's job, and the in-process handoff `integration.board_update` is an adapter, not a deployed service. Other next steps: a wired model pass for the root Critic's gray zone, a second recorded sample address, and verified legal-source retrieval so the legal Critic can conclude.

## Repo layout

```
run.py, webapp.py            front door (CLI) and demo web page
critic.py, critic-fixtures.json, critic-spec.md    root Critic R1-R10 and its fixtures
input_examples/              sample input (1 Mock Street)
agents/legal_agent/          identity, reconciliation, legal workflow, verdict, tools, tests
  tools/                     Zetaris provider, Meterless/LLM adapters, source registry
  data/source_registry.json  the 20 registered sources
  vendor/hmem/               vendored H-MEM engine (unmodified)
  docs/                      development logs (historical; see banner in each)
scripts/                     investigate_address.py (CLI core), Zetaris and Nightshift helpers
web/                         demo page (three.js bundle committed, no build step needed)
docs/receipts/               saved run evidence
Dockerfile, .dockerignore    offline-replay image
```

Docs map: [`agents/legal_agent/README.md`](agents/legal_agent/README.md) (specialist API and CLI), [`agents/legal_agent/docs/`](agents/legal_agent/docs/) (development logs), [`BRIEF.md`](BRIEF.md) (the original plan).

## Pre-existing components and attribution

- **H-MEM engine, vendored and unmodified.** `agents/legal_agent/vendor/hmem/` is the TypeScript reference engine from the Meterless repository (`github.com/Meterless/Meterless`, commit `1742dec56a66e58eef9dda2d2b865823758ca8cd`, path `engines/hmem/reference/src`), Apache-2.0, with its `LICENSE` kept. `UPSTREAM.json` records the commit and SHA-256 hashes; all 10 source files match their recorded hashes (checked during this audit), and the official conformance runner passes 13/13. What is ours: the Python bridge `agents/legal_agent/memory.py` and `scripts/hmem_bridge.mjs`, and the decision of what to store and recall. The conformance runner's `npm install` step is not needed for the commands above. Other H-MEM services in the engine (dreaming, sleep, conflict resolution) are present but not run automatically by the app.
- **Meterless Nightshift provider contract.** `tools/meterless.py` implements the Meterless Runtime v4 provider contract as documented by Meterless; the code is ours.
- **three.js** (MIT, `web/THREE_LICENSE.txt`): the classes used by the 3D case board are bundled into `web/board.js` from `web/src/board.src.js`.
- **Python dependencies:** Flask, Pydantic, python-dotenv, pytest (`agents/legal_agent/requirements.txt`).
- **Data, not code:** NYC Open Data / agency datasets listed in the source registry, and public-page excerpts in `agents/legal_agent/data/legal_authority_snapshots.json` (source URLs are recorded per entry).
- **Services:** Zetaris, Meterless Nightshift and the NVIDIA-hosted Nemotron model are used as external services. No code from them is copied other than the H-MEM engine above.
- Not used: the Meterless World Model engine and any other Meterless engine.

## Team and demo

- Team ByteRock: Sodikjon Ismoilov, Alif Cryptovan Sinaga, Yawen Liu
- Repository: https://github.com/sodikjonismoilov/byte_rock.git
- Demo video: [demo video link]
