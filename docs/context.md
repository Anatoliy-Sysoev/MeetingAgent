# Контекст проекта

Обновлено: 2026-05-22.

## Retrieval quality evolution

После realistic-100 и realistic-500 ручной разметки retrieval quality переведён на bucket-driven pipeline.

Главные failure buckets:

```text
ФТТ не находится
ЦТА не находится
ПР не находится
СоИ AD/LDAPS не находится
MDR/НСИ/Bearer Token ломается
guard ошибочно refuse/allow
hallucination при слабых источниках
```

Для каждого bucket реализуются:

```text
retrieval hints
anchor expansion
lexical aliases
metadata routing
hybrid rerank boost
targeted eval rerun
approved regression set
```

Новый quality-layer:

```text
scripts/rag_bucket_quality.py
```

Назначение:

```text
bucket detection
query expansion by domain
metadata-aware routing
path-aware rerank boosting
bucket diagnostics
failure classification
```

Targeted rerun runner:

```text
scripts/18_targeted_bucket_eval.py
```

Pipeline:

```text
review verdicts
  -> failure buckets
  -> retrieval diagnostics
  -> targeted rerun
  -> rerank tuning
  -> approved regression set
  -> realistic rerun
```

Approved regression set:

```text
approved_regression_set.jsonl
```

Используется как:

```text
stable retrieval baseline
anti-regression corpus
quality smoke set
```

Hybrid retrieval quality v3:

```text
vector retrieval
+ BM25/FTS5 lexical retrieval
+ targeted lexical scan
+ bucket expansion
+ metadata-aware rerank
+ source-quality hard gate
```

Rerank теперь учитывает:

```text
lexical_score
matched_terms
matched_numbers
phrase_matches
bucket_signals
doc_type_match
path boosts
metadata routing
```

Hard source-quality gate:

```text
weak retrieval -> no_answer
weak retrieval -> retrieval_fix_required
```

LLM не должен выдавать answered если:

```text
нет anchor terms
нет section match
нет metadata/doc-type match
низкий lexical score
```

Guard evolution:

```text
harmful security queries -> refused
project security/auth questions -> allowed
```

Примеры allowed:

```text
Bearer Token MDR
JWT/OAuth/OIDC в проекте
LDAPS/AD интеграция
```

Примеры refused:

```text
SQL injection payload
взлом
обход авторизации
эксплойт
```

## GigaAM ASR Experiment 2026-05-25

Локальный GigaAM-путь зафиксирован как reference-документация:

```text
docs/references/GIGAAM_EXPERIMENT.md
```

Фактическая локальная среда:

```text
venv = %LOCALAPPDATA%\MeetingAgent\gigaam-venv312
model = v3_e2e_rnnt
device = cpu
fp16_encoder = false
```

Фактический прогон:

```text
meeting = meetings/2026-05-19__asu-novatek-stroycontrol-gigaam/
chunks_total = 224
chunks_done = 224
errors = []
elapsed_sec_this_run = 1070.2
```

Решение: GigaAM остаётся экспериментальным ASR fallback. Основной MeetingAgent pipeline пока использует `faster-whisper`; для GigaAM нужен отдельный адаптер и benchmark качества.
