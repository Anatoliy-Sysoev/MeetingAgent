# Контекст Проекта

Обновлено: 2026-05-15.

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
- `ideas.md` — research backlog;
- `RUNBOOK_V2.md` — запуск extraction/chunking/index/search/guard/API;
- `product/` — отдельный продуктовый пакет: problem, vision, JTBD, BABOK, архитектура, roadmap;
- `smoke_report_project_guard_v2.md` — финальный smoke-отчёт ProjectGuard v2;
- `smoke_report_search_service_commit1.md` — smoke-отчёт SearchService;
- `smoke_report_api_search_mvp.md` — smoke-отчёт API Search MVP.

Важное решение: текущий `scripts/09_chat.py` остается prototype project-only чата. Новую реализацию Asu June Bot нужно делать модульно, без дальнейшего раздувания одного CLI-скрипта.

## Актуальный Статус Asu June Bot

Asu June Bot v2.1/v2.2 доведён до уровня API Search MVP.

Дополнительно подготовлен отдельный product package в:

```text
docs/subprojects/asu-june-bot/product/
```

Он описывает продукт как самостоятельный контур: проблему, ценность, целевые роли, BABOK-требования, продуктовую архитектуру и этапы развития.

Готово:

```text
apply_config_v2_1 -> extract_text_v2 -> chunks_v2 -> audit_sources_v2 -> build_index_v2 -> health_v2 -> search_v2
Search Quality v2.2
ProjectGuard v2
SearchService
FastAPI GET /health
FastAPI POST /search
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

ProjectGuard v2:

```text
45 regression cases
false_allow = 0
```

API Search MVP:

```text
GET /health работает
POST /search работает
/search возвращает sources/context, но не генерирует осмысленный ответ
```

Важно: `/search` — не чат. Он возвращает `primary_sources`, `supporting_sources`, `excluded_sources` и diagnostics. Осмысленный ответ должен появиться на этапе Chat MVP через `PromptBuilder`, `LLMClient`, `AnswerValidator` и `ResponseFormatter`.

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

## Ближайшая Цель Asu June Bot

Следующий этап — Chat MVP:

```text
src/asu_june_bot/chat/
src/asu_june_bot/llm/
scripts/asu_june_bot_chat.py
```

Будущий pipeline:

```text
User question
  -> ChatService
  -> SearchService.search()
  -> if refused/clarify: return refusal/clarification without LLM
  -> if ok: use context.primary_sources + context.supporting_sources
  -> PromptBuilder
  -> LLMClient
  -> AnswerGenerator
  -> AnswerValidator
  -> ResponseFormatter
  -> answer with citations
