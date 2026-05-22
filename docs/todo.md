# TODO

Обновлено: 2026-05-22.

## Retrieval quality roadmap

### Реализовано

```text
realistic-100 eval
realistic-500 eval
manual review pipeline
approved regression set
failure bucket classification
hard source-quality gate
hybrid vector+lexical rerank
metadata-aware retrieval
SQLite FTS5 lexical retrieval
bucket-driven retrieval expansion
harmful security guard
project security allowlist
compact realistic review builder
FTT section-aware rerank
FTT requirement-id routing
source tiering
hard doc-type routing
low-priority source penalties
project-safe security allowlist
JWT/Bearer/LDAPS safe routing
```

Новые retrieval-компоненты:

```text
scripts/rag_bucket_quality.py
scripts/18_targeted_bucket_eval.py
scripts/19_build_compact_review.py
```

Bucket-driven retrieval:

```text
ФТТ bucket
ЦТА bucket
ПР bucket
СоИ AD/LDAPS bucket
MDR/НСИ/Bearer bucket
guard quality bucket
hallucination bucket
```

## Следующий этап

### Priority 1

```text
Targeted rerun по каждому bucket
```

Команды:

```powershell
python scripts/18_targeted_bucket_eval.py --review data/realistic_500_eval_review.jsonl --bucket ftt_missing
python scripts/18_targeted_bucket_eval.py --review data/realistic_500_eval_review.jsonl --bucket cta_missing
python scripts/18_targeted_bucket_eval.py --review data/realistic_500_eval_review.jsonl --bucket pr_missing
python scripts/18_targeted_bucket_eval.py --review data/realistic_500_eval_review.jsonl --bucket soi_ad_missing
python scripts/18_targeted_bucket_eval.py --review data/realistic_500_eval_review.jsonl --bucket soi_nsi_mdr_bearer
python scripts/18_targeted_bucket_eval.py --review data/realistic_500_eval_review.jsonl --bucket guard_wrong_refuse_allow
```

Expected validation targets:

```text
reduce ftt_missing
reduce soi_ad_missing
reduce pr_missing
reduce cta_missing
reduce soi_nsi_mdr_bearer
reduce guard_wrong_refuse_allow
reduce garbage_source
reduce low_score
```

### Priority 2

```text
Improve retrieval quality by bucket
```

Для каждого bucket:

```text
aliases
anchors
metadata routing
rerank boosts
path routing
chunk overlap tuning
section-aware retrieval
requirement-id routing
source tiering
citation validator
```

FTT retrieval:

```text
prioritize exact requirement ids:
4.1
4.2
4.2.1
4.2.2
4.2.3
4.2.4
4.2.5
4.2.6
4.2.7
4.2.8
4.2.9
4.2.10
4.3
9.6
10.8
```

Implemented in rerank:

```text
exact_ftt_section_matches
ftt_section_hint_matches
ftt_section_boost
FTT path-aware retrieval
```

Implemented hard routing:

```text
source_tier
hard_route_boost
hard_route_penalty
unknown-doc penalties
low-priority penalties
```

Implemented routing expansions:

```text
AD/LDAPS anchors
Bearer/MDR/НСИ anchors
CTA infra anchors
PR business-flow anchors
```

Implemented guard refinement:

```text
project-safe JWT routing
project-safe Bearer routing
project-safe LDAPS routing
safe security lookup separation
harmful abuse separation
```

Source tiering roadmap:

```text
Tier 1:
ФТТ
ПР
ЦТА
СоИ

Tier 2:
ПМИ
ПСИ
Приложения

Tier 3:
transcript
макеты
_analysis
site export

Tier 4:
raw json/api dumps
HAR/network exports
DOM exports
```

### Priority 3

```text
realistic-500 rerun after retrieval fixes
```

Цель:

```text
reduce missing_source
reduce low_score
reduce garbage_source
remove hallucination
increase grounded answered
reduce bad_refusal
```

### Priority 4

```text
stable approved regression corpus
```

Build:

```text
compact labeled review
approved regression set
bucket-specific regression subsets
```

## Long-term ideas

```text
DSPy retrieval optimization
cross-encoder rerank
adaptive chunk retrieval
query decomposition
agentic retrieval
graph retrieval
citation validator
structured answer synthesis
```