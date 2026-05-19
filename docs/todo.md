# Список Задач

Обновлено: 2026-05-19.

## Сейчас

- Использовать numpy-поиск как основной стабильный локальный RAG-поиск.
- Использовать `scripts/09_chat.py` как текущий prototype Project-Only Chatbot MVP: ответ только по источникам проекта или корректный отказ.
- Использовать `docs/quality/QUERY_FEEDBACK_LOOP.md` как основной регламент накопления датасета запросов: логировать → просматривать → размечать → корректировать.
- Использовать `docs/quality/DATASET_PIPELINE_STATUS.md` как статус реализованного dataset pipeline.
- Использовать `docs/quality/synthetic_seed_queries.jsonl` как стартовый synthetic smoke/regression corpus.
- Использовать `scripts/10_review_queries.py` для подготовки `data/query_log_review.jsonl` из `data/query_log.jsonl`.
- Использовать `scripts/11_run_synthetic_seed.py` для прогона synthetic seed через `scripts/04_query.py`.
- Использовать `scripts/12_analyze_seed_report.py` для построения `data/synthetic_seed_summary.md`.
- Использовать `scripts/13_build_eval_candidates.py` для подготовки `data/eval_candidates.jsonl` из ручной review-разметки.
- Не считать synthetic seed и eval candidates утверждённым eval без ручного review.
- Не дообучать веса LLM; текущий подход — ручной active-learning поверх RAG через корпус, exclude-правила, retrieval-параметры и regression-кейсы.

## Ближайшие Практические Шаги

1. Подтянуть ветку `claude/model-training-guide-CAfwU` локально.
2. Проверить синтаксис новых скриптов:

```powershell
.\.venv\Scripts\python.exe -m py_compile scripts\10_review_queries.py scripts\11_run_synthetic_seed.py scripts\12_analyze_seed_report.py scripts\13_build_eval_candidates.py
```

3. Прогнать небольшой retrieval smoke на synthetic seed:

```powershell
.\.venv\Scripts\python.exe scripts\11_run_synthetic_seed.py --limit 20
.\.venv\Scripts\python.exe scripts\12_analyze_seed_report.py
```

4. Открыть `data/synthetic_seed_summary.md` и проверить:

- failed rows;
- запросы без sources;
- low top score;
- часто возвращаемые мусорные источники.

5. Накопить первые реальные запросы через `scripts/04_query.py` и `scripts/09_chat.py`.
6. Подготовить review-срез:

```powershell
.\.venv\Scripts\python.exe scripts\10_review_queries.py --limit 100
```

7. Вручную разметить `data/query_log_review.jsonl` verdict-ами:

- `ok`;
- `missing_source`;
- `garbage_source`;
- `low_score`;
- `hallucination`;
- `out_of_scope`.

8. Собрать кандидатов:

```powershell
.\.venv\Scripts\python.exe scripts\13_build_eval_candidates.py
```

9. После ручного approval перенести часть candidates в постоянный regression/eval corpus.

## Далее

- Разобрать слабые вопросы baseline: ПМИ, инфраструктурные ограничения, архитектурные aggregation-запросы.
- Проверить полноту индексации ПМИ: какие ПМИ-файлы реально попали в `chunks.jsonl`, сколько у них chunks и почему они ниже ФТТ в выдаче.
- Проверить проблемные вопросы с `--no-dedupe`, чтобы понять, не скрыла ли дедупликация дополнительные подтверждающие источники.
- Подобрать `--score-threshold` для project-only отказов на smoke-наборе.
- Зафиксировать baseline project-only chatbot: проектные вопросы, внепроектные вопросы, threshold, модель, время ответа, качество источников, timeout и `llm_empty_response`.
- Ввести или спроектировать метаданные `source_type`: `project_doc`, `system_export`, `analytical_note`, `instruction`.
- Для aggregation-вопросов попробовать многоэтапный retrieval: сначала определить типы документов, затем искать внутри каждого типа.
- Оценить, нужен ли BM25-гибрид или метаданные-фильтры, если системные HTML/TXT-экспорты продолжают вытеснять проектные документы в top-k.
- Вынести CLI-логику project-only чат-бота в local API `/chat` только после успешного smoke-прогона и стабилизации project-only guardrail.

## Meeting Pipeline

- Использовать `configs/schemas/meeting.schema.json` как контракт `FTT-MA-09` для всех будущих обработчиков встреч.
- Использовать `scripts/06_transcribe_meeting.py` как минимальный offline CLI для одной встречи.
- Использовать `scripts/08_process_meeting_pipeline.py` как первый оконный offline-pipeline для готовой записи: ASR по окнам, MAP по готовым окнам, затем REDUCE/RENDER.
- Проверить качество первого transcript: акронимы ФТТ/ПМИ/ЦТА, таймкоды, разбиение на абзацы, шумные места.
- Учитывать результат сравнения моделей: `small/int8` для быстрого черновика и live MVP, `large-v3-turbo/int8` для финальной offline-транскрибации важных встреч.
- WhisperX оставить как эксперимент для word-level alignment/diarization, не включать в основной MVP pipeline.

## Позже

- Добавить инкрементальный `update_rag.ps1` для новых, измененных и удаленных документов.
- В `update_rag.ps1` обязательно обработать deletion: удаленные и попавшие под `exclude_path_patterns` документы должны исчезать из актуального индекса.
- Добавить watcher/скрипт загрузки встреч из `watched_folder/` поверх уже готового `06_transcribe_meeting.py`.
- Добавить локальный web UI.
- Добавить DOCX export через `python-docx` или `docxtpl`, когда протоколы нужно будет отдавать заказчику как финальные документы.
- Рассмотреть hybrid retrieval: BM25 + vector + reranker, если корпус вырастет примерно до 50k+ chunks или numpy/vector-only начнет стабильно промахиваться.
- Рассмотреть FAISS поверх того же формата metadata, если numpy станет медленным на большем корпусе.
- Рассмотреть pyannote 3.1 как основной путь diarization, когда появится потребность в speaker timeline.

## Что Не Делать Сейчас

- Не делать fine-tuning LLM на `query_log.jsonl`.
- Не переносить автоматически плохие ответы в eval.
- Не считать synthetic seed golden dataset.
- Не коммитить runtime-данные из `data/`.
- Не подключать DSPy/LangGraph/Dify до стабилизации базового project-only RAG.
- Не делать Docker до завершения локального smoke и стабилизации минимального runtime.

## Известные Риски

- Полная RAG-сборка долгая и зависит от стабильности Ollama.
- ChromaDB локально нестабилен на загрузке HNSW-индекса, поэтому не должен быть критической зависимостью для поиска.
- В выдаче может оставаться шум от похожих HTML/TXT-экспортов системы; точные дубли уже дедуплицируются по тексту.
- Новый baseline `docs/quality/rag_eval_baseline_clean_2026-05-07.md` показал, что поиск по ПМИ и архитектурным сборным запросам требует улучшения.
- Project-only отказ по одному `score_threshold` может быть слишком мягким или слишком жестким.
- `qwen3:8b` на CPU может быть слишком медленным для интерактивного чата при большом prompt.
- `qwen3:4b` может вернуть пустой `response` без HTTP-ошибки; такой случай должен считаться отказом `llm_empty_response`, а не успешным ответом.

## Восстановление Контекста

```text
Прочитай README.md, AGENTS.md, docs/context.md, docs/todo.md, docs/quality/QUERY_FEEDBACK_LOOP.md, docs/quality/DATASET_PIPELINE_STATUS.md и git log --oneline -10. Восстанови контекст проекта и предложи следующий практический шаг.
```
