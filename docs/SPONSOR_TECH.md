# SignSafe — Sponsor Technology Integration

## SignSafe overview

SignSafe helps prospective NYC renters evaluate fragmented official housing records
before signing a lease. A housing violation, construction permit and administrative
proceeding can identify a property differently and describe different dates or outcomes.
SignSafe preserves those distinctions, attaches agency citations to factual observations,
and exposes what could not be checked.

Zetaris provides the authoritative-data access layer, Meterless supplies persistent
agent memory and model routing, and NVIDIA Nemotron supports legal planning, research
and critique. Their distinctive use is the separation of source records, remembered
context, model interpretation and deterministic validation—not treating a generated
answer as evidence.

## Zetaris — Implementation, deployed USL and tests

The [Zetaris provider](../agents/legal_agent/tools/address_data.py) registers bounded
REST definitions and executes filtered, paginated queries through the existing
authenticated gateway. Original IDs, statuses, dates and source provenance remain
available to identity resolution and root attribution review. An API development
fallback is explicitly selected and labeled; live failures do not silently become
synthetic investigations.

A deployed Unified Semantic Layer, `renter_records_v1.events`, presents a common
record contract across three verified NYC sources: HPD Housing Maintenance Code
violations, DOB permits and the FDNY subset of OATH administrative records. Six
exploratory queries succeeded, followed by compilation/deployment, activation and
three working USL queries. The bounded slice contains **200 HPD, 20 DOB and 20 OATH
records**. The executed `source_identity_integrity` rule checked **240 records:
240 valid, 0 invalid**.

The rule checks original-ID presence, allowed datasets, an official source-URL prefix
and BIN/BBL format when present. It does not establish property matches, current
conditions, legal compliance or citywide completeness. The model uses `UNION ALL`;
missing identifiers remain NULL rather than becoming inferred links.

The USL centralizes heterogeneous column mappings and citation construction. It is
**deployed independently of the application's Investigator**, which still uses its
existing Zetaris source path. The [sanitized execution summary](receipts/zetaris_usl_verification.md)
publishes actual milestones, counts and SQL hashes without raw records or credentials.
[The USL appendix](ZETARIS_USL.md) supplies SQL, scope and reproduction details;
[runner tests](../tests/test_zetaris_usl.py) cover bounded execution, safe resume,
existing-object refusal and failure handling.

## Meterless — H-MEM and Nightshift implementation and tests

**H-MEM is the implemented Meterless Engine.** The
[Python adapter](../agents/legal_agent/memory.py) and
[Node bridge](../scripts/hmem_bridge.mjs) invoke the vendored official engine for
persistent cross-run recall. [Cold/warm tests](../agents/legal_agent/tests/test_hmem.py)
exercise an empty store, subsequent recall, deduplication, invalidation and provenance;
the official conformance suite passes **13/13**.

Durable finding memory requires successful legal review and accepted source references.
Incomplete reviews may retain explicitly labeled working feedback, never unsupported
draft conclusions. Recalled memories are untrusted context, not evidence or legal
authorities. The versioned investigation handoff is separate from H-MEM and is not
claimed as a deployed Meterless World Model service.

The integration branch's [front door][planner-run] enables H-MEM by default at
`.local/legal-memory`. Local files persist across application runs. Containers need
a persistent mount at `/app/.local` to retain memory across containers; `/app/outputs`
can be mounted separately for reports and traces.

**Nightshift is the live-mode model-provider default in that front door:**
`LLM_PROVIDER=meterless` with configured reasoning, subject to explicit environment
overrides. The [Runtime adapter](../agents/legal_agent/tools/meterless.py) sends
bearer-authenticated OpenAI-compatible requests with application/scope headers and
supports discovered routing IDs. [Provider tests](../agents/legal_agent/tests/test_meterless.py)
cover authentication, URL normalization, routing discovery, plain text and error states.

A [committed smoke receipt][nightshift-receipt], produced by the
[smoke script][nightshift-script], records HTTP 200 for `meterless/auto`,
`meterless/fast`, `meterless/cheap` and `meterless/deep`, each identifying the response
model as `nvidia/nemotron-3.5-bolt-e4b`. This is direct routing evidence, distinct from
H-MEM's engine conformance.

## NVIDIA Nemotron — Contribution and tests

Nemotron contributes to the existing [model-backed legal stages](../agents/legal_agent/agents/model_agents.py):
the Planner selects research tasks, the Researcher uses retrieved authorities and
available official excerpts, and the Critic reviews the draft. The
[structured adapter](../agents/legal_agent/tools/llm.py) validates responses; canonical
citation metadata comes from the retrieved registry rather than freely generated titles
or identifiers. [Citation](../agents/legal_agent/tests/test_citation_grounding.py) and
[observation-isolation tests](../agents/legal_agent/tests/test_observation_isolation.py)
verify that unknown sources cannot become accepted claims.

