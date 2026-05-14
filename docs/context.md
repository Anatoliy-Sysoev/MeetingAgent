# Контекст Проекта

Обновлено: 2026-05-14.

## Текущее Состояние

MeetingAgent — приватный GitHub-backed пет-проект и локальный продуктовый репозиторий.

Репозиторий:

- Локальный путь: `%USERPROFILE%\Desktop\AI\MeetingAgent`
- Remote: `https://github.com/Anatoliy-Sysoev/MeetingAgent`
- Видимость: private
- Основная рабочая ветка подпроекта: `docs/asu-june-bot-subproject`

Продуктовое направление: local-first агент памяти проекта.

Основные сценарии:

- RAG по проектной документации;
- транскрибация встреч;
- генерация memo и протоколов;
- очищенный чат-бот только по проектным источникам;
- классификация по этапу проекта, ФТТ, задаче и документу;
- генерация документов на основе цитируемых проектных источников.

## Подпроекты

### Asu June Bot

`Asu June Bot` выделен как отдельный подпроект для локального AI-агента по проекту ЦП УПКС.

Цель подпроекта: сделать проектного ассистента системного аналитика, который отвечает только по загруженной документации ЦП УПКС, анализирует ФТТ, ЦТА, ПР, СоИ, ПМИ, Паспорт ИС, протоколы встреч и возвращает ответы с проверяемыми источниками.

Документация подпроекта находится в `docs/subprojects/asu-june-bot/`:

- `README.md` — обзор подпроекта;
- `context.md` — текущий контекст;
- `decisions.md` — архитектурные решения;
- `architecture.md` — целевая архитектура;
- `mvp.md` — состав локального MVP;
- `roadmap.md` — этапы развития;
- `todo.md` — ближайшие задачи;
- `eval_questions.md` — проверочные вопросы;
- `RUNBOOK_V2.md` — запуск extraction/chunking/index/search v2.1;
- `search_smoke_report_2026-05-14.md` — последний smoke-отчет search v2.1.

Важное решение: текущий `scripts/09_chat.py` остается prototype project-only чата. Новую реализацию Asu June Bot нужно делать модульно, без дальнейшего раздувания одного CLI-скрипта.

## Актуальный Статус Asu June Bot v2.1

Asu June Bot v2.1 технически собран до уровня локального Search MVP.

Готово:

```text
apply_config_v2_1 -> extract_text_v2 -> chunks_v2 -> audit_sources_v2 -> build_index_v2 -> health_v2 -> search_v2
```

Корпус v2.1:

```text
documents = 213
blocks = 31076
chunks_v2 = 31302
indexed_chunks = 31285
skipped_code_chunks = 17
embedding_model = bge-m3
embedding_dim = 1024
```

Health v2:

```text
status = ok
vector_ready = true
bm25_ready = true
ollama_available = true
embedding_model_installed = true
```

Из основного корпуса исключены:

```text
Система
asu_docs_export
asu_admin_export
site_review_runs
playwright
exports
.har
временные файлы
медиа/архивы
```

Старый RAG MeetingAgent остается v1/baseline и не должен смешиваться с v2.1:

```text
data/chunks.jsonl
data/embeddings_cache.jsonl
data/numpy_index/
```

Новый runtime Asu June Bot:

```text
data/asu_june_bot/chunks_v2.jsonl
data/asu_june_bot/embeddings_cache_v2.jsonl
data/asu_june_bot/numpy_index_v2/
```

## Последний Search Smoke v2.1

Результаты зафиксированы в:

```text
docs/subprojects/asu-june-bot/search_smoke_report_2026-05-14.md
```

Итог:

- `Какие интеграции заявлены в проекте?` — retrieval достаточен для API Search MVP: поднимаются ЦТА, Паспорт ИС, ФТТ, ПР и wiki-summary.
- `ФТТ 4.2.5 НОВАДОК ЭЦП` — retrieval практически пригоден: ФТТ поднимается в top-1/top-2, есть строка `ЦП УПКС -> НОВАДОК`, но metadata `section/requirement_id` шумит.
- `Что входит в Паспорт ИС?` — BM25 top-1/top-2 корректный, hybrid top-1 корректный, но дальше есть vector-only noise: ПР, таблицы ПО, поддержка.

Вывод: нельзя переходить напрямую к Chat MVP от raw hybrid top-k. Нужен этап Search Quality v2.2.

## Ближайшая Цель Asu June Bot

Перед API Search выполнить Search Quality v2.2:

```text
query_intent -> post_rerank -> context_builder -> diagnostics -> smoke_report
```

Минимальные новые компоненты:

```text
src/asu_june_bot/retrieval/query_intent.py
src/asu_june_bot/retrieval/post_rerank.py
src/asu_june_bot/retrieval/context_builder.py
```

Цель v2.2:

- определять `query_intent`;
- не отправлять LLM весь raw hybrid top-k;
- выделять `primary_sources` и `supporting_sources`;
- фильтровать software/support/glossary/front matter noise для overview-запросов;
- усиливать exact requirement/document type;
- возвращать diagnostics в JSON search output.

К API `/search` переходить только после успешного Search Quality v2.2.

К Chat MVP переходить только после API Search.

## Текущий RAG v1 / Project-Only Chat Prototype

