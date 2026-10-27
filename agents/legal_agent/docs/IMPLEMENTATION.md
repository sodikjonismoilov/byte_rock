# Implementation and validation record

> **Historical development log.** This file records an earlier checkpoint. Its test counts, "not verified" statements and
> `reports/...` file references describe that moment only: `reports/` held local, gitignored captures that are not in this
> repository. Current status and verified results are in the [root README](../../../README.md).

The original repository was inspected before edits: workflow, Pydantic schemas, every agent/tool/test, CLI, fixtures and catalog. Baseline: 19 passing tests. A source snapshot was retained in the chat workspace's work/baseline folder. The implementation extends the existing workflow rather than introducing an agent framework.

The incremental plan preserved public contracts with defaulted additions, then implemented identity resolution; per-issue findings and catalog expansion; provider-backed structured agents; reconciliation and critique; execution/context boundaries; and Flask/contracts/examples. Tests ran at each stage. Existing tests were preserved without edits. Final validation: **60 passed, one explicitly disabled live-model smoke test skipped**. Compilation and both standalone examples also pass. Four original example statuses remain heat completed, complaint-only pests inconclusive, confirmed pests completed, and thin water evidence inconclusive.

Working offline components: independently callable identity resolver, provenance-preserving candidate matching, identifier conflicts and aliases, lot/building/unit distinctions, per-category planning and findings, local legal retrieval, event/status reconciliation, duplicate origin tracking, dependency invalidation, deterministic review gate, bounded retries/deadlines/tool budgets, context projections, JSON/Pydantic contracts and both Flask routes.

Working through mocked model responses: actual provider adapter request/response construction, JSON validation, provider error handling, model planning and explicit search execution, model legal drafts, independent model critique, meaningful revised searches, retained unaffected findings, deterministic veto, model-call and waiting limits. No real model was invoked. No paid API was called. Endpoint compatibility with any specific NVIDIA deployment remains untested.

Simulated inputs: all local properties, BIN/BBL values, complaints and violations are fictional. `sample` is not verified NYC identity. Local legal sources are real attributable URLs and conservative paraphrases; source retrieval at runtime is catalog search rather than a live version check. A hot-water source-version disagreement remains explicitly disclosed. No quotations or case holdings were fabricated.

Interfaces only: GeoSearch/HPD/Zetaris loader adapters, a fixed read-only SQL template, and Meterless H-MEM memory protocol. There are no live government/court connectors or persistent memory integration. Court filings, execution records, ownership linkage and full coverage need upstream integration. Entity-only litigation is quarantined.

Practical limits: address normalization is lexical, not geocoding; unknown and ambiguous addresses need upstream work. Source provenance assertions are not independently authenticated. Reconciliation uses issue/status/origin metadata and cannot discover arbitrary semantic duplicates. Rules catch structural citation problems and selected unsafe interpretations; they cannot prove arbitrary prose is supported. Model semantic legal accuracy has not been evaluated live. Python worker threads cannot be forcibly terminated; remote connectors need transport deadlines and read-only credentials. Targeted revisions preserve named unaffected findings but are not a general task dependency scheduler.

The authoritative registry stays separate from agent context and is not shared global state. Source objects are copied per search instance to prevent cached mutable state from leaking between investigations. Retrieved text is untrusted; prompt injection remains a model risk, while deterministic tools and permissions constrain available actions.
