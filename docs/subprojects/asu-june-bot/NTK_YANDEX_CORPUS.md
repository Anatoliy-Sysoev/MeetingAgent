# NTK Yandex Corpus

Обновлено: 2026-05-27.

## Назначение

`NTK Yandex Corpus` — отдельный runtime-корпус Project Knowledge Bot по очищенной папке:

```text
C:\Users\Сотрудник\Desktop\Yandex.Disk\Документы НТК Сдача
```

Цель: использовать боевые сдачные файлы НТК как основной источник знаний и возвращать `source_url` на опубликованные файлы Яндекс.Диска там, где ссылка есть в экспорте.

Корпус собирается отдельно от текущего:

```text
data/asu_june_bot_ntk/
```

Текущий стабильный корпус не меняется:

```text
data/asu_june_bot/
```

## Feature Flag

Переключение корпуса теперь делается не правкой кода, а feature flag:

```text
configs/asu_june_bot/corpus.yaml
ASU_JUNE_BOT_ACTIVE_CORPUS=default|ntk
```

Пример для PowerShell:

```powershell
$env:ASU_JUNE_BOT_ACTIVE_CORPUS = "ntk"
.\.venv\Scripts\python.exe scripts\asu_june_bot_health_v2.py --json
```

Ожидаемо health должен вернуть:

```text
corpus=ntk_yandex_corpus
corpus_key=ntk
paths -> data/asu_june_bot_ntk/*
```

## Команды сборки

### 1. Построить source links

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_build_source_links.py `
  --project-root "C:\Users\Сотрудник\Desktop\Yandex.Disk\Документы НТК Сдача" `
  --cloud-links "C:\Users\Сотрудник\Desktop\yandex_disk_full_export\cloud_links_full.csv" `
  --output data\asu_june_bot_ntk\source_links.jsonl
```

### 2. Извлечь текст

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_extract_text_v2.py `
  --project-root "C:\Users\Сотрудник\Desktop\Yandex.Disk\Документы НТК Сдача" `
  --source-links data\asu_june_bot_ntk\source_links.jsonl `
  --output-dir data\asu_june_bot_ntk\extracted_v2 `
  --exclude-dir _Obsidian
```

Для чистой пересборки добавить `--reset`.

### 3. Собрать chunks

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_build_chunks_v2.py `
  --blocks-path data\asu_june_bot_ntk\extracted_v2\blocks.jsonl `
  --output-dir data\asu_june_bot_ntk
```

### 4. Собрать embeddings и vector index

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_build_index_v2.py `
  --chunks-path data\asu_june_bot_ntk\chunks_v2.jsonl `
  --cache-path data\asu_june_bot_ntk\embeddings_cache_v2.jsonl `
  --index-dir data\asu_june_bot_ntk\numpy_index_v2 `
  --report-path data\asu_june_bot_ntk\index_v2_report.json