Earlier direct NVIDIA replays exercised these stages; one invalid Critic response
correctly prevented legal publication while preserving factual findings. Separately,
the [Planner's committed README][planner-notes] documents three Nemotron model calls
through Nightshift during a synthetic investigation. Its full trace remains local,
and the reported legal result was INCONCLUSIVE. A real-Zetaris-plus-Nightshift
end-to-end application run remains to be demonstrated. These evidence levels support
model participation and failure containment, not an accuracy or successful legal-publication claim.

## What makes these sponsor integrations distinctive

Each technology has a different trust responsibility:

- **Authoritative data:** Zetaris exposes agency records; the USL preserves their
  distinct identities and provenance rather than asserting cross-source property links.
- **Persistent memory:** H-MEM recalls reviewed context or labeled feedback without
  promoting it into an authoritative source registry.
- **Model routing:** Nightshift aliases select execution routes; the returned NVIDIA
  model identity identifies which model answered. Routing is separate from interpretation.
- **Evidence interpretation:** Nemotron proposes research and legal observations;
  source identity alone does not prove claim support or historical applicability.
- **Deterministic validation:** typed references, legal-publication gates and traceable
  policy checks constrain model output. The integration branch also exposes a separate
  rule-based renter verdict, rather than asking a model to invent one.

Accepted factual reporting can remain useful when legal review is incomplete. The
integration branch implements [CLI sample mode][planner-run] and a
[web application][planner-web] with a browser frontend, trace polling and report
downloads. Its synthetic replay is explicit; no live address is silently replaced.

## Compact implementation evidence and links

Application evidence below is pinned to inspected Planner commit
[`6df8fe7`][planner-tree] on `origin/recovered/all-work`; those application files have
not been merged into this sponsor-compliance working branch.

- **Zetaris:** [safe live execution summary](receipts/zetaris_usl_verification.md),
  [SQL/deployment appendix](ZETARIS_USL.md) and [support tests](../tests/test_zetaris_usl.py).
- **Meterless:** [official H-MEM suite](../agents/legal_agent/vendor/hmem/conformance/runner.ts),
  [memory tests](../agents/legal_agent/tests/test_hmem.py) and the
  [committed Nightshift receipt][nightshift-receipt].
- **Application:** [front-door tests][planner-run-tests] and
  [web sample/trace/download tests][planner-web-tests] exercise the actual interfaces.
  Recorded Captain validation is **290 passed, 1 skipped**; the combined integration
  acceptance suite is a separate check in [the team handoff](TEAM_HANDOFF.md).

After the [documented dependency setup](../agents/legal_agent/README.md#clean-checkout-setup),
run from a checkout containing the integration files:

```sh
SAMPLE_MODE=true .venv/bin/python run.py input_examples/1.json
SAMPLE_MODE=true .venv/bin/python webapp.py
.venv/bin/python -m pytest -q agents/legal_agent/tests tests/test_zetaris_usl.py
HMEM_IMPL="$PWD/agents/legal_agent/vendor/hmem/src/index.ts" node --experimental-transform-types agents/legal_agent/vendor/hmem/conformance/runner.ts
```

Sample execution needs no external credentials; exit 2 denotes an expected
INCONCLUSIVE legal result. Traces identify providers, modes, model operations and
failures. H-MEM's [upstream commit/hashes](../agents/legal_agent/vendor/hmem/UPSTREAM.json)
and [license](../agents/legal_agent/vendor/hmem/LICENSE) disclose third-party code;
public NYC datasets, legal texts and any pre-build preparation belong in submission
declarations. Development tooling is separate from runtime integrations: the supplied
Legal Agent history includes Codex, with no exclusive Cursor claim. Actual Cursor
usage and final submission checks are assigned in [TEAM_HANDOFF.md](TEAM_HANDOFF.md).

[planner-tree]: https://github.com/sodikjonismoilov/byte_rock/tree/6df8fe7f5534beb068ef6cf6e0b1ded1752ba67b
[planner-run]: https://github.com/sodikjonismoilov/byte_rock/blob/6df8fe7f5534beb068ef6cf6e0b1ded1752ba67b/run.py
[planner-web]: https://github.com/sodikjonismoilov/byte_rock/blob/6df8fe7f5534beb068ef6cf6e0b1ded1752ba67b/webapp.py
[planner-notes]: https://github.com/sodikjonismoilov/byte_rock/blob/6df8fe7f5534beb068ef6cf6e0b1ded1752ba67b/README.md#nightshift--nvidia
[nightshift-receipt]: https://github.com/sodikjonismoilov/byte_rock/blob/6df8fe7f5534beb068ef6cf6e0b1ded1752ba67b/docs/receipts/nightshift_smoke.json
[nightshift-script]: https://github.com/sodikjonismoilov/byte_rock/blob/6df8fe7f5534beb068ef6cf6e0b1ded1752ba67b/scripts/nightshift_smoke.py
[planner-run-tests]: https://github.com/sodikjonismoilov/byte_rock/blob/6df8fe7f5534beb068ef6cf6e0b1ded1752ba67b/agents/legal_agent/tests/test_run_front_door.py
[planner-web-tests]: https://github.com/sodikjonismoilov/byte_rock/blob/6df8fe7f5534beb068ef6cf6e0b1ded1752ba67b/agents/legal_agent/tests/test_webapp.py
