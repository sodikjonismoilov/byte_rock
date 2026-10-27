# ByteRock: NYC renter due-diligence agents

**Team ByteRock · Track 1 (Solving Fragmented Intelligence) · Open Agent Hackathon 2026 (Level 2)**

You are about to sign a lease in New York City. Give the system the address and it investigates whether the building is safe to rent. NYC records identify the same building in different ways, so it resolves the building's identity first, then pulls city records through Zetaris, reconciles them, and has a root Critic reject records that don't belong to this building. It writes a renter report in which every claim cites the agency, record ID and date behind it. Missing data is reported as unknown, never as "safe", and the report makes no safety score or liability conclusion. It is built for renters and anyone advising them.

**Deadline:** Tue Oct 27, 2026, 7:45 PM ET.

## Quick start

### a. Docker (recommended: no credentials, no network)

```sh
docker build -t byte-rock .
docker run --rm byte-rock
```

This runs `python run.py input_examples/1.json` with `SAMPLE_MODE=true`. The expected output is a JSON object with `"status": "inconclusive"`, `"data_mode": "recorded_replay"`, `"factual_findings": 1`, and process exit code 2 (see [Exit codes](#exit-codes)). It also works with `docker run --rm --network none byte-rock`.

Run the test suite inside the image (expect `384 passed, 1 skipped`):

```sh
docker run --rm byte-rock python -m pytest -q
```

To keep the generated reports, mount the output folder: `docker run --rm -v "$PWD/outputs:/app/outputs" byte-rock`. H-MEM memory (see below) is created inside the container at run time, so it only carries over between runs if you also mount a volume at `/app/.local`.

### b. Local

Requirements: **Python 3.11+** and **Node.js 22.x**.

Why Node 22 specifically: the vendored H-MEM memory engine is started with `node --experimental-transform-types`, and newer Node versions reject that flag. There is no `npm install` step; the engine is vendored in `agents/legal_agent/vendor/hmem/`.

### c. The demo web page

A browser front end over the same code path as `run.py` (`webapp.py` calls `run.build_argv` and `scripts.investigate_address.run_investigation`; it adds no agent logic). Type an address, watch the seven specialists work on a 3D case board, and get the verdict placard, the cited evidence, what could not be checked, and the full trace.

```sh
SAMPLE_MODE=true python webapp.py        # recorded replay, no credentials, no network
python webapp.py                         # live: needs .env.local (Zetaris) and the Nightshift app open
```

Then open http://127.0.0.1:5050. In Docker: `docker run --rm -p 5050:5050 byte-rock python webapp.py --host 0.0.0.0` (same default `SAMPLE_MODE=true`).

- The page's live feed is the run's own `trace.jsonl`, read while the run is still writing it. Nothing on screen is invented: the specialists' status, the pinned/rejected/held record cards and the verdict rules all come from trace events.
- The specialists are presentation names for the real components, each tagged with what runs it: Surveyor (identity resolution, rules), Archivist (records via Zetaris), Warden (root Critic R1-R10, rules), Pathfinder / Bloodhound / Magistrate (legal Planner / Researcher / Critic, model-backed when a model is configured, otherwise deterministic), Assessor (verdict rules).
- One investigation runs at a time. Live runs take about four minutes.
- No build step and no CDN: `web/board.js` is a committed bundle of [three.js](https://threejs.org) (MIT, see `web/THREE_LICENSE.txt`) plus `web/src/board.src.js`. To rebuild it: `npm i --no-save three esbuild && npx esbuild web/src/board.src.js --bundle --minify --format=esm --outfile=web/board.js`.
- If WebGL is unavailable, the 3D board is skipped and the record chips under it still list every record the Warden examined.

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r agents/legal_agent/requirements.txt
SAMPLE_MODE=true python run.py input_examples/1.json
python -m pytest -q
```

## Input and output

Input is a JSON file (`input_examples/1.json`):

```json
{"address": "1 Mock Street", "borough": "Manhattan", "unit": null}
```

`address` is required. `borough` and `unit` are optional.

Output is one JSON object on stdout:

| Field | Meaning |
|---|---|
| `run_id`, `status`, `exit_code`, `termination_reason` | How the run ended and why |
| `sample_mode`, `data_mode`, `provider` | Where the data came from (`recorded_replay` / `synthetic-fixture` in sample mode) |
| `identity_status` | Whether the building identity was verified |
| `factual_findings` | Number of accepted, cited factual findings |
| `models_used` | Model names that were called (empty when no model is used) |
| `run_dir`, `renter_report`, `trace` | Paths to the artifacts |

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Completed |
| 2 | Inconclusive: an honest, partial factual report (not an error) |
| 1 | Error or bad input |

### Artifacts

Each run writes `outputs/<timestamp>_<run-id>/` containing `renter_report.md`, `investigation_report.md`, `investigation_report.json` (the full audit), `trace.jsonl` (an append-only event trace) and `run_summary.json`. These are gitignored.

### What SAMPLE_MODE is

`SAMPLE_MODE=true` replays a recording (`agents/legal_agent/tests/fixtures/address_replay.synthetic.json`) of **one synthetic address, "1 Mock Street, Manhattan"**. The records are fictional and every run is labelled `data_mode=recorded_replay`. Exit code 2 is the expected result there: the recording has a response for only 5 of the 20 registered sources, so the legal review is inconclusive and the report is factual-only. In the replay run we checked, 15 of the 20 sources are marked unavailable. Other addresses get a stderr warning and come back mostly unavailable. The sample run also exercises H-MEM: its trace (`trace.jsonl`) contains `memory.retrieved` and `memory.stored` events.

## How it works

```
 address JSON
      |
      v
 identity resolution (BBL/BIN/HPD building ID, borough, unit)
      |
      v
 data retrieval through Zetaris (20 registered sources, bounded paging)
      |
      v
 reconciliation (duplicates, stale/conflicting records, lot vs building vs unit scope)
      |
      v
 root Critic, rules R1-R10 (critic.py): reject / quarantine / pass each record
      |  accepted factual findings
      v
 legal research workflow <-+  Planner -> Researcher -> legal Critic
 (agents/legal_agent)      |  bounded revisions (max 2), tool and model budgets
      +--------------------+
      |
      v
 deterministic renter report + audit JSON + trace.jsonl
```

- **Identity first.** The address is matched to a building using identifiers from HPD records. Ambiguous or unverified identity stops the run as inconclusive instead of guessing.
- **Root Critic (`critic.py`).** Hard rejects: R1 BBL mismatch, R2 borough conflict, R3 geo distance, R4 temporal impossibility, R5 same-dataset collision. Quarantine: R6 address divergence, R7 class mismatch, R8 low-confidence uncorroborated. Also R9 finding with no evidence and R10 phantom source (record ID not on the board). It runs standalone: `python critic.py critic-fixtures.json`.
- **Legal workflow.** A Planner, Researcher and legal Critic run in a bounded loop with at most two revisions. If the legal review can't be completed, the factual report is still delivered.
- **Renter report.** It is a deterministic rendering of accepted findings, with no formatting model call. Draft claims stay in the JSON audit.

The code lives in `agents/legal_agent/`. The CLI behind `run.py` is `scripts/investigate_address.py`. See `agents/legal_agent/README.md` for details.

**Planned, not implemented:** `BRIEF.md` describes separate Matcher, Investigator, Reporter and Conductor agents and a World Model evidence board. In the code today, identity resolution plus reconciliation plays the Matcher's role, and the shared-state handoff (`integration.board_update`) is an in-process adapter awaiting the team's orchestrator, not a deployed World Model service.

## Sponsor technology

### Zetaris (data layer)

All city records are read through Zetaris. `scripts/zetaris_api.py` is the HTTP client, and `agents/legal_agent/tools/zetaris.py` and `tools/address_data.py` map Zetaris rows to evidence and run bounded, paginated queries against the source registry (`agents/legal_agent/data/source_registry.json`). Required variables: `ZETARIS_BASE_URL`, a numeric `ZETARIS_ORG_ID`, and either `ZETARIS_API_KEY` or `ZETARIS_USERNAME` + `ZETARIS_PASSWORD` (`ZETARIS_ENGINE_ID` is optional). `agents/legal_agent/docs/DELIVERY_STATUS.md` records live Zetaris runs for two real addresses (840 Second Avenue and 102-15 1 Street) done earlier in development. `SAMPLE_MODE` does not touch Zetaris.

### Meterless: H-MEM engine

The Meterless engine used is **H-MEM**. It is vendored **unmodified** from the upstream Meterless repository (`github.com/Meterless/Meterless`, commit `1742dec`, path `engines/hmem/reference/src`, Apache-2.0). `agents/legal_agent/vendor/hmem/UPSTREAM.json` records the commit, license and per-file SHA-256 hashes. Only the Python/Node bridge (`agents/legal_agent/memory.py`, `scripts/hmem_bridge.mjs`) is ours.

It powers persistent legal-research memory. `run.py` turns it **on by default in both modes** by setting `LEGAL_MEMORY_DIR` to `.local/legal-memory` (gitignored; override with your own `LEGAL_MEMORY_DIR`). The engine runs locally and needs no Meterless HTTP service. Memory is treated as untrusted context and never as evidence. In the sample run the first run logs `memory.retrieved` with count 0 and `memory.stored` with count 1; a second run retrieves count 1, i.e. what the first run stored.

Proof it works: the official conformance runner (13/13 per `PRE_PUSH_AUDIT.md`) and `agents/legal_agent/tests/test_hmem.py`:

```sh
HMEM_IMPL="$PWD/agents/legal_agent/vendor/hmem/src/index.ts" node --experimental-transform-types agents/legal_agent/vendor/hmem/conformance/runner.ts
python -m pytest agents/legal_agent/tests/test_hmem.py -q
```

### Nightshift / NVIDIA

Nightshift (the Meterless runtime) is the model provider. Live runs use `LLM_PROVIDER=meterless` with `--reasoning configured`; `run.py` sets both by default (override the reasoning mode with `RUN_REASONING`). The legacy `--reasoning nightshift` alias (`NIGHTSHIFT_*` variables) and direct NVIDIA (`--reasoning nvidia`) still exist in the CLI but are not the default. A failure never silently falls back to deterministic reasoning. The adapter is `agents/legal_agent/tools/meterless.py`.

**Setup (local, no secrets in the repo):**
- Nightshift runs as a local app (M1-M4 build) at `http://127.0.0.1:8088/v1`. Keep it open while the code runs.
- Add the NVIDIA key inside Nightshift (Setup > Providers). It never goes in this repo.
- Save the runtime token privately with `.venv/bin/python scripts/meterless_runtime.py configure` (hidden prompts; stored under `.local/`, gitignored).
- Check the connection: `.venv/bin/python scripts/meterless_runtime.py detect` and `.venv/bin/python scripts/meterless_runtime.py text --model meterless/auto`.

**Verified live (2026-10-26):**
- `scripts/nightshift_smoke.py` sent one tiny request per alias. All four aliases (`meterless/auto`, `fast`, `cheap`, `deep`) answered with response model **`nvidia/nemotron-3.5-bolt-e4b`**. Receipt: `docs/receipts/nightshift_smoke.json` (about 16:20 UTC). The receipt has no request IDs: the runtime did not send that header.
- The full model-backed pipeline (Planner, Researcher, legal Critic) ran through Nightshift against the recorded synthetic fixture (not Zetaris): 3 model calls, all returned `nvidia/nemotron-3.5-bolt-e4b`, 2 valid observations, 0 rejected. It took about 225 s in total; the model calls took 31 s, 90 s and 103 s. The legal Critic returned **INCONCLUSIVE** (`MISSING_DETAIL`, `UNIT_SCOPE_LIMITATION`) because the synthetic recording lacks unit-scope detail, so **0 legal findings were published**. The model-backed path works, but no completed legal review is claimed. This run's trace is local (`outputs/` is gitignored); only the smoke receipt is committed.

## Live mode configuration

Live mode (real Zetaris data plus a real model) is **not yet verified through `run.py`** (see Status). **The CLI reads `.env.local`, not `.env`.** Exported environment variables take precedence.

Create `.env.local` with only what you need, as placeholders:

```
ZETARIS_BASE_URL=<http://host:port>
ZETARIS_ORG_ID=<numeric org id>
ZETARIS_API_KEY=<key>            # or ZETARIS_USERNAME and ZETARIS_PASSWORD
```

Copy only these lines, not the whole `.env.example`. The example's context limits (`LEGAL_CONTEXT_MAX_BYTES=40000`, `LEGAL_CONTEXT_MAX_TOKENS=16000`) are too small for a model-backed run and would stop it in the Planner stage with "Mandatory identity, uncertainty and provenance context exceeds budget". `run.py` avoids this by applying larger defaults with `setdefault` in live mode (your own environment still wins): `LLM_PROVIDER=meterless`, `LEGAL_CONTEXT_MAX_BYTES=60000`, `LEGAL_CONTEXT_MAX_TOKENS=60000`, `LEGAL_MODEL_MAX_TOKENS=100000`, `INVESTIGATION_TIMEOUT=480` (a model-backed run takes about 225 s, over a third of the repo's 300 s default). If you call `scripts/investigate_address.py` directly, set these yourself.

```sh
python run.py input_examples/1.json   # with SAMPLE_MODE unset; needs Zetaris + Nightshift
```

In Docker, keep secrets out of the image (`.dockerignore` excludes `.env*` except `.env.example`) and pass them at run time. To reach Zetaris or Nightshift running on your host from inside the container, use `host.docker.internal` as the hostname in the URLs. Live mode through the container is untested.

## Limitations

- No completed live legal review is claimed. Legal review is inconclusive in every recorded run, and legal applicability and operative-law versions are unverified.
- A live run through `run.py` against Zetaris has not been verified, and the Nightshift pipeline run used the synthetic fixture, so there are no real (non-synthetic) sample outputs yet.
- A model-backed run is slow (about 225 s; individual model calls up to about 100 s).
- Retrieval is bounded by page caps and exact query filters. A completed query is not proof of complete history, and "no records" is not "safe".
- The root Critic's R5 rule holds records that are identical apart from their own IDs as possible duplicates. `integration.py` gives R5 a content signature, so distinct same-day records are kept; held records stay in the audit.
- HCR rent history and court records (WebCivil, NYSCEF) are manual-only references. Nothing is scraped around restrictions.
- Legacy DOB permits timed out in one live run and were marked unavailable, not reused from an earlier run.
- The report is not a safety certification, liability determination or legal advice.
- The only built-in sample is one synthetic address; there is no second sample input yet.

## Team and roles

| Role | Responsibilities | Branch prefix | Owner |
|---|---|---|---|
| Records Clerk (data and infra) | Zetaris, NYC datasets, Docker | `clerk/` | TODO |
| Squad Captain (agents) | Identity, Critic, legal research, Nightshift LLM calls | `captain/` | TODO |
| Evidence Keeper (state and front door) | H-MEM, run.py, tests | `keeper/` | TODO |

## Rules

- Never commit directly to `main`. Make a branch named `<role>/<what>` (e.g. `keeper/idempotent-ingest`), open a PR, and get one review.
- Never commit API keys. Secrets go in `.env.local`, which is gitignored.
- No hardcoded outputs. Replays of recorded runs must be labelled as replays.

## Status

- [x] Agents working on sample data (SAMPLE_MODE replay; `pytest` 384 passed, 1 skipped)
- [x] Memory engine with passing test (H-MEM, `tests/test_hmem.py` and conformance runner)
- [x] Docker build works (`docker build`, `docker run`, tests pass in the image)
- [x] Nightshift connected: all four aliases answer with `nvidia/nemotron-3.5-bolt-e4b` (`docs/receipts/nightshift_smoke.json`); model-backed pipeline ran on the synthetic fixture (legal review INCONCLUSIVE)
- [x] H-MEM on by default (memory events in the trace)
- [ ] Zetaris running: TODO (live retrieval was done earlier by the team; not re-verified in this repo state, not through `run.py` or Docker)
- [ ] TODO: live run through `run.py` against Zetaris
- [ ] TODO: real (non-synthetic) sample outputs
- [ ] TODO: Zetaris live in the demo
- [ ] Demo video
- [ ] Slide deck
- [ ] Submission
