# NYC Legal Research Agent

An address-based specialist for the team's NYC rental investigation. Accepted city
records support factual observations; retrieved official authorities support legal
research. Legal review can be INCONCLUSIVE while a useful factual report succeeds.
No safety score or historical liability conclusion is inferred from incomplete data.

## Clean-checkout setup

Run all commands below from the repository root. Use Python 3.11+ and Node.js 22.18+
(or a newer supported release with `--experimental-transform-types`) for the
vendored official H-MEM engine. There is no npm install step for that engine.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r agents/legal_agent/requirements.txt
.venv/bin/python -m pytest -q
```

Offline example, **fictional records**, no credentials or network required:

```sh
.venv/bin/python scripts/investigate_address.py '1 Mock Street' --borough Manhattan --provider replay --replay agents/legal_agent/tests/fixtures/address_replay.synthetic.json --reasoning deterministic --output reports/offline_demo
```

Exit code 2 means an INCONCLUSIVE legal assessment. The generated factual-only
report is still a useful result. The fixture is not evidence about a real address.
For a real-record offline replay, replace the fixture path and address with your own
locally saved `investigation_report.json` and its matching address.

## Local configuration and live command

Copy `.env.example` to **`.env.local`** and fill only the provider settings you use.
The CLI reads `.env.local` (not `.env`); exported variables take precedence. Never
commit either local file, a connect link or a token.

- Zetaris: `ZETARIS_BASE_URL`, numeric `ZETARIS_ORG_ID`, and either `ZETARIS_API_KEY`
  or `ZETARIS_USERNAME` / `ZETARIS_PASSWORD`. `ZETARIS_ENGINE_ID` is optional; no
  engine or table is invented if configuration/data are unavailable. The configured
  gateway must expose the registered official datasets in `data/source_registry.json`.
- Direct NVIDIA: `NVIDIA_BASE_URL`, `NVIDIA_MODEL`, `NVIDIA_API_KEY`. Choose an actual
  model available to your account. CLI `--reasoning nvidia` selects it explicitly;
  failures never silently switch to deterministic reasoning.
- Meterless Runtime: `METERLESS_BASE_URL`, `METERLESS_MODEL`, and
  `METERLESS_RUNTIME_TOKEN`, or `METERLESS_STATE_DIR` containing `proxy-token`.
  Provider ID is `meterless`; discovered `meterless/*` routing IDs are retained.
  Use `LLM_PROVIDER=meterless` with `--reasoning configured`.
- Nightshift compatibility: `NIGHTSHIFT_BASE_URL`, `NIGHTSHIFT_MODEL`,
  `NIGHTSHIFT_API_KEY` are the legacy Meterless Runtime adapter aliases selected by
  `--reasoning nightshift`. This contract is tested; a live Nightshift endpoint
  has **not** been demonstrated.
- Persistent H-MEM: use `--memory-dir .local/legal-memory` or `LEGAL_MEMORY_DIR`.
  This invokes the vendored official engine locally; no running Meterless HTTP
  service is needed for H-MEM. Memory remains untrusted context, never evidence.

Exact live address command (requires configured gateway and NVIDIA):

```sh
LEGAL_CONTEXT_MAX_BYTES=60000 LEGAL_CONTEXT_MAX_TOKENS=60000 LEGAL_MODEL_MAX_TOKENS=100000 .venv/bin/python scripts/investigate_address.py '840 Second Avenue, Manhattan, NY' --borough Manhattan --reasoning nvidia --memory-dir .local/legal-memory --page-size 5 --max-pages 1 --model-timeout 60 --output reports/investigations
```

The pagination bounds make coverage partial. Credentials are not required to render
an already saved report. Optional Runtime setup uses hidden token/link prompts:

```sh
.venv/bin/python scripts/meterless_runtime.py configure
.venv/bin/python scripts/meterless_runtime.py detect
.venv/bin/python scripts/meterless_runtime.py status
.venv/bin/python scripts/meterless_runtime.py text --model meterless/auto
```

These Runtime commands require your local Runtime; they are not needed for the
deterministic example. Authentication failures remain `unauthorized`, not `offline`.

## Execution, output and team handoff

`scripts/investigate_address.py` delegates to `address_investigation.py`, then the
existing identity resolver, reconciliation, legal `workflow.py` and root Critic.
`ModelAgents` uses the bounded provider adapter for Planner, Researcher and legal
Critic; strict canonical citations and independent support checks govern publication.
Complete request sizing includes schema/instructions. Tool/model budgets, deadlines,
one truncation retry and at most two legal revisions remain enforced.

Each run creates `reports/<output>/<timestamp>_<run-id>/` (or the selected output root)
containing `renter_report.md`, `investigation_report.md`, `investigation_report.json`,
`trace.jsonl` and `run_summary.json`. The renter report is deterministic presentation
of accepted findings; it makes no formatting model call. Draft claims stay in the
JSON audit, and failure reports retain accepted facts whenever feasible. All generated
reports, local memory and traces are ignored by Git.

`integration.board_update()` exports original evidence, accepted legal findings,
authority references, source/review limitations, Critic history and task status.
`SharedInvestigationState.read/update` provides a versioned, optimistic handoff
projection; stale writes cannot overwrite another agent's patch. `LegalSharedAdapter`
and `world_model_fact` remain the Keeper boundary/mapping. **Global context is an
adapter awaiting the team's orchestrator/transport**, not a deployed shared World
Model. H-MEM is separate. No global Planner or root Critic replacement is included.

See [final readiness audit](docs/PRE_PUSH_AUDIT.md) for what is test-backed versus
previously demonstrated live. Live NVIDIA calls and H-MEM retrieval were observed;
the latest model Critic response failed evidence-ID validation, so no completed live
legal review or legal publication is claimed. Historical law applicability, current
conditions, unit rent status and full source coverage remain unverified where absent.
Root BLOCKED always prevents publication. No live requests were made for this polish.

## Offline validation

```sh
.venv/bin/python -m pytest -q
HMEM_IMPL="$PWD/agents/legal_agent/vendor/hmem/src/index.ts" node --experimental-transform-types agents/legal_agent/vendor/hmem/conformance/runner.ts
.venv/bin/python critic.py critic-fixtures.json
```

The opt-in live test stays skipped unless `RUN_LIVE_MODEL_TESTS=1`. Historical notes
below refer to locally generated captures that are deliberately excluded from Git;
they are not clean-checkout prerequisites or current live-service guarantees.

## Historical implementation notes

# NYC Renter Legal Research Specialist

> Latest narrow repair: [strict observation isolation and replay results](docs/OBSERVATION_ISOLATION.md).

> Latest reliability pass: [bounded drafts, factual-only renter report and shared-state handoff status](docs/RELIABILITY_PASS.md).

> Canonical citations and independent claim support: [citation grounding repair and replay guide](docs/CITATION_GROUNDING.md).

> Legal retrieval and recoverable review-loop repair: [reproduction, changes and exact live replay results](docs/LEGAL_RETRIEVAL_REPAIR.md).

> Start here for a full observable run: [address CLI command and artifact guide](docs/ADDRESS_CLI.md).

> Latest provider and persistent-memory implementation: [Meterless Runtime v4 and H-MEM](docs/METERLESS_RUNTIME.md).

> Current safeguard/model/context/tracing status: [production integration checkpoint](docs/PRODUCTION_INTEGRATION.md).
> Earlier deterministic-only execution notes below describe the original captures.

## Address-driven multi-source investigation

The new command accepts arbitrary NYC addresses, borough and optional unit:

```bash
python scripts/investigate_address.py '840 Second Avenue, Manhattan'
python scripts/investigate_address.py '102-15 1 Street' --borough Queens --goals habitability
```

Run these commands from the repository root. The source registry covers 17
machine-readable agency datasets verified with real Zetaris rows, plus manual
HCR and court references. Upstream filters and pagination are registered per
bounded run; the old ZIP demo tables are not used as citywide data. The report
separates coverage, accepted factual findings, and legal uncertainty. Root Critic
vetoes and unit/lot scope remain enforced. See
[DYNAMIC_ADDRESS_INTEGRATION.md](docs/DYNAMIC_ADDRESS_INTEGRATION.md),
[VERIFIED_SOURCE_INVENTORY.md](docs/VERIFIED_SOURCE_INVENTORY.md), and
[ROOT_CRITIC_HANDOFF.md](docs/ROOT_CRITIC_HANDOFF.md).

The sections below describe the original specialist API and bounded HPD demo,
which remain supported for compatibility and regression testing.

Team integration now includes explicit Zetaris row mapping, an unchanged-root-Critic
bridge, externally reviewed evidence consumption, legal applicability limitations,
review history, and a local report renderer. See [TEAM_INTEGRATION.md](docs/TEAM_INTEGRATION.md)
for the responsibility matrix, provider boundary, real-data command and replay.
Two official HPD REST tables have now been registered and queried through Zetaris.
The genuine sample at **840 2 Avenue, Manhattan 10017** has verified identity and
two reviewed violation records from eight retrieved rows. Its legal result is
**inconclusive**, with unverified operative-law versions and bounded coverage.
`SHOW DATASOURCES` lists logical sources; physical REST sources are listed by
`SHOW LIGHTNING DATABASES`. The server-selected engine identity remains unexposed.

An incremental extension of the original Python/Flask prototype. Existing public interfaces, agent injection hooks, source search and all 19 original tests are retained. Python 3.11+; install `requirements.txt`, then run `pytest` or `python main.py`.

The default `main.py` command is **offline deterministic demo mode**, with fictional property fixtures. The separate `scripts/investigate_hpd.py --provider zetaris --source signsafe_hpd_20261025` command uses real Zetaris records and explicitly deterministic legal research. An optional API development fallback is selected explicitly and never labelled Zetaris. A configured model supplies structured planning, legal analysis and independent critique; a deterministic review gate always runs.

## Public integration contract (proposed version 1.1)

```python
from identity import resolve_building_identity
from workflow import investigate_legal_issue

identity = resolve_building_identity("214 E 7th St Apt 4B", {})
result = investigate_legal_issue(
    {"task_id": "renter-1", "question": "Due diligence before signing a lease",
     "building": {"address": "214 East 7th Street", "unit": "4B"}},
    {"identity": identity, "evidence": []},
)
```

Both return JSON-compatible dictionaries. Pydantic contracts live in `models/`; machine-readable schemas are in `docs/contracts/`. This is a proposed specialist contract, not an assumed team standard. No shared input or global state is mutated. Input validation errors raise Pydantic errors for Python callers and HTTP 400 for Flask callers.

Task input retains `task_id`, `question`, `building`, optional `issue_types`, `evidence_ids` and `requested_by`. Context accepts evidence, optional resolved identity or `identity_candidates`, and `as_of` (ISO date). Supplying explicit evidence IDs never falls back to unrelated records. Evidence IDs must be unique.

Output retains the original result fields and adds `schema_version`, `identity`, `record_matches`, `reconciliation`, `legal_sources`, `plans`, `tool_calls` and `research_requests`. Each issue finding includes referenced evidence, supported record descriptions, cited implications, contradictions, missing information, confidence, sufficiency and follow-up requests. A record description establishes what the record reports; it does not independently establish that an allegation is true.

Status is `completed`, `inconclusive` or `error`. Critic decisions are `PASS`, `REVISE`, `INCONCLUSIVE`, `BLOCKED`. Unresolved identity returns `inconclusive` with `BLOCKED`. PASS means reviewed, qualified research; it is not a safety certification or liability decision. Completed historical research does not establish present conditions.

## Identity and upstream data

`resolve_building_identity(address, context)` accepts optional `unit`, `borough`, and `candidates`. If candidates are omitted, only the explicitly fictional local fixtures are searched. Supply `candidates: []` to disable those fixtures. Unknown addresses return `missing`, never invented identifiers. Unit suffixes and street abbreviations are normalized; fuzzy geocoding is deliberately not implemented. Aliases require upstream candidate records. Unknown boroughs and address ranges require verification upstream.

An identity candidate has `candidate_id`, `address`, optional `borough`, `aliases`, and `identifiers`. Each identifier has `kind` (`bin`, `bbl`, `hpd_building_id`), `value`, `source`, `record_id`, `authoritative` and `fictional`. Only upstream-authoritative, non-fictional identifiers appear in `verified_identifiers`. This module preserves the upstream provenance assertion; it does not authenticate it with a government API. Sample identifiers are labeled `sample` and never appear as verified. Conflicting identifiers or multiple candidate buildings remain ambiguous. Reused identities are recomputed from candidate provenance.

Evidence keeps the original fields. `metadata` carries linkage and record semantics:

```json
{
  "evidence_id": "upstream-123",
  "kind": "case_filing",
  "source": "Upstream public docket adapter",
  "date": "2026-01-12",
  "description": "A petition was filed; outcome not supplied.",
  "building_address": "214 East 7th Street",
  "status": "pending",
  "metadata": {
    "bin": "1000001",
    "scope": "building",
    "issue": "litigation",
    "origin_source": "public docket",
    "origin_record_id": "example-case-id"
  }
}
```

This example's BIN is fictional. Supported evidence kinds additionally distinguish inspection, permit, filing, decision, judgment, warrant and executed eviction. Upstream adapters must classify accurately and preserve source URLs/retrieval timestamps in metadata. A source label alone is not proof of reliability.

Identifier conflicts override address similarity. A BBL-only building record is quarantined because one lot can contain multiple buildings; a `scope: property` record remains explicitly lot-level. `scope: unit` requires the target unit. `scope: entity` is quarantined pending independent property linkage. Rejected or quarantined evidence invalidates dependent findings and clears their legal conclusions. Reconciliation preserves duplicate groups, temporal/status disagreements and records older than 90 days. Ninety days is a triage threshold, not a legal rule or proof that a newer record is current. Duplicates require shared origin keys; semantic duplicate discovery is not implemented.

`GeoSearchAdapter`, `HPDAdapter` and `ZetarisAdapter` are mapping interfaces for injected read-only loaders, **not live connectors**. Obtain candidates through the team's data layer, then pass validated JSON. External requests in results are for the main orchestrator to route; this specialist does not launch other specialists.

## Research and review

Address-first due diligence considers identity, heat, maintenance, construction, eviction, litigation and rent regulation without assuming a problem in each. Offline mode uses explicit routing and conservative templates. Model mode generates executable ordered research questions with required inputs, tools, dependencies, priority and completion conditions. Only `legal_search`, `evidence_review` and `request_external` are permitted. The workflow executes selected searches; the model cannot fabricate retrieval results or modify budgets.

The local source catalog distinguishes statutes from agency/court guidance and exposes version limitations. Retrieval is keyword search over attributable catalog paraphrases, **not live retrieval of current law**. Existing unversioned quotations were removed. Inherited hot-water code text conflicts with current HPD guidance; that conflict is explicitly flagged pending operative-code verification. Incident-date applicability must be established before substantive legal advice. No invented case holdings or judicial decisions are supplied.

The Critic checks evidence membership/classification, rejected dependencies, citation existence, source/identifier correspondence, known jurisdiction/date boundaries, obvious unsupported liability/unit-status/eviction-stage assertions and broad due-diligence coverage. A separate model critique assesses semantic support and interpretation when configured. Deterministic checks are conservative rules, not a complete proof that every statement is entailed by a citation. Production semantic review and source-version retrieval still require evaluation.

Critic feedback changes the next plan and search activity. Identical model replans stop as inconclusive. When finding IDs identify affected work, valid unaffected findings are retained. Current source search remains per revised question with exact-query caching; this is not a general dependency scheduler, and new broad questions may repeat related research. Failure within the budget produces qualified output rather than forced approval.

## Model configuration

Copy `.env.example` to ignored `.env`, or set environment variables. `main.py` loads `.env`; importing the specialist expects the hosting Flask app to configure its environment.

Set `LLM_PROVIDER=compatible`, `LLM_BASE_URL=https://provider.example/v1`, `LLM_MODEL=...`, `LLM_API_KEY=...`. The adapter calls `/chat/completions` using JSON mode and validates against Pydantic. The same contract can target compatible NVIDIA inference endpoints; endpoint/model compatibility has **not** been tested live. Replace providers by injecting an adapter implementing `complete(schema, payload)` into `LegalResearchWorkflow(model_adapter=...)`.

No credentials are included in model messages or committed configuration. HTTPS is required; credential-bearing redirects are refused. Transport failures have bounded retries and sanitized errors. Invalid model JSON stops safely; it does not silently masquerade as demo reasoning. Mocked model tests validate the entire planning/research/critique path. To explicitly run the separate live smoke test, configure credentials and use `RUN_LIVE_MODEL_TESTS=1 pytest -m live`; ordinary tests require no network.

## Deterministic safeguards and context

`ExecutionLimits` enforces ceilings of two revisions, ten research tool attempts, two transient retries per call and nine model calls; default retries are one. Both successful and failed search attempts consume the budget. Exact cached queries consume no new tool calls. Defaults include five-second search waits and 30-second model transport deadlines. No external write tools or recursive delegation exist. Future SQL access accepts a fixed parameterized BIN query template, not agent SQL.

Python search timeouts stop waiting; Python cannot kill an already running thread. Future remote adapters must also enforce transport deadlines and read-only database credentials. All model adapters are wrapped with call budgets, output validation and waiting deadlines. Custom adapters must also enforce transport deadlines because Python cannot kill running threads; the supplied HTTP adapter implements transport timeouts and bounded retries. Do not expose arbitrary loader or adapter callables in HTTP requests.

Agent context contains task-specific evidence, identity, sources, findings and feedback, not accumulated chat history or credentials. The authoritative registry is separate from projections. `MemoryAdapter` defines the future Meterless H-MEM boundary; no competing persistent memory is implemented. Memory is not wired into production execution yet. All retrieved text is treated as untrusted data; prompt instructions reduce injection risk but are not a guarantee of model behavior.

## Flask and demonstrations

`python main.py --serve --port 5001` provides `GET /health`, `POST /resolve-identity` (`address`, optional `context`) and `POST /investigate` (`task`, optional `context`). These are local hackathon endpoints without authentication; deploy behind the team's authenticated application. No live service is started by tests.

`python main.py` prints the fictional heat example. The original alternate examples remain:

```bash
python main.py --address "88-12 Roosevelt Avenue"
python main.py --address "410 West 145th Street"
python main.py --address "19 Pierrepont Street"
```

These return complaint-only inconclusive, supported pest research completed, and thin-water-record inconclusive respectively. `python examples/due_diligence.py` prints a broad assessment with explicit missing categories.

## Remaining integrations

The initial HPD Building Files/violation path works through Zetaris. Broader coverage, GeoSearch, 311/DOB, HPD litigation, eviction datasets, WebCivil Local, Supreme Court/NYSCEF documents, entity ownership/property linkage, operative-law retrieval, Nightshift validation and Meterless storage remain team integration work. Restricted, sealed and missing court records must be reported as coverage limitations. A missing search result is never proof of a clean history. Apartment rent status still requires unit-specific records. No production legal accuracy or live provider reliability claim is made.
