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

Run the test suite inside the image (expect `279 passed, 1 skipped`):

```sh
docker run --rm byte-rock python -m pytest -q
```

To keep the generated reports, mount the output folder: `docker run --rm -v "$PWD/outputs:/app/outputs" byte-rock`.

### b. Local

Requirements: **Python 3.11+** and **Node.js 22.x**.

Why Node 22 specifically: the vendored H-MEM memory engine is started with `node --experimental-transform-types`, and newer Node versions reject that flag. There is no `npm install` step; the engine is vendored in `agents/legal_agent/vendor/hmem/`.

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

`SAMPLE_MODE=true` replays a recording (`agents/legal_agent/tests/fixtures/address_replay.synthetic.json`) of **one synthetic address, "1 Mock Street, Manhattan"**. The records are fictional and every run is labelled `data_mode=recorded_replay`. Exit code 2 is the expected result there: the recording has a response for only 5 of the 20 registered sources, so the legal review is inconclusive and the report is factual-only. In the replay run we checked, 15 of the 20 sources are marked unavailable. Other addresses get a stderr warning and come back mostly unavailable.

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

It powers optional persistent legal-research memory (`--memory-dir` or `LEGAL_MEMORY_DIR`). The engine runs locally and needs no Meterless HTTP service. Memory is treated as untrusted context and never as evidence. It is off in the default sample run.

Proof it works: the official conformance runner (13/13 per `PRE_PUSH_AUDIT.md`) and `agents/legal_agent/tests/test_hmem.py`:

```sh
HMEM_IMPL="$PWD/agents/legal_agent/vendor/hmem/src/index.ts" node --experimental-transform-types agents/legal_agent/vendor/hmem/conformance/runner.ts
python -m pytest agents/legal_agent/tests/test_hmem.py -q
```

### Nightshift / NVIDIA

Live runs choose the model provider with `--reasoning` (`run.py` passes `nightshift` by default in live mode, overridable with `RUN_REASONING`). `nightshift` uses `NIGHTSHIFT_BASE_URL`, `NIGHTSHIFT_MODEL` and `NIGHTSHIFT_API_KEY`, which are legacy aliases for the Meterless Runtime adapter in `agents/legal_agent/tools/meterless.py`. `nvidia` calls NVIDIA directly (`NVIDIA_BASE_URL`, `NVIDIA_MODEL`, `NVIDIA_API_KEY`). A failure never silently falls back to deterministic reasoning.

**Honest status:** the Nightshift contract is covered by transport-based tests, but **a live Nightshift call has NOT been demonstrated.** `PRE_PUSH_AUDIT.md` records earlier live NVIDIA requests during development, but the latest model Critic response failed evidence-ID validation, so no completed live legal review is claimed.

`TODO(nightshift): fill in after the live smoke test, with model name and date`

## Live mode configuration

Live mode (real Zetaris data and a real model) needs a configuration file. **The CLI reads `.env.local`, not `.env`.** Exported environment variables take precedence.

```sh
cp .env.example .env.local   # then fill in values; never commit it
python run.py input_examples/1.json   # with SAMPLE_MODE unset
```

Placeholders (see `.env.example` for the full list):

```
ZETARIS_BASE_URL=<http://host:port>
ZETARIS_ORG_ID=<numeric org id>
ZETARIS_API_KEY=<key>            # or ZETARIS_USERNAME / ZETARIS_PASSWORD
NIGHTSHIFT_BASE_URL=<url>
NIGHTSHIFT_MODEL=<model name>
NIGHTSHIFT_API_KEY=<key>
```

In Docker, keep secrets out of the image (`.dockerignore` excludes `.env*` except `.env.example`). Pass them at run time, for example `docker run --rm --env-file .env.local -e SAMPLE_MODE=false byte-rock`. To reach Zetaris or Nightshift running on your host, use `host.docker.internal` as the hostname in the URLs. Live mode is untested through the container.

## Limitations

- No completed live legal review is claimed. Legal review is inconclusive in every recorded run, and legal applicability and operative-law versions are unverified.
- A live Nightshift call has not been demonstrated (see above).
- Retrieval is bounded by page caps and exact query filters. A completed query is not proof of complete history, and "no records" is not "safe".
- The root Critic's R5 rule can hold distinct same-day records from the same dataset as a collision. Source IDs remain in the audit.
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

- [x] Agents working on sample data (SAMPLE_MODE replay, 279 passed, 1 skipped)
- [x] Memory engine with passing test (H-MEM, `tests/test_hmem.py` and conformance runner)
- [x] Docker build works (`docker build`, `docker run`, tests pass in the image)
- [ ] Zetaris running (live retrieval was done earlier by the team; not re-verified in this repo state or through Docker)
- [ ] Nightshift connected (not demonstrated live)
- [ ] Demo video
- [ ] Slide deck
- [ ] Submission
