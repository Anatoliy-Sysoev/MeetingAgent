# TODO

Обновлено: 2026-05-28.

## Сейчас: NTK realistic-100 P1 retrieval fixes

Прогон, ручная разметка, P0 guard/routing bucket, P1 CTA bucket и P1 PR bucket завершены.

```text
docs/quality/ntk_realistic_100_new_queries.jsonl
docs/quality/ntk_realistic_100_new_eval_review_filled.jsonl
docs/quality/ntk_realistic_100_new_eval_review_filled_overview.csv
docs/quality/ntk_realistic_100_new_eval_review_manual_summary.json
docs/quality/ntk_realistic_100_new_eval_review_manual_summary.md
docs/quality/ntk_realistic_100_new_p0_project_scope_guard_eval_2026-05-28.md
docs/quality/ntk_realistic_100_new_p1_cta_missing_source_eval_2026-05-28.md
docs/quality/ntk_realistic_100_new_p1_pr_missing_source_eval_2026-05-28.md
```

Review summary:

```text
ok: 34
missing_source: 27
low_score: 23
bad_refusal: 8
needs_clarification: 4
garbage_source: 2
out_of_scope: 2
hallucination: 0
```

P0 закрыт:

```text
project_scope_clarify_or_sensitive_guard:
  NTK100-NEW-071, 073, 077, 079, 080, 085, 086 -> status=ok
  NTK100-NEW-090 -> status=refused, retrieval_called=False
guard_v2_eval: 65/65
pytest guard slice: 68 passed
```

P1 CTA закрыт:

```text
CTA missing_source:
  NTK100-NEW-025, 026, 027, 028 -> hybrid search-level 4/4
  chat-level targeted eval -> 4/4 answered
  pytest retrieval slice -> 9 passed
```

P1 PR закрыт:

```text
PR missing_source:
  NTK100-NEW-014, 016, 019, 020 -> hybrid search-level 4/4
  chat-level targeted eval -> 4/4 answered, validation_errors=[]
  pytest retrieval slice -> 12 passed
```

Следующие правки делать bucket-first, не смешивая всё в один коммит:

```text
P1 retrieval:
  NSI regulation/reference:
    NTK100-NEW-053, 054, 055, 056, 057, 059
  Passport:
    NTK100-NEW-063, 064, 065
  AD/app_ccpm:
    NTK100-NEW-036, 039, 040

P2 guard polish:
  out_of_scope clarify instead of refused:
    NTK100-NEW-093, 094, 095, 096
```

Definition of done для каждого bucket:

```text
1. Воспроизвести bucket на текущем main.
2. Внести точечный routing/guard/retrieval fix.
3. Запустить targeted bucket eval.
4. Запустить полный NTK realistic-100 после серии P0/P1 правок.
5. Обновить docs/quality summary и docs/todo.md.
```

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
```

Новые retrieval-компоненты:

```text
scripts/rag_bucket_quality.py
scripts/18_targeted_bucket_eval.py
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

### Obsidian vault по NTK Yandex

Готово:

```text
scripts/ntk_obsidian_rebuild.py
_Obsidian пересобран полностью
document_registry.csv создан
chunk_quality_report.md создан
relationships_draft.csv создан
00_Главная/Карта проекта ЦП УПКС.md создана
шаблоны документа/требования/замечания/ADR созданы
Obsidian sync/publish отключены
broken wikilinks = 0
```

Следующие шаги:

```text
1. Открыть vault в Obsidian и проверить главную страницу.
2. Ручно пройти ключевые связи по ФТТ, ЦТА, ПР, СоИ, ПМИ и ПСИ.
3. Отфильтровать requirement candidates: убрать версии/номера разделов, оставить реальные требования.
4. Заполнить вручную первые ADR и замечания по самым важным открытым вопросам.
5. При изменении Yandex-папки пересобирать chunks/source_links и снова запускать ntk_obsidian_rebuild.py.
```

### Priority 0

