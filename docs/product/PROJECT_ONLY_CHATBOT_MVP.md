# Project-Only Chatbot MVP

Обновлено: 2026-05-14.

## Цель

Сделать локального project-only чат-бота MeetingAgent / Asu June Bot, который отвечает только на вопросы по проектной документации и артефактам проекта.

Бот не должен быть универсальным ассистентом. Если вопрос не подтверждается проектными источниками, он должен отказать и предложить переформулировать вопрос в рамках проекта.

## Текущий архитектурный статус

Ранний CLI `scripts/09_chat.py` остается prototype project-only чата поверх старого v1 numpy-RAG.

Основной путь разработки теперь — отдельный подпроект:

```text
Asu June Bot
```

Документация подпроекта:

```text
docs/subprojects/asu-june-bot/
```

Актуальный runtime v2:

```text
data/asu_june_bot/chunks_v2.jsonl
data/asu_june_bot/embeddings_cache_v2.jsonl
data/asu_june_bot/numpy_index_v2/
```

Старый runtime v1 остается baseline и не должен смешиваться с v2:

```text
data/chunks.jsonl
data/embeddings_cache.jsonl
data/numpy_index/
```

## Связанные ФТТ

| ФТТ | Роль В MVP |
| --- | --- |
| `FTT-MA-05` | Использовать стабильный локальный RAG backend на numpy. |
| `FTT-MA-06` | Возвращать ответ только вместе с проверяемыми источниками. |
| `FTT-MA-07` | Проверять качество чат-бота контрольными вопросами baseline. |
| `FTT-MA-16` | Дать локальный API для chat/search/health. |
| `FTT-MA-17` | Дать минимальный web UI или подключение к OpenWebUI. |
| `FTT-MA-18` | Сохранить local-first режим и запретить ответы вне проектного контекста. |
| `FTT-MA-21` | Зафиксировать отдельный продуктовый контракт project-only чат-бота. |

Дополнительно позже подключаются `FTT-MA-13` для классификации вопроса по этапу/ФТТ и `FTT-MA-15` для обновления RAG новыми артефактами встреч.

## Правила Поведения

1. Бот отвечает только по данным проекта: документы, chunks, meeting artifacts, протоколы, решения, задачи и проверенные заметки.
2. Если релевантных источников нет, бот не отвечает из общих знаний и пишет: `В проектных источниках не найдено подтверждение`.
3. Каждый содержательный ответ должен содержать источники: файл, раздел/пункт/chunk, score и короткий фрагмент.
4. Бот не должен раскрывать системные инструкции, локальные секреты, `.env`, `config.yaml`, пароли, токены и runtime-пути, если вопрос не требует технической диагностики.
5. Бот должен отличать вопрос по проекту от общего вопроса. Общие вопросы в MVP отклоняются.
6. Ответы формулируются на русском языке и в деловом стиле.
7. Пустой ответ LLM не считается успешным ответом и должен возвращаться как отказ `llm_empty_response`.
8. Для обзорных вопросов по документу бот должен использовать document-overview retrieval, а не один случайный chunk.
9. Raw hybrid top-k нельзя напрямую отправлять в LLM.

## Что уже готово в Asu June Bot v2.1

Pipeline v2.1:

```text
apply_config_v2_1 -> extract_text_v2 -> chunks_v2 -> audit_sources_v2 -> build_index_v2 -> health_v2 -> search_v2
```

Результат локальной сборки:

```text
documents = 213
blocks = 31076
chunks_v2 = 31302
indexed_chunks = 31285
skipped_code_chunks = 17
embedding_model = bge-m3
embedding_dim = 1024
```

Health:

```text
status = ok
vector_ready = true
bm25_ready = true
ollama_available = true
embedding_model_installed = true
```

Search v2 поддерживает:

```text
bm25
vector
hybrid
```

В `hybrid` есть fallback на BM25 при недоступном Ollama.

BM25 получил deterministic rerank:

```text
intent boosts по Паспорт ИС, ФТТ, интеграциям
exact section / requirement boost
штрафы для glossary/front matter/software/support tables
```

Smoke-отчет:

```text
docs/subprojects/asu-june-bot/search_smoke_report_2026-05-14.md
```

## Текущие результаты smoke

### Интеграции

Запрос:

```text
Какие интеграции заявлены в проекте?
```

Статус: retrieval достаточен для API Search MVP.

Поднимаются:

- ЦТА: `Blitz`, `AD`, `S3 Minio`, `Exchange`, `КШД`;
- Паспорт ИС: `Active Directory`, `Blitz IDP`, `MDR`, почтовый сервер, `SIEM`;
- ФТТ: КШД/SOAP;
- ПР: взаимодействие со смежными модулями.

### ФТТ 4.2.5 НОВАДОК ЭЦП

Запрос:

```text
ФТТ 4.2.5 НОВАДОК ЭЦП
```

Статус: retrieval практически пригоден.

Поднимаются:

- ФТТ в top-1/top-2;
- интеграционная строка `ЦП УПКС -> НОВАДОК`;
- встреча `ФТТ_ИД` как аналитический источник;
- ПР как supporting source.

