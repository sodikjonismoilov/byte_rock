# Meterless Runtime v4 and persistent legal memory

The provider follows the Runtime 1.4/v4 contract on
https://meterless.ai/engines.html (POWER → Add Meterless as a provider).
The repository's older provider guide still describes Runtime 0.90.0; v4 is
implemented here. NVIDIA remains a separately selectable provider. The previously
verified NVIDIA address execution and its publication veto remain intact.

## Provider

`tools/meterless.py` exposes `MeterlessRuntime`, `RuntimeConfig`, `MeterlessSettings`
and `auto_detect`. Canonical provider ID: `meterless`; display name: Meterless Runtime.
`tools/llm.py` reuses this transport for structured legal agents. Set
`LLM_PROVIDER=meterless`; `LLM_PROVIDER=nightshift` is a compatibility alias.

- Defaults to `http://127.0.0.1:8088/v1`; normalizes scheme-less URLs and the documented
  pasted endpoint suffixes to origin + `/v1`, including IPv6. Credentials in URL
  userinfo/query strings and unsupported paths are rejected without echoing input.
- Connect links are parsed locally; only origin + `/v1` and decoded fragment `k`
  are saved. Links and tokens never appear in request URLs or diagnostics.
- Every call sends real Bearer auth and `meterless-app: signsafe-legal`; chat sends
  `meterless-scope: user`. `rt-local` is rejected. Redirects are not followed.
- Models come from GET `/v1/models`; unknown `meterless/*` IDs are retained. A selected
  routing ID must be advertised. `meterless/auto` is never assumed to exist merely
  because the process responds. `/healthz` is not used to declare online status.
- Discovery returns `unauthorized` for 401/403, `online` only for 200 plus Meterless
  IDs, otherwise `offline`. Chat 401/403 also updates status to unauthorized.
- Auto Detect tries ports 8088, 8090, 8787, 11434, each on 127.0.0.1, localhost, [::1],
  and saves the first online or unauthorized hit. All-offline detection leaves
  previous settings untouched. No runtime is installed or started automatically.
- `complete_text(prompt, model='meterless/auto')` accepts and returns strings. Plain
  text is not wrapped in JSON or a structured schema. Chat timeout is 180 seconds.
  Structured calls still validate Pydantic output and enforce the aggregate deadline;
  their outer wait uses 180 seconds for Meterless rather than the former 60-second
  model ceiling. NVIDIA and injected-adapter limits remain unchanged.

Private configuration lives in ignored `.local/meterless.json` with mode 0600,
under the exact key `meterless_runtime_token`. It also holds base URL and routing ID.
A saved token is bound to its origin and is not reused after a host change.
RuntimeConfig hides token fields from repr. Settings routes never return the key.

Supported environment inputs (keep real values in ignored `.env.local`):

- `LLM_PROVIDER=meterless`
- `METERLESS_BASE_URL`, `METERLESS_MODEL`, `METERLESS_RUNTIME_TOKEN`
- Lowercase `meterless_runtime_token` is accepted as an application configuration key.
- `METERLESS_STATE_DIR`: explicitly configured runtime directory containing `proxy-token`.
- Existing `NIGHTSHIFT_BASE_URL`, `NIGHTSHIFT_MODEL`, `NIGHTSHIFT_API_KEY` map to the same
  v4 contract when provider `nightshift` is selected. No runtime state directory is guessed.

From the repository root:

```bash
.venv/bin/python -B scripts/meterless_runtime.py detect
.venv/bin/python -B scripts/meterless_runtime.py configure
.venv/bin/python -B scripts/meterless_runtime.py status
.venv/bin/python -B scripts/meterless_runtime.py text --model meterless/auto
```

`configure` reads connect links and tokens with hidden input. Do not put connect links
or keys on the command line. To read and save an existing runtime token, use
`status --state-dir /actual/runtime/stateDir`; only use an actual known directory.
The configuration does not automatically switch NVIDIA; choose `LLM_PROVIDER=meterless`.

An optional local settings page provides password fields and a discovered routing
picker with Auto Detect. Start the existing Flask app with:

```bash
.venv/bin/python -B -m agents.legal_agent.main --serve --meterless-settings --port 5001
```

Open `http://127.0.0.1:5001/providers/meterless/settings`. Routes are disabled by default,
require loopback clients, check Origin for mutations and require JSON POSTs. Settings
pages are not cached or framed. Leave these operator routes disabled in deployment;
team authentication and reverse-proxy configuration remain team responsibilities.

## Actual runtime status

The local 12-endpoint probe found **LIVE_NIGHTSHIFT_NOT_AVAILABLE**. No runtime token
was fabricated or runtime installed. Wrong-token→unauthorized, Auto Detect, unknown
routing IDs, real headers, private connect parsing, and string-returning chat pass
mocked transport tests. Live Meterless inference is **not verified**. The provider
is ready for a real runtime/connect link, not claimed online.

