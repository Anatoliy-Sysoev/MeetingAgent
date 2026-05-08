# Контекст Проекта

Обновлено: 2026-05-08.

## Текущее Состояние

MeetingAgent - приватный GitHub-backed пет-проект и локальный продуктовый репозиторий.

Репозиторий:

- Локальный путь: `%USERPROFILE%\Desktop\AI\MeetingAgent`
- Remote: `https://github.com/Anatoliy-Sysoev/MeetingAgent`
- Видимость: private
- Ветка: `main`

Продуктовое направление: local-first агент памяти проекта.

Основные сценарии:

- RAG по проектной документации;
- транскрибация встреч;
- генерация memo и протоколов;
- классификация по этапу проекта, ФТТ, задаче и документу;
- генерация документов на основе цитируемых проектных источников.

## Рабочий Статус

Основной RAG-corpus локально собран: текущие `data/chunks.jsonl` дают 5153 chunks после исключения архивов, черновиков, backup-файлов и служебных JSON-копий. `data/embeddings_cache.jsonl` содержит валидные `bge-m3` embeddings для всех текущих chunks и сохраняет stale-записи для ранее удаленных/исключенных chunks.

ChromaDB больше не считается стабильным поисковым слоем: локально наблюдалась ошибка загрузки HNSW-индекса. Для критического пути поиска используется отдельный numpy-индекс в `data/numpy_index`.

Важные runtime-факты:

- `run_full_rag.ps1` запускает полную сборку.
- `scripts/03_build_index.py` - долгий шаг создания chunks и пополнения embeddings cache.
- `data/embeddings_cache.jsonl` - resumable cache embeddings.
- `scripts/05_build_numpy_index.py` - сборка стабильного numpy-поиска из готовых chunks и embeddings cache.
- `data/numpy_index` - локальный numpy-индекс, игнорируется Git.
- `monitor_rag.ps1` - один тик мониторинга.
- Локальные рабочие папки игнорируются Git.

## Важные Файлы

- `README.md`: обзор продукта и запуск.
- `AGENTS.md`: инструкции для Codex/AI.
- `docs/context.md`: текущее состояние проекта.
- `docs/decisions.md`: почему приняты ключевые решения.
- `docs/todo.md`: следующие шаги.
- `.env.example`: безопасный пример переменных окружения.
- `config.example.yaml`: безопасный пример локальной конфигурации.
- `scripts/03_build_index.py`: worker для embeddings/indexing.
- `scripts/05_build_numpy_index.py`: сборщик локального numpy-индекса.
- `scripts/04_query.py`: запросы к RAG через numpy-индекс.
- `scripts/06_transcribe_meeting.py`: offline-транскрибация одной папки встречи по `meeting.json`.
- `monitor_rag.ps1`: мониторинг долгой RAG-сборки.
- `docs/product/PROJECT_STAGES_AND_FTT.md`: рабочая карта этапов продукта, ФТТ и критериев приемки.
- `docs/product/PROJECT_TAXONOMY.md`: единый реестр этапов проекта и типов документов.
- `docs/glossary.md`: словарь терминов и заготовка `initial_prompt` для транскрибации.
- `docs/operations/BACKUP_AND_RETENTION.md`: правила backup, восстановления и хранения медиа.
- `docs/quality/rag_eval_questions.md`: стартовый набор вопросов для baseline качества RAG.
- `docs/references/WHISPERDESK_EXPERIMENT.md`: что берем из эксперимента WhisperDesk для live-транскрибации.
- `configs/schemas/meeting.schema.json`: формальная JSON schema карточки встречи `meeting.json`.
- `configs/schemas/meeting.decisions.schema.json`: schema решений встречи.
- `configs/schemas/meeting.tasks.schema.json`: schema задач встречи.
- `configs/schemas/meeting.risks.schema.json`: schema рисков встречи.
- `configs/schemas/meeting.open_questions.schema.json`: schema открытых вопросов встречи.
- `configs/prompts/meeting_memo.md`: prompt-шаблон memo встречи.
- `configs/prompts/meeting_protocol.md`: prompt-шаблон протокола встречи.
- `configs/prompts/meeting_artifacts_json.md`: prompt-шаблон структурированных JSON-артефактов.
- `scripts/07_generate_meeting_artifacts.py`: генератор memo/protocol/JSON-артефактов из готового transcript.
- `docs/templates/MEETING_CARD.md`: человекочитаемый шаблон карточки встречи и структура папки `meetings/YYYY-MM-DD__slug/`.

## Что Изменилось Недавно

- Создана продуктовая структура репозитория.
- Создан и запушен приватный GitHub-репозиторий.
- Локальные рабочие данные исключены из Git.
- Мониторинг усилен для работы с Ollama и живым Python build-процессом.
- В `scripts/03_build_index.py` сохранены reusable `chunk_id` и совместимый `db_id`, но запись в ChromaDB убрана из основного build-пути.
- Добавлены стандартные файлы пет-проекта: `AGENTS.md`, `docs/context.md`, `docs/decisions.md`, `docs/todo.md` и `.env.example`.
- Основная документация переведена на русский язык как основной язык проекта.
- Добавлен подробный продуктовый документ `docs/product/PRODUCT_VISION_AND_PLAN.md`: видение, модули, сценарии, roadmap и адаптация идей Speakr.
- Добавлен план параллельных работ `docs/product/PARALLEL_WORK_WHILE_RAG_BUILDS.md`, чтобы развивать продукт, пока текущая RAG-сборка продолжается.
- Добавлен отдельный стабильный локальный RAG-поиск на numpy: `scripts/rag_numpy_backend.py` и `scripts/05_build_numpy_index.py`.
- `scripts/04_query.py` переведен на numpy-поиск по умолчанию и больше не зависит от ChromaDB для обычного поиска.
- `run_full_rag.ps1` теперь после build/indexing запускает сборку `05_build_numpy_index`.
- Ранний smoke-поиск numpy прошел на корпусе 9575 chunks; после чистки корпуса актуальный индекс пересобран на 5153 chunks.
- `vector_db/` полностью исключен из Git как устаревшая локальная папка ChromaDB, чтобы rebuild не удалял tracked-заглушки.
- `monitor_rag.ps1` получил более устойчивое определение процессов через CIM fallback и lock PID fallback.
- Добавлен документ `docs/product/PROJECT_STAGES_AND_FTT.md`: этапы разработки MeetingAgent, ФТТ продукта, предметные этапы проекта АСУ и ближайший маршрут выполнения.
- Добавлен документ `docs/references/WHISPERDESK_EXPERIMENT.md`: WhisperDesk зафиксирован как экспериментальный референс для live-транскрибации, но не как продуктовый код.
- Добавлены `docs/glossary.md`, `docs/product/PROJECT_TAXONOMY.md`, `docs/operations/BACKUP_AND_RETENTION.md` и `docs/quality/rag_eval_questions.md`.
- `scripts/04_query.py` получил компактный вывод источников, `score` и JSON-обертку для evaluation.
- `scripts/03_build_index.py` больше не пересоздает `vector_db/`; после него `run_full_rag.ps1` собирает numpy-индекс через `scripts/05_build_numpy_index.py`.
- `RAG_AUTOMATION_INSTRUCTION.md` переписан под актуальный numpy-поток и больше не описывает ChromaDB как рабочий путь.
- `config.example.yaml` дополнен настройками генерации и live-транскрибации.
- Добавлен `docs/quality/rag_eval_report_template.md` для исторических срезов качества RAG.
- Выполнен первый baseline-прогон `FTT-MA-07` по 10 вопросам и сохранен в `docs/quality/rag_eval_baseline_2026-05-07.md`.
- В `docs/decisions.md` добавлены решения про контракт вывода `04_query.py` и политику ротации медиа.
- Добавлена гигиена корпуса RAG: `exclude_path_patterns` исключают `Архив`, `Черновики и шаблоны`, backup-папки и служебные `_analysis/docx_json*`, но оставляют curated `_analysis/*.md`.
- `scripts/04_query.py` и numpy backend теперь по умолчанию фильтруют исключенные пути и дедуплицируют одинаковые chunks по тексту; для диагностики есть `--include-excluded` и `--no-dedupe`.
- `run_full_rag.ps1` и `monitor_rag.ps1` настроены на UTF-8 вывод; `monitor_rag.ps1` больше не считает старый done-маркер завершением, если жив текущий wrapper/build.
- После чистки корпуса RAG пересобран: `data/numpy_index` содержит 5153 chunks, свежий done-маркер `full_rag_2026-05-07_17-38-14.done.txt`, failed-маркеров нет.
- Снят новый рабочий baseline `FTT-MA-07` на очищенном корпусе: `docs/quality/rag_eval_baseline_clean_2026-05-07.md`, итог `9 hit / 5 partial / 1 miss`.
- В `docs/product/PROJECT_STAGES_AND_FTT.md` уточнено, что `FTT-MA-15` должен корректно обрабатывать deletion: удаленные или исключенные документы не попадают в актуальный numpy-индекс, даже если embeddings остаются в cache.
- `docs/quality/rag_eval_report_template.md` актуализирован под новый стандарт baseline: Git snapshot, hash chunks, cache stats, backend поиска, raw-log, правила `hit/partial/miss`, тип запроса и метрики дублей.
- Начат `FTT-MA-09`: добавлена формальная схема `configs/schemas/meeting.schema.json`, обновлен `docs/templates/MEETING_CARD.md`, зафиксирована структура папки встречи `meetings/YYYY-MM-DD__slug/`.
- В `docs/decisions.md` добавлены решения про slug-идентификатор встречи, роль `meeting.json` как машинного контракта, а также фиксацию retention и RAG-политики внутри карточки встречи.
- `docs/operations/MEETING_PIPELINE.md`, `docs/architecture/FOLDER_STRUCTURE.md` и `docs/product/PROJECT_STAGES_AND_FTT.md` синхронизированы с новым контрактом карточки встречи.
- Уточнено, что `meeting.json` версии `1` меняется только через явную миграцию, Markdown-карточка является представлением JSON-артефактов, а проверки, зависящие от статуса, выполняются pipeline, а не JSON schema.
- Начат минимальный `FTT-MA-08`: добавлен `scripts/06_transcribe_meeting.py` для offline-транскрибации одной встречи из папки `meetings/YYYY-MM-DD__slug/`.
- В `configs/schemas/meeting.schema.json` добавлено необязательное поле `last_error` для failure-safe состояния `failed`.
- Создана локальная тестовая карточка `meetings/2026-05-08__test-meeting/`; исходное видео скопировано в `source/` и игнорируется Git.
- `--dry-run` на тестовой карточке прошел: schema валидна, `ffmpeg` найден, `faster-whisper` модель `small/int8` доступна.
- Реальная offline-транскрибация тестовой записи выполнена: `processing_status = transcribed`, создано 398 segments, `transcript/transcript.md` и `transcript/segments.jsonl` лежат локально и игнорируются Git.
- Runtime `meetings/**/meeting.json` больше не должен коммититься: пример `new`-карточки перенесен в `docs/examples/meeting.new.example.json`, а реальные карточки встреч остаются локальными рабочими данными.
- Сравнены `faster-whisper` модели `small` и `large-v3-turbo` на тестовой записи: `small/int8` быстрее и подходит для черновика/live, `large-v3-turbo/int8` заметно лучше для финальной offline-транскрибации, но на CPU идет примерно в реальном времени.
- Проведен отдельный эксперимент WhisperX: создан Python 3.12 venv вне репозитория, WhisperX запущен на тестовой записи без diarization, результаты и выводы зафиксированы в `docs/references/WHISPERX_EXPERIMENT.md`.
- Начат `FTT-MA-12`: добавлены prompt-шаблоны для memo, протокола и структурированных JSON-артефактов, а также JSON-схемы `decisions`, `tasks`, `risks`, `open_questions`.
- Добавлен `scripts/07_generate_meeting_artifacts.py`: быстрый `extractive`-режим прошел на тестовой встрече и создал валидные `memo.md`, `protocol.md`, `decisions.json`, `tasks.json`, `risks.json`, `open_questions.json`; карточка встречи перешла в `processing_status = summarized`.
- Экспериментальный `--mode ollama` на Qwen3 пока слишком медленный для длинного transcript на CPU и не считается обязательным путем MVP.
- После ручной проверки результата `extractive` признан скаффолдом контракта, а не готовым продуктовым генератором: он выбирает фразы по ключевым словам и может путать решения, задачи, риски и вопросы.
- Целевой production-путь `FTT-MA-12` зафиксирован как `MAP -> REDUCE -> RENDER` в `docs/architecture/MEETING_ARTIFACTS_PIPELINE.md`; добавлены prompt-файлы `meeting_map_extract.md`, `meeting_reduce_artifacts.md`, `meeting_render_documents.md` и режим `--mode ollama-map-reduce`.
- Внешний документ `deep-research-report (1).md` подтверждает текущие архитектурные решения по meeting pipeline: map-reduce вместо full-context, `faster-whisper` для CPU/local-first, pyannote 3.1 как будущий diarization path, карточку встречи как папку с `meeting.json` и обязательные `source_refs`.
- По итогам внешнего исследования явно не берем в MVP мультиагентные оркестраторы, cloud ASR/meeting-сервисы, DeepEval/RAGAS как обязательный framework и маркетинговые метрики без собственного замера.