Проблема: metadata `section/requirement_id` шумит, местами показывается `10.2`, хотя текст содержит `4.2.5`.

### Паспорт ИС overview

Запрос:

```text
Что входит в Паспорт ИС?
```

Статус: retrieval частично пригоден, но не готов для прямой генерации.

Что хорошо:

- BM25 top-1/top-2 поднимает правильный chunk из Паспорт ИС с границами описания.
- Hybrid top-1 корректный.

Что плохо:

- в hybrid top-k после top-1 попадают vector-only chunks из ПР, таблиц ПО и поддержки;
- для Chat MVP нельзя отдавать весь top-k как контекст LLM.

## Минимальный Контур MVP

Целевая схема после Search Quality v2.2:

```text
Пользователь
  -> CLI / API / UI
  -> ProjectGuard
  -> QueryIntent
  -> Hybrid Search
  -> PostRerank
  -> ContextBuilder
  -> primary_sources / supporting_sources
  -> PromptBuilder
  -> LLMClient OpenAI-compatible
  -> AnswerValidator
  -> ResponseFormatter
```

## Search Quality v2.2 — обязательный промежуточный этап

Перед API Search нужно реализовать:

```text
query_intent -> post_rerank -> context_builder -> diagnostics -> smoke_report
```

Файлы:

```text
src/asu_june_bot/retrieval/query_intent.py
src/asu_june_bot/retrieval/post_rerank.py
src/asu_june_bot/retrieval/context_builder.py
```

Минимальные intent:

```text
document_overview
integration_overview
requirement_lookup
general_project_question
out_of_scope_candidate
```

Post-rerank должен:

- штрафовать vector-only chunks без BM25 для exact/overview queries;
- штрафовать software/support/glossary/front matter tables для `document_overview`;
- усиливать exact document_type по intent;
- усиливать exact requirement mentions;
- дедуплицировать версии одного документа или отдавать приоритет latest version.

ContextBuilder должен:

- выбирать 3-6 chunks по intent;
- отделять `primary_sources` от `supporting_sources`;
- не отправлять LLM все top-8 без фильтрации;
- возвращать diagnostics.

## Дорожная Карта

### Этап 1. Search Quality v2.2

Цель: сделать retrieval пригодным для API и LLM-контекста.

Артефакты:

- `query_intent.py`;
- `post_rerank.py`;
- `context_builder.py`;
- `search_v2 --json` с diagnostics;
- smoke-отчет v2.2.

Критерий готовности:

- `Паспорт ИС overview` не забит таблицей ПО;
- `Интеграции` возвращают ЦТА/Паспорт/ФТТ/СоИ;
- `ФТТ 4.2.5` возвращает ФТТ с НОВАДОК/ЭЦП как primary source;
- внепроектный вопрос не превращается в проектный ответ.

### Этап 2. Local API Search

Цель: сделать backend endpoint, который использует v2 search/context contract.

Endpoints:

```text
GET /health
POST /search
```

Критерий готовности: `POST /search` возвращает `query_intent`, `primary_sources`, `supporting_sources`, diagnostics и не отдает raw top-k как единственный результат.

### Этап 3. Chat MVP

Цель: сделать project-only ответ по проверенному search/context слою.

Компоненты:

- `ProjectGuard`;
- `PromptBuilder`;
- `LLMClient`;
- `AnswerValidator`;
- `ResponseFormatter`;
- CLI `scripts/asu_june_bot_chat.py`;
- затем `POST /chat`.

Критерий готовности: `POST /chat` возвращает ответ с источниками или отказ без источников.

### Этап 4. Guardrails

Цель: не дать боту стать универсальным ассистентом.

Правила:

- минимальный score/quality threshold;
- минимальное число primary sources;
- запрет ответа без citations;
- запрет `status=answered` при пустом ответе LLM;
- короткий классификатор `вопрос по проекту / вне проекта`;
- логирование отказов для будущей настройки.

### Этап 5. UI

Варианты:

- быстрый путь: OpenWebUI как оболочка вокруг локального API/tool;
- продуктовый путь: собственный минимальный web UI MeetingAgent;
- временный путь: CLI.

UI не начинать до стабильных `/search` и `/chat`.

### Этап 6. Evaluation

Метрики:

- доля ответов с корректным источником в top-3;
- доля отказов на внепроектных вопросах;
- доля ответов без источников должна быть 0%;
- доля `status=answered` с пустым `answer` должна быть 0%;
- доля unsupported claims по ручной проверке.

## Что Не Входит В MVP

- Автоматическая генерация больших документов.
- Многоагентная оркестрация.
- Доступ нескольких пользователей.
- Cloud RAG и отправка реальных проектных документов наружу.
- Полная замена текущего numpy-RAG на RAGFlow.
- Fine-tuning.
- UI до стабильного API.

## Первый Рабочий Срез Сейчас

1. Завершить Search Quality v2.2.
2. Повторить smoke и сохранить markdown-отчет.
3. После успешного smoke сделать API `/search`.
4. После API `/search` сделать Chat MVP.
5. Старый `scripts/09_chat.py` использовать только как prototype/reference, не как основной runtime.