```text
NTK Yandex corpus после chunk-quality фиксов пересобран:
- extracted_v2 готов;
- chunks_v2.jsonl: 31270 chunks;
- numpy_index_v2/manifest.json создан;
- BM25 smoke: 8/20 ok;
- hybrid smoke после расширения project markers/routing: 20/20 ok.
```

Ручная проверка hybrid smoke была выполнена на retrieval-level grounding:

```text
strict source-supported pass: 18/20
partial: 2/20
fail: 0/20
```

Важное уточнение после chat-level проверки через LLM:

```text
NTK-SMOKE-007 / RTO-RPO — false positive на уровне smoke/retrieval.

Команда:
.\.venv\Scripts\python.exe scripts\asu_june_bot_chat.py "Что указано в ЦТА про RTO и RPO?"

Фактический результат:
LLM корректно ответил, что в переданных источниках данных недостаточно.
В контекст попали фрагменты ЦТА про Grafana Loki / SIEM / HTTPS / порт 443,
но не фрагменты про RTO, RPO, восстановление или резервное копирование.

Вывод:
- LLM не галлюцинирует и корректно отказывается отвечать без источников;
- проблема находится в retrieval/routing;
- текущий smoke 20/20 был слишком мягким, потому что засчитывал doc_type=ЦТА,
  но не проверял наличие RTO/RPO anchors в найденных источниках.
```

Feature flag уже добавлен:

```text
configs/asu_june_bot/corpus.yaml
ASU_JUNE_BOT_ACTIVE_CORPUS=default|ntk
```

Follow-up кейсы:

```text
NTK-SMOKE-007:
- закрыт;
- отдельный intent `cta_recovery_rto_rpo` добавлен;
- chat-level `asu_june_bot_chat.py` по запросу "Что указано в ЦТА про RTO и RPO?" теперь поднимает recovery chunks с RTO=4 часа и RPO=4 часа;
- в smoke добавлен `expected_terms_in_top5`, чтобы этот кейс больше не проходил только по doc_type=ЦТА.

NTK-SMOKE-012:
- внесен targeted retrieval-fix;
- повторно проверить вручную, достаточно ли top-2 с chunk "Роли / группы AD" и app_ccpm_ul_cc_01/02/03.

NTK-SMOKE-017:
- expectation обновлен на `Методика/Регламент НСИ`;
- retrieval/chat-level проверка подтверждает, что это корректный тип документа для вопроса про регламенты ведения;
- отдельный residual risk: primary source пока выбирается через weak fallback на короткий registry/note chunk, хотя supporting sources содержат полноценные регламентные документы;
- smoke после обновления expectation снова дает `20/20 ok`;
- следующий шаг по качеству: поднять полноценный регламентный doc chunk в primary без weak fallback
```

Incremental update для Yandex-папки делать после подтверждения качества нового корпуса.

### Priority 0.1

Пересобрать NTK corpus после chunk-quality фиксов:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_extract_text_v2.py `
  --project-root "$env:USERPROFILE\Desktop\Yandex.Disk\Документы НТК Сдача" `
  --source-links data\asu_june_bot_ntk\source_links.jsonl `
  --output-dir data\asu_june_bot_ntk\extracted_v2 `
  --reset

.\.venv\Scripts\python.exe scripts\asu_june_bot_build_chunks_v2.py `
  --blocks-path data\asu_june_bot_ntk\extracted_v2\blocks.jsonl `
  --output-dir data\asu_june_bot_ntk
```

После пересборки проверить:

```text
gt6000 должен резко снизиться;
lt80 должен снизиться за счёт удаления микрошума;
unknown document_type должен снизиться;
source_url coverage не должен ухудшиться;
4 СВОК РД.xlsx не должен создавать 100k+ chunks.
Excel-листы с шириной >120 колонок должны попадать в stderr warning,
а после hard cap 250 не должны раздувать embedding text.
```

Не делать пока без отдельного решения:

```text
hardcoded fallback source_url;
канонизация версий ПР как единственный режим;
удаление всех WIP/pptx из корпуса.
```

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

## GigaAM / ASR Backlog

```text
При следующем ручном GigaAM-прогоне использовать scripts/run_gigaam_transcribe.ps1,
а не inline-команды из чата.