```

Команда resumable: при повторном запуске уже посчитанные embeddings берутся из `embeddings_cache_v2.jsonl`.

### 5. Watchdog для ночной сборки

```powershell
.\scripts\monitor_asu_june_bot_ntk_index.ps1 -Loop -IntervalMinutes 30
```

Watchdog ничего не удаляет. Он проверяет, есть ли живой процесс `asu_june_bot_build_index_v2.py` для `data\asu_june_bot_ntk`; если процесса нет, а `numpy_index_v2\manifest.json` ещё не создан, запускает resumable build заново.

### 6. Пересобрать Obsidian vault

После готовности `source_links.jsonl` и `chunks_v2.jsonl` можно полностью пересобрать Obsidian-базу знаний:

```powershell
.\.venv\Scripts\python.exe scripts\ntk_obsidian_rebuild.py --clear-vault
```

Скрипт очищает только:

```text
C:\Users\Сотрудник\Desktop\Yandex.Disk\Документы НТК Сдача\_Obsidian
```

Результат:

```text
_Obsidian/00_Главная/Карта проекта ЦП УПКС.md
_Obsidian/01_Реестры/document_registry.csv
_Obsidian/01_Реестры/chunk_quality_report.md
_Obsidian/01_Реестры/relationships_draft.csv
_Obsidian/99_Шаблоны/*
```

Важно: `relationships_draft.csv` является черновым графом; связи по кандидатам требований требуют ручной проверки.

## Smoke-проверка

Вопросы:

```text
docs/quality/ntk_yandex_smoke_questions.jsonl
```

Быстрая retrieval-проверка без LLM:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_ntk_smoke_eval.py `
  --mode bm25 `
  --chunks-path data\asu_june_bot_ntk\chunks_v2.jsonl `
  --index-dir data\asu_june_bot_ntk\numpy_index_v2 `
  --output data\asu_june_bot_ntk\smoke_eval_bm25.jsonl
```

После готовности vector-index:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_ntk_smoke_eval.py `
  --mode hybrid `
  --chunks-path data\asu_june_bot_ntk\chunks_v2.jsonl `
  --index-dir data\asu_june_bot_ntk\numpy_index_v2 `
  --output data\asu_june_bot_ntk\smoke_eval_hybrid.jsonl
```

## Текущий результат 2026-05-27

Source links:

```text
local_files: 1166
cloud_links: 345
matched: 325
missing_source_url: 841
```

Extraction:

```text
candidate_sources_total: 174
sources_extracted_this_run: 171
blocks_extracted_this_run: 31018
errors_this_run: 0
table_row_blocks_this_run: 19400
```

Chunks:

```text
chunks_total: 31270
chunks file: data/asu_june_bot_ntk/chunks_v2.jsonl
source_url_chunk_pct: 93.8
project_doc: 25170
analytical_note: 3551
instruction: 1938
meeting_artifact: 611
```

Chunk quality after Excel/table cleanup:

```text
max_chars: 14358
p95_chars: 987
p99_chars: 2433
gt6000: 57
short_noise_samples: 0 found by review script
```

Main document types:

```text
Справочник НСИ: 9551
ПР: 6072
СоИ Справочники: 3553
ФТТ: 2146
Руководство: 1938
ЦТА: 1859
ПМИ: 1473
Методика/Регламент НСИ: 1438
unknown: 1235
```

Vector index:

```text
index: data/asu_june_bot_ntk/numpy_index_v2
manifest: exists
count: 31270
embedding_model: bge-m3
embedding_dim: 1024
created_at: 2026-05-27T01:57:30Z
```

BM25 smoke:

```text
20 cases
ok: 8
source_url_in_top5: 12
status_counts: ok=12, clarify=7, refused=1
```

Hybrid smoke после расширения project markers и routing:

```text
20 cases
ok: 20
doc_type_hits: 19
status_hits: 1
source_url_in_top5: 19
status_counts: ok=19, refused=1
failed_ids: []
```

После chat-level проверки `NTK-SMOKE-007` smoke был усилен:

```text
для кейса RTO/RPO добавлен `expected_terms_in_top5 = [rto, rpo, время восстановления]`;
это убирает ложное `ok` только по doc_type=ЦТА без recovery anchors.
```

Новый retrieval smoke после фикса `cta_recovery_rto_rpo`:

```text
20 cases
ok: 20
failed_ids: []
NTK-SMOKE-007: ok=true, terms_hit_in_top5=true
NTK-SMOKE-017: ok=true после обновления expectation на `Методика/Регламент НСИ`
```

Manual source-supported review:

```text
total: 20
strict pass: 18/20
partial: 2/20
fail: 0/20
threshold >=18/20: met
```

Артефакты ручной проверки:

```text
docs/quality/ntk_smoke_manual_review_2026-05-27_summary.md
docs/quality/ntk_smoke_manual_review_2026-05-27.csv
docs/quality/ntk_smoke_manual_review_2026-05-27.jsonl
```

Вывод: индекс собран, hybrid smoke технически проходит и ручная source-supported проверка подтверждает корпус на пороге `18/20 strict pass`. Этого достаточно, чтобы включать NTK corpus через feature flag. Безусловным глобальным default корпус пока не становится.

Оставшиеся follow-up кейсы:

```text
NTK-SMOKE-012:
targeted retrieval-fix внесен;
теперь в top-2 появляется chunk с таблицей "Роли / группы AD" и app_ccpm_ul_cc_01/02/03;
нужен повторный ручной review

NTK-SMOKE-017:
targeted retrieval-fix внесен;
запросы про регламенты ведения теперь поднимают Методика/Регламент НСИ в top-1..top-5;
chat-level проверка подтверждает, что это корректный тип документа для вопроса;
expectation smoke обновлен на `Методика/Регламент НСИ`;
hybrid smoke после обновления expectation снова дает `20/20 ok`;
остаточный quality-follow-up: primary source всё ещё выбирается через weak fallback на краткий registry/note chunk, хотя supporting уже содержит полноценные регламентные документы
```

## Realistic-100 manual review 2026-05-28

Пакет ручной проверки закреплен в репозитории:

```text
docs/quality/ntk_realistic_100_new_eval_review_filled.jsonl
docs/quality/ntk_realistic_100_new_eval_review_filled_overview.csv
docs/quality/ntk_realistic_100_new_eval_review_manual_summary.json
docs/quality/ntk_realistic_100_new_eval_review_manual_summary.md
docs/quality/ntk_realistic_100_new_eval_review_action_plan.md
```

Прогон завершен штатно:

```text
review_ready
100/100 rows
active PID: none
statuses: answered=35, no_answer=46, validation_failed=1, clarify=12, refused=6
```

Результат ручной разметки:

```text
total: 100
ok: 34
missing_source: 27
low_score: 23
bad_refusal: 8
needs_clarification: 4
garbage_source: 2
out_of_scope: 2
hallucination: 0
```

Вывод: стабильность eval-runner подтверждена, но quality gate не пройден по retrieval/routing/guard. Главная зона потерь - `missing_source + low_score = 50/100`; project-scope вопросы все еще уходят в `clarify`; out-of-scope guard не всегда переводит фикус/медицину/shopping/Chrome в `refused`.

Приоритет исправлений:

```text
P0 project_scope_clarify_or_sensitive_guard:
NTK100-NEW-071, 073, 077, 079, 080, 085, 086, 090

P1 CTA missing_source:
NTK100-NEW-025, 026, 027, 028

P1 PR missing_source:
NTK100-NEW-014, 016, 019, 020

P1 NSI regulation/reference:
NTK100-NEW-053, 054, 055, 056, 057, 059

P1 Passport:
NTK100-NEW-063, 064, 065

P1 AD/app_ccpm:
NTK100-NEW-036, 039, 040

P2 out_of_scope clarify instead of refused:
NTK100-NEW-093, 094, 095, 096
```

P0 закрыт 2026-05-28:

```text
docs/quality/ntk_realistic_100_new_p0_project_scope_guard_eval_2026-05-28.md

P0 search-level targeted eval: 8/8
071, 073, 077, 079, 080, 085, 086 -> status=ok
090 -> status=refused, retrieval_called=False
guard_v2_eval: 65/65
pytest guard slice: 68 passed
```

P1 CTA закрыт 2026-05-28:

```text
docs/quality/ntk_realistic_100_new_p1_cta_missing_source_eval_2026-05-28.md

hybrid search-level targeted eval: 4/4
chat-level targeted eval: 4/4 answered
pytest retrieval slice: 9 passed
```

P1 PR закрыт 2026-05-28:

```text
docs/quality/ntk_realistic_100_new_p1_pr_missing_source_eval_2026-05-28.md

hybrid search-level targeted eval: 4/4
chat-level targeted eval: 4/4 answered
pytest retrieval slice: 12 passed
```

P1 NSI regulation/reference закрыт 2026-06-02:

```text
docs/quality/ntk_realistic_100_new_p1_nsi_regulation_reference_eval_2026-05-28.md

chat-level targeted eval: 6/6 answered
clarify: 0
parse_errors: 0
pytest NSI/chat slice: 32 passed
compileall src/asu_june_bot: ok
```

Следующий шаг: исправлять оставшиеся P1 bucket-first, начиная с `Passport`, затем `AD/app_ccpm`, отдельным маленьким коммитом на каждый bucket, с targeted eval перед повторным full `NTK realistic-100`.

## Что не сделано

```text
global default switch — не выполнен
feature-flag enablement — можно делать
incremental update для Yandex-папки — следующий этап после закрепления feature flag и follow-up фиксов
```

## Следующая проверка качества

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_ntk_smoke_eval.py `
  --mode hybrid `
  --chunks-path data\asu_june_bot_ntk\chunks_v2.jsonl `
  --index-dir data\asu_june_bot_ntk\numpy_index_v2 `
  --output data\asu_june_bot_ntk\smoke_eval_hybrid.jsonl `
  --summary data\asu_june_bot_ntk\smoke_eval_hybrid_summary.json
```

Не переключать корпус в безусловный global default до закрытия оставшихся P1 buckets `Passport` и `AD/app_ccpm`, а затем повторного full `NTK realistic-100`.