A fresh NVIDIA regression smoke after this provider addition passed with actual
configured/API-returned model `nvidia/nemotron-3.5-bolt-e4b`. Receipt:
`reports/nvidia_meterless_provider_regression.json`. No fallback was used.

## H-MEM engine and Python bridge

`vendor/hmem/src` contains the unmodified official TypeScript reference engine,
pinned to Meterless commit `1742dec56a66e58eef9dda2d2b865823758ca8cd`. Apache-2.0
license, original hashes and official conformance vectors/runner are included.
The root README, llms.txt, AGENTS.md and engines/hmem/AGENTS.md were inspected.
This is the real reference engine, not a reimplementation claiming its API.

`memory.py` connects Python to `scripts/hmem_bridge.mjs` with bounded JSON stdin/stdout.
It requires Node 22 with `--experimental-transform-types`; no npm runtime packages
or network calls are needed. Each invocation hydrates the same engine directory.
Python serializes read/write operations with a deadline-bounded file lock; node
writes private files under umask 077. The engine's state.json/ledger.jsonl store
**memory**, not the authoritative evidence registry or team-global state.

`LegalResearchWorkflow(memory=LegalMemory(directory))` retrieves short hints after
identity/reconciliation and before agent reasoning. Complete records stay in the
existing evidence registry/reports. The existing context projection includes hints
with IDs, references, timestamps, trust labels and relevance, always `is_evidence=false`.
Memory never upgrades held records or Critic vetoes. Scope includes canonical building,
unit and sample-versus-official origin, and works across separate investigation/task IDs.
Duplicate hint content is omitted from the prompt. Local recall requests top three
at threshold 0.1 (a deliberate recall-oriented adapter setting); the unmodified engine
retains its canonical scoring and default 0.35 threshold for normal upstream calls.

After completed/PASS, valid cited findings can be stored as provenance-linked long-term
memory. Storage requires accepted evidence references and source URLs; blocked/error
results are not stored. An INCONCLUSIVE/REVISE run may store only the factual review
feedback in working memory, explicitly `review_feedback_only`, never its draft claims.
Repeated validated updates are deduplicated using stable content/provenance keys.
Separate review observations retain their review references. Invalidation sets confidence
zero and records an audited update, retaining the original record. A validated replacement
may be referenced with `superseded_by`; cross-scope replacements are rejected.

Sample memories require explicit `allow_sample=True` and cannot cross into live scope.
The application does not auto-run dreaming, conflict resolution, sleep or unreviewed
mining. The full official engine services remain available in the reference, including
its dream approval boundary. Keeper still owns shared authoritative state; this optional
legal-local memory must not be configured as another global evidence database.

CLI opt-in:

```bash
.venv/bin/python -B scripts/investigate_address.py '840 Second Avenue' --borough Manhattan --provider replay --replay reports/nvidia_live_identity/investigation_report.json --goals property_identity --reasoning deterministic --memory-dir .local/legal-memory-demo --output reports/hmem_cold
.venv/bin/python -B scripts/investigate_address.py '840 Second Avenue' --borough Manhattan --provider replay --replay reports/nvidia_live_identity/investigation_report.json --goals property_identity --reasoning deterministic --memory-dir .local/legal-memory-demo --output reports/hmem_warm
```

Use a new memory directory for an empty cold state. Verified demonstration: cold retrieved
zero hints; a separate warm process retrieved one useful prior-review hint. These two
runs used **recorded real NYC rows and deterministic reasoning**, not fresh Zetaris or
live Meterless inference. Both remained inconclusive. Separate pytest fixtures verify
validated finding persistence, provenance, context reinjection, invalidation and replacement.
No token savings or improved legal accuracy is claimed from the retrieval demonstration.

## Verification

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider
HMEM_IMPL="$PWD/agents/legal_agent/vendor/hmem/src/index.ts" node --experimental-transform-types agents/legal_agent/vendor/hmem/conformance/runner.ts
.venv/bin/python -B critic.py critic-fixtures.json
```

Official vendored H-MEM conformance: **13/13**. Root Critic policy is unchanged.
The reference engine is intentionally minimal; Node's transform flag is experimental.
Shared Keeper approval, production persistence lifecycle, and a real Meterless Runtime
are still external dependencies. The existing broader-address mandatory-context-budget
limit is retained. No commits or pushes were made.

Final verification: **195 pytest passed, one opt-in live-model test skipped**;
root fixtures **12/12**. Official conformance output is saved in
`reports/hmem_conformance.txt`. Summary receipt:
`reports/meterless_integration_verification.json`.

A fresh live Zetaris/NVIDIA address run also used the new memory path:
`reports/hmem_nvidia_live/`. It recalled one non-authoritative review hint and
completed all three real NVIDIA roles, retained verified identity and two accepted
factual findings, and removed its temporary namespace. Its legal review stayed
inconclusive and published zero legal findings. The warm hint's source was recorded
review feedback; this does not claim newly validated legal memory or local Runtime
inference. Configured-secret scanning found no matches in new code or demo artifacts.