```

Ключевое правило:

```text
/search возвращает evidence/context
/chat возвращает осмысленный ответ
```

## Search Quality v2.2

Реализовано:

```text
src/asu_june_bot/retrieval/query_intent.py
src/asu_june_bot/retrieval/post_rerank.py
src/asu_june_bot/retrieval/context_builder.py
```

`search_v2 --json` и `POST /search` возвращают:

```text
query_intent
guard
rerank
context.primary_sources
context.supporting_sources
context.excluded_sources
results
warnings
```

Проверено:

- `Что входит в Паспорт ИС?` — primary содержит обзорный chunk `Границы описания`;
- `ФТТ 4.2.5 НОВАДОК ЭЦП` — primary содержит ФТТ, Таблица 8, строка 44, № `4.2.5`;
- `Какие интеграции заявлены в проекте?` — context содержит ЦТА, Паспорт ИС, ФТТ, СоИ;
- JSON через `--output` сохраняется в UTF-8 без mojibake.

## ProjectGuard v2

Реализовано:

```text
src/asu_june_bot/guardrails/models.py
src/asu_june_bot/guardrails/segmenter.py
src/asu_june_bot/guardrails/scope_classifier.py
src/asu_june_bot/guardrails/aggregator.py
src/asu_june_bot/guardrails/policy.py
src/asu_june_bot/guardrails/project_guard.py
```

Тесты и eval:

```text
tests/asu_june_bot/test_project_guard_v2.py
tests/asu_june_bot/guard_v2_cases.jsonl
tests/asu_june_bot/test_project_guard_v2_cases.py
scripts/asu_june_bot_guard_v2_eval.py
```

ProjectGuard v2 работает до retrieval:

```text
allow -> retrieval выполняется
refused -> retrieval не выполняется
clarify -> retrieval не выполняется
```

Важное policy-level правило:

```text
project + unknown tail -> refused / in_project_query_contains_unclassified_segment
```

Это правило введено вместо расширения marker DB частными creative/chitchat темами.

## Текущий RAG v1 / Project-Only Chat Prototype

Основной RAG v1 локально собран: текущие `data/chunks.jsonl` дают 5153 chunks после исключения архивов, черновиков, backup-файлов и служебных JSON-копий. `data/embeddings_cache.jsonl` содержит валидные `bge-m3` embeddings для всех текущих chunks и сохраняет stale-записи для ранее удаленных/исключенных chunks.

ChromaDB больше не считается стабильным поисковым слоем: локально наблюдалась ошибка загрузки HNSW-индекса. Для критического пути поиска используется отдельный numpy-индекс в `data/numpy_index`.

Project-Only Chatbot prototype начат как узкий CLI поверх текущего numpy-RAG:

- `scripts/09_chat.py` выполняет retrieval, фильтрует источники по `score_threshold`, отказывает без источников и только после этого вызывает локальную LLM;
- `configs/prompts/project_only_chat.md` задает project-only политику ответа и включает `/no_think` для Qwen;
- `docs/quality/project_only_chatbot_smoke_questions.md` содержит smoke-набор проектных и внепроектных вопросов.

Важно: `scripts/09_chat.py` не развивать как основной runtime Asu June Bot. Он остается prototype.

## Важные Runtime-Факты

- `scripts/asu_june_bot_build_index_v2.py` — сборка embeddings/index v2.
- `data/asu_june_bot/embeddings_cache_v2.jsonl` — resumable cache embeddings v2.
- `data/asu_june_bot/numpy_index_v2` — локальный numpy-индекс v2, игнорируется Git.
- `scripts/asu_june_bot_health_v2.py` — CLI health check v2.
- `scripts/asu_june_bot_search_v2.py` — CLI search v2, thin wrapper над `SearchService`.
- `scripts/asu_june_bot_api.py` — запуск FastAPI Search API.
- `src/asu_june_bot/search/service.py` — единая orchestration-точка для CLI/API search.
- `src/asu_june_bot/api/routes_search.py` — thin API adapter над `SearchService`.
- `scripts/asu_june_bot_guard_v2_eval.py` — regression eval guard v2.
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
- `docs/subprojects/asu-june-bot/ideas.md`: research backlog.
- `docs/subprojects/asu-june-bot/RUNBOOK_V2.md`: runbook v2.
- `docs/subprojects/asu-june-bot/smoke_report_project_guard_v2.md`: smoke-отчёт ProjectGuard v2.
- `docs/subprojects/asu-june-bot/smoke_report_search_service_commit1.md`: smoke-отчёт SearchService.
- `docs/subprojects/asu-june-bot/smoke_report_api_search_mvp.md`: smoke-отчёт API Search MVP.
- `docs/product/PROJECT_ONLY_CHATBOT_MVP.md`: дорожная карта очищенного чат-бота только по проектным источникам, если файл присутствует в ветке.
- `docs/product/PROJECT_STAGES_AND_FTT.md`: рабочая карта этапов продукта, ФТТ и критериев приемки.
- `docs/product/PROJECT_TAXONOMY.md`: единый реестр этапов проекта и типов документов.

## Что Осталось

- Реализовать Chat MVP.
- Добавить `/chat` только после стабильного CLI Chat MVP.
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
