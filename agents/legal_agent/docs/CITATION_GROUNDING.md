# Citation grounding repair

## Reproduction and cause

The previous `reports/legal_retrieval_verification.json` replay executed legal
retrieval but let the model generate citation identifiers independently of the
retrieved catalog. All four audited references failed identifier matching. A real
source ID, a generated identifier and an interpretation were being validated as
one concept. The earlier repair guide remains an unchanged historical receipt.

## Targeted changes

- `tools/llm.py` now uses a model-facing selection schema for ResearchDraft:
  citations contain a canonical retrieved `authority_id` and an exact supporting
  quotation. The allowed IDs come from the authorities actually delivered in the
  model context, not the complete catalog. Citation metadata is forbidden there.
- `citations.py` converts selections into the existing public ResearchDraft and
  copies identifiers, exact titles, URLs, jurisdiction, authority type and excerpt
  provenance from the executed retrieval registry. Unknown/unretrieved IDs fail
  model validation. Public evidence/authority/memory domains remain separate.
- Source-text selections can omit a duplicate statement: the runtime formats the
  selected quotation with explicit current-guidance or statutory attribution.
  An explicit model statement is never rewritten to conceal an unsupported claim.
- Independent support validation rechecks excerpt hashes, exact quotations,
  source type, scope, observation dates and topic. It conservatively verifies only
  narrowly attributed exact source-text statements. A paraphrase, property-specific
  liability interpretation or historical application is not automatically verified.
  The legal Critic recomputes these checks instead of trusting `supported` flags.
- Heat guidance is excluded from unrelated litigation searches; boiler guidance
  is excluded from unrelated permit searches. Known absent historical versions
  become explicit external-research limitations instead of repeated catalog searches.
- `ModelAgents` retains the existing dependency sorter, targeted review loop and
  limits. Context packing reserves space for the draft and role instructions under
  the same 64,000-byte payload ceiling, keeps mandatory uncertainty and records
  omissions. The public report keeps original evidence and canonical citations.
- Reports and run summaries distinguish cited-claim source identity, independent
  source-text support and findings actually published after review. Root BLOCKED
  precedence, two revisions, tool/model budgets, H-MEM separation and all histories
  remain in place. No root Critic policy or fixture was edited.

## Replay interpretation

`reports/citation_grounding_verification.json` is the machine-readable receipt for
all attempts and the final observed sequence. All attempts use live NVIDIA model
calls and persistent local H-MEM with the previously captured Zetaris evidence in
`reports/investigations/20261026T035040435638Z_d27bd49e-6969-42cd-b7aa-478930b1d4d3/`.
These are recorded-data replays, not new Zetaris retrievals or live website fetches.
Official excerpt snapshots retain their original URLs, retrieval provenance and
historical-version limitations.

Earlier attempts are retained, including a Critic payload-budget stop and
Researcher responses truncated at the unchanged 2,048-output-token limit. Failure
reports and trace events record these outcomes without raw model responses or
credentials. Prompt packing and concise output instructions address those failures
without raising execution budgets or weakening publication checks.

## Reproduce

Run from the repository root with locally configured NVIDIA credentials:

```sh
PYTHONDONTWRITEBYTECODE=1 LEGAL_CONTEXT_MAX_BYTES=60000 LEGAL_CONTEXT_MAX_TOKENS=60000 LEGAL_MODEL_MAX_TOKENS=100000 .venv/bin/python -B scripts/investigate_address.py '840 Second Avenue, Manhattan, NY' --borough Manhattan --provider replay --replay reports/investigations/20261026T035040435638Z_d27bd49e-6969-42cd-b7aa-478930b1d4d3/investigation_report.json --reasoning nvidia --memory-dir .local/legal-memory-demo --model-timeout 60 --max-model-calls 9 --max-revisions 2 --output reports/citation_grounding_replays
```

Every run creates its own report MD/JSON, trace JSONL and run summary. Exit code 2
means inconclusive, not a publication success. A correct source identity never
implies verified historical law, safe conditions, legal liability or Critic PASS.

## Regression coverage

`tests/test_citation_grounding.py` covers canonical selection, metadata population,
unknown/unretrieved and wrong-domain IDs, memory separation, wrong-topic sources,
unsupported interpretations, current versus historical applicability, independent
Critic checks, context packing and historical-search termination. Existing workflow,
Zetaris, root-Critic, H-MEM, budget, revision and failure-report tests also run.

## Observed result

The citation-bearing attempt `20261026T050647281424Z_39fa8c0f-2932-46a3-8bc3-b2bab2be0322`
contains **3 cited claims with valid source identity, 0 independently verified
claim-support checks, and 0 published legal findings**. One assertion was unrelated
to its selected excerpt; two statements lacked explicit current-guidance attribution.
They were not promoted to PASS. Runtime attribution formatting and its regression
test were added subsequently; a provided false interpretation is never rewritten.

The latest full-address attempt `20261026T053431892102Z_9f1ef437-5378-43d2-abf3-bdc2dff9c6ad`
completed identity/reconciliation, root record reviews, H-MEM retrieval, live NVIDIA
planning, and one `legal_search` returning eight authorities (five excerpt-backed).
Its three planned tasks were ordered jurisdiction review → legal duties lookup →
record interpretation, with two valid dependency edges. The live Researcher then
hit `finish_reason=length`; no draft was accepted, no local/model Critic review or
revision ran, H-MEM storage was skipped, and a traced INCONCLUSIVE failure report
was saved. Its counters are **0 completed cited claims, 0 support checks verified,
0 published legal findings**. Initial dependency order is verified live; revised
ordering is covered by tests but not exercised by this replay. The source-identity
repair is tested; a complete full-address live review remains unverified because
of model output truncation.

Validation: **241 pytest tests passed, 1 opt-in live test skipped**; official H-MEM
**13/13** and unchanged root Critic **12/12**. A configured-secret-value scan found
zero matches across the 21 replay/receipt artifacts. No commit or push was made.
