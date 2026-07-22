# Retrieval Ranking

[English](retrieval_ranking.md) | [Русский](../ru/retrieval_ranking.md)

## Purpose

Project Knowledge Bot ranks sources before any LLM call. This layer must be
testable independently: an incorrect source cannot be repaired reliably by a
better prompt or model.

The deterministic path is:

1. classify query intent;
2. calculate BM25 base scores and policy adjustments;
3. combine BM25 and vector scores using a selected fusion policy;
4. apply post-rerank policies;
5. route sources into primary, supporting, or excluded context buckets.

`src/asu_june_bot/retrieval/ranking_policies.py` contains named policies.
`ranking_signals.py` contains reusable structural predicates. The BM25 and
post-rerank modules orchestrate these components and do not own customer
vocabulary.

## Ranking Profile

Public defaults live in `configs/asu_june_bot/ranking_profile.yaml`. Private or
customer-specific terminology belongs only in the ignored file
`configs/asu_june_bot/ranking_profile.local.yaml`.

The local YAML is a deep overlay. A list supplied by the local file replaces
the complete public list for that group; preserve every default marker that is
still required. The profile is validated at startup: malformed group names,
non-string values, duplicates, oversized values, or unsupported versions fail
closed.

Do not add real customer names, corpus paths, queries, or document excerpts to
the public profile or tests.

## Diagnostics

Every score adjustment records:

- stage (`bm25` or `post_rerank`);
- policy and stable label;
- multiplier;
- score before and after the adjustment;
- ranking profile version.

Hybrid results also report the selected fusion policy and vector/BM25 weights.
Diagnostics explain ranking behavior; they are not an authorization boundary
and must not contain private paths or full source content.

## Regression And Coverage Gates

`tests/fixtures/retrieval/ranking_characterization.jsonl` is a bounded public
synthetic behavior baseline. Update it deliberately before changing expected
ranking behavior. Policy tests cover individual positive, negative, and
penalty branches.

Run the retrieval-only gate:

```powershell
python scripts/48_retrieval_coverage.py
```

The command runs without Ollama, network access, or LLM calls and enforces
module plus group branch-coverage thresholds for ranking core and source
routing. The canonical `scripts/46_ci_verify.py` runs it after the full test
suite.