Основной RAG v1 локально собран: текущие `data/chunks.jsonl` дают 5153 chunks после исключения архивов, черновиков, backup-файлов и служебных JSON-копий. `data/embeddings_cache.jsonl` содержит валидные `bge-m3` embeddings для всех текущих chunks и сохраняет stale-записи для ранее удаленных/исключенных chunks.

ChromaDB больше не считается стабильным поисковым слоем: локально наблюдалась ошибка загрузки HNSW-индекса. Для критического пути поиска используется отдельный numpy-индекс в `data/numpy_index`.

Project-Only Chatbot prototype начат как узкий CLI поверх текущего numpy-RAG:

- `scripts/09_chat.py` выполняет retrieval, фильтрует источники по `score_threshold`, отказывает без источников и только после этого вызывает локальную LLM;
- `configs/prompts/project_only_chat.md` задает project-only политику ответа и включает `/no_think` для Qwen;
- `docs/quality/project_only_chatbot_smoke_questions.md` содержит smoke-набор проектных и внепроектных вопросов.

Важно: `scripts/09_chat.py` не развивать как основной runtime Asu June Bot. Он остается prototype.

## Важные Runtime-Факты

- `run_full_rag.ps1` запускает полную сборку v1.
- `scripts/03_build_index.py` — долгий шаг создания v1 chunks и пополнения embeddings cache.
- `data/embeddings_cache.jsonl` — resumable cache embeddings v1.
- `scripts/05_build_numpy_index.py` — сборка стабильного numpy-поиска v1.
- `data/numpy_index` — локальный numpy-индекс v1, игнорируется Git.
- `scripts/asu_june_bot_build_index_v2.py` — сборка embeddings/index v2.
- `data/asu_june_bot/embeddings_cache_v2.jsonl` — resumable cache embeddings v2.
- `data/asu_june_bot/numpy_index_v2` — локальный numpy-индекс v2, игнорируется Git.
- `scripts/asu_june_bot_health_v2.py` — единая проверка готовности v2.
- `scripts/asu_june_bot_search_v2.py` — CLI search v2.
- Локальные рабочие папки игнорируются Git.

## Важные Файлы

- `README.md`: обзор продукта и запуск.
- `AGENTS.md`: инструкции для Codex/AI.
- `docs/context.md`: текущее состояние проекта.
- `docs/decisions.md`: почему приняты ключевые решения.
- `docs/todo.md`: следующие шаги.
- `docs/subprojects/asu-june-bot/README.md`: обзор подпроекта Asu June Bot.
- `docs/subprojects/asu-june-bot/context.md`: контекст подпроекта Asu June Bot.
- `docs/subprojects/asu-june-bot/decisions.md`: решения подпроекта Asu June Bot.
- `docs/subprojects/asu-june-bot/architecture.md`: архитектура подпроекта Asu June Bot.
- `docs/subprojects/asu-june-bot/mvp.md`: MVP подпроекта Asu June Bot.
- `docs/subprojects/asu-june-bot/roadmap.md`: roadmap подпроекта Asu June Bot.
- `docs/subprojects/asu-june-bot/todo.md`: todo подпроекта Asu June Bot.
- `docs/subprojects/asu-june-bot/eval_questions.md`: eval-вопросы Asu June Bot.
- `docs/subprojects/asu-june-bot/RUNBOOK_V2.md`: runbook v2.1.
- `docs/subprojects/asu-june-bot/search_smoke_report_2026-05-14.md`: smoke-отчет search v2.1.
- `docs/product/PROJECT_ONLY_CHATBOT_MVP.md`: дорожная карта очищенного чат-бота только по проектным источникам.
- `docs/product/PROJECT_STAGES_AND_FTT.md`: рабочая карта этапов продукта, ФТТ и критериев приемки.
- `docs/product/PROJECT_TAXONOMY.md`: единый реестр этапов проекта и типов документов.
- `docs/glossary.md`: словарь терминов и заготовка `initial_prompt` для транскрибации.
- `docs/quality/project_only_chatbot_smoke_questions.md`: smoke-набор вопросов чат-бота.
- `docs/quality/rag_eval_questions.md`: стартовый набор вопросов для baseline качества RAG.
- `scripts/09_chat.py`: prototype project-only CLI чат-бота поверх v1 numpy-RAG.
- `scripts/asu_june_bot_search_v2.py`: search CLI v2.
- `scripts/asu_june_bot_health_v2.py`: health check v2.

## Что Осталось

- Выполнить Search Quality v2.2.
- Улучшить metadata extraction/chunking для `requirement_id`, `mentioned_requirement_ids`, `contract_section`, `document_version`.
- Добавить `/search` только после v2.2.
- Добавить `/chat` только после стабильного `/search`.
- Не отправлять raw hybrid top-k в LLM.
- Не развивать `scripts/09_chat.py` как основную архитектуру.
- Для future: добавить инкрементальное обновление RAG и обработку deletion.
- Для future: добавить source links через `data/asu_june_bot/source_links.json`.

## Восстановление Контекста В Новом Треде

Используй prompt:

```text
Прочитай README.md, AGENTS.md, docs/context.md, docs/todo.md и git log --oneline -10. Восстанови контекст проекта и предложи следующий шаг.
```

Для Asu June Bot используй prompt:

```text
Прочитай README.md, AGENTS.md, docs/context.md, docs/todo.md и все файлы docs/subprojects/asu-june-bot/. Восстанови контекст подпроекта Asu June Bot и предложи следующий практический шаг.
```