## Что Осталось

- Принять порог приемки `FTT-MA-07` на основе нового baseline `9 hit / 5 partial / 1 miss`.
- Ввести или спроектировать метаданные `source_type`: `project_doc`, `system_export`, `analytical_note`, `instruction`.
- Проверить, достаточно ли полно индексируются ПМИ-документы и почему ПМИ плохо поднимается в top-k.
- Для aggregation-вопросов попробовать многоэтапный retrieval: сначала определить типы документов, затем искать внутри каждого типа.
- Использовать `docs/product/PROJECT_STAGES_AND_FTT.md` как основной рабочий чек-лист.
- Проверить качество первого transcript: акронимы ФТТ/ПМИ/ЦТА, таймкоды, абзацы, ошибки распознавания.
- На основе первого transcript и сравнения моделей решить, как запускать финальный offline-профиль: `small` для быстрого черновика, `large-v3-turbo` для важных встреч или отдельный `--quality-profile`.
- WhisperX пока не включать в основной pipeline: он полезен для word-level alignment, но в текущем CPU/Windows-профиле медленнее и сложнее, чем `large-v3-turbo`.
- Использовать extractive-артефакты только как черновик для проверки контракта, не как готовый memo/protocol.
- Следующий шаг по `FTT-MA-12`: прогнать `ollama-map-reduce` на одном окне transcript, сравнить `qwen2.5:7b-instruct` и `mistral:7b-instruct`, оценить валидность JSON и качество классификации.
- Для будущей оценки LLM-режима добавить source-grounding метрику: целевой уровень менее 5% пунктов без надежной привязки к transcript/source_refs.
- После проверки offline-транскрибации перейти к следующему шагу `FTT-MA-08`: watcher и загрузка новых записей из `watched_folder/`.
- Затем проектировать live-сессию вокруг `FTT-MA-10` и `FTT-MA-11`.
- Добавить инкрементальное обновление RAG.
- Собрать первый pipeline обработки встреч.
- Опционально подключить FAISS как ускорение поверх того же контракта поиска, если понадобится скорость на большем корпусе.

## Восстановление Контекста В Новом Треде

Используй prompt:

```text
Прочитай README.md, AGENTS.md, docs/context.md, docs/todo.md и git log --oneline -10. Восстанови контекст проекта и предложи следующий шаг.
```
