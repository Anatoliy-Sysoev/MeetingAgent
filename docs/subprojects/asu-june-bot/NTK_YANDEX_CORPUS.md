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

Hybrid smoke:

```text
first 2 cases: ok=True
case 3: stopped by Ollama embedding timeout, read timeout 120s
output file was not produced
```

Вывод: индекс собран, но качество пока не подтверждено для переключения дефолта. BM25-only результат недостаточен, а hybrid smoke нужно повторить после перезапуска или стабилизации Ollama.

## Что не сделано

```text
hybrid smoke — повторить после стабилизации Ollama
default bot corpus switch — не выполнен
incremental update для Yandex-папки — следующий этап после подтверждения качества
```

## Следующая проверка

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_ntk_smoke_eval.py `
  --mode hybrid `
  --chunks-path data\asu_june_bot_ntk\chunks_v2.jsonl `
  --index-dir data\asu_june_bot_ntk\numpy_index_v2 `
  --output data\asu_june_bot_ntk\smoke_eval_hybrid.jsonl `
  --summary data\asu_june_bot_ntk\smoke_eval_hybrid_summary.json
```

Если hybrid smoke не проходит из-за timeout Ollama, сначала перезапустить Ollama и проверить `/api/embeddings` на коротком запросе. Не переключать дефолтный корпус до успешного smoke.