Если GigaAM станет постоянным ASR-путем, добавить интеграцию с meeting card:
source/media_files -> transcript/segments.jsonl -> meeting.json status.

Проверить качество GigaAM против faster-whisper на 2-3 русскоязычных встречах:
термины проекта, обрывы на чанках, шум, имена, пригодность для source_refs.

Не коммитить runtime output из Downloads или meetings/**/transcript;
для Git фиксировать только отчет в docs/references или curated transcript excerpt.
```

## MeetingAgent MVP Pipeline

```text
Принят roadmap от ingest записи до meeting search:
docs/meeting_agent_architecture.md
docs/meeting_agent_mvp_scope.md

Основной checklist ФТТ обновлен:
docs/product/PROJECT_STAGES_AND_FTT.md
```

### Priority 0

```text
Реализовать scripts/20_ingest_meeting.py:
- вход mp4/mp3/wav/m4a;
- создание meetings/<meeting_id>/;
- meeting_id как YYYY-MM-DD__slug;
- копирование raw/source файла;
- meeting.json по configs/schemas/meeting.schema.json;
```

## MeetingAgent next steps на 2026-05-27

Сделано:

```text
scripts/32_index_meeting_artifacts.py реализован;
decisions/tasks/risks/open_questions экспортируются как отдельные source_type:
  meeting_decision
  meeting_action_item
  meeting_risk
  meeting_open_question
31_meeting_search.py ищет по structured source types и приоритизирует их для вопросов про решения/задачи/риски/вопросы;
source_policy и asu_june_bot_build_index_v2.py разрешают structured meeting source types по умолчанию;
на 2026-05-26__support-scheme meeting index пересобран: 17 rows, 17 embeddings.
```

Осталось:

```text
подключить meeting search к API/боту;
добавить regression questions для meeting_decision/meeting_action_item/meeting_risk/meeting_open_question;
улучшить качество LLM extraction и REDUCE timeout;
добавить speaker mapping/diarization;
после стабилизации JSON-артефактов сделать DOCX export протокола.
```

Текущая проблема:

```text
локальный LLM REDUCE на CPU нестабилен и может уходить в timeout;
fallback делает pipeline рабочим, но качество decisions/tasks/risks/open_questions требует review;
runtime artifacts в meetings/ и data/meeting_* ignored, в Git хранится код и воспроизводимая документация.
```

## Transcription Productization

### Готово

```text
Этап 1: общий transcription contract module:
- CanonicalSegment / TranscriptDocument / TranscriptionReport;
- normalize_segments для raw backend output;
- генерация segment_id и segment_index;
- фильтр пустых и invalid segments;
- сортировка по времени;
- exporters TXT/MD/SRT/VTT/JSON/JSONL;
- transcription report counters/warnings;
- unit tests.
```

### Готово в Этапе 2

```text
scripts/22_transcribe_meeting.py реализован как официальный entrypoint:
- --engine faster-whisper;
- --engine gigaam;
- --engine from-segments --segments-path ...;
- --model;
- --language ru;
- --compute-type int8;
- --force;
- --resume;
- --dry-run;
- --output-formats txt,md,srt,vtt,json,jsonl;
- запись transcript/transcription_report.json;
- обновление meeting.json artifacts/status;
- отказ от перезаписи готового transcript без --force.

scripts/06_transcribe_meeting.py не удалять: его импортирует scripts/08_process_meeting_pipeline.py.
```

### Следующий шаг

```text
Этап 3: усилить faster-whisper backend:
- выбор source/audio_16k_mono.wav уже есть;
- добавить smoke/dry-run проверку модели в 22;
- сохранить avg_logprob/no_speech_prob, если backend возвращает эти поля;
- проверить реальный прогон на маленьком аудио;
- обновить 06_transcribe_meeting.py до thin wrapper только после отвязки 08_process_meeting_pipeline.py от его внутренних функций.
```
