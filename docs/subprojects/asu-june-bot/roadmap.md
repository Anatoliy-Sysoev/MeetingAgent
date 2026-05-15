# Roadmap Asu June Bot

Обновлено: 2026-05-15.

## Принцип roadmap

Развитие должно идти не от UI и не от модели, а от качества project-only контура:

```text
источники -> поиск -> guard -> context -> API -> ответ -> проверка -> UI -> GPU
```

## Статус этапов

```text
Этап 0. Документация и архитектурный reset — выполнено
Этап 1. Базовый Project-only Search — выполнено
Этап 1.1. Search Quality v2.2 — выполнено
Этап 1.2. ProjectGuard v2 — выполнено
Этап 1.3. API Search MVP — следующий этап
Этап 2. Project-only Chat MVP — после API Search
Этап 3. Evaluation baseline — частично выполнено для guard, расширить для search/chat
Этап 4. Улучшение качества retrieval — продолжается итерационно
Этап 5. FastAPI + Open WebUI — после /chat
Этап 6. GPU migration path — позже
Этап 7. Enterprise-hardening — позже
```

## Этап 0. Документация и архитектурный reset

Статус: выполнено.

Цель: отделить Asu June Bot от общего MeetingAgent и остановить разрастание `scripts/09_chat.py`.

Артефакты:

- README подпроекта;
- context.md;
- decisions.md;
- architecture.md;
- mvp.md;
- roadmap.md;
- todo.md;
- eval_questions.md;
- ideas.md;
- RUNBOOK_V2.md.

Критерий готовности:

- есть полный стартовый контекст для нового треда;
- понятно, что `09_chat.py` — prototype, а не целевой код.

## Этап 1. Базовый Project-only Search

Статус: выполнено.

Цель: получить надежный search CLI до генерации ответов.

Реализовано:

1. Extraction/Chunking v2.1.
2. Metadata extraction:
   - document_type;
   - module;
   - stage;
   - section;
   - title;
   - source_type.
3. Vector search adapter поверх `numpy_index_v2`.
4. BM25 search.
5. Hybrid merge.
6. Source type filtering.
7. CLI `scripts/asu_june_bot_search_v2.py`.
8. Health check `scripts/asu_june_bot_health_v2.py`.

Критерий готовности:

- corpus/index/search готовы;
- exact queries по ФТТ не теряются;
- `system_export` исключён из основного корпуса;
- `health_v2` показывает `status=ok`, `vector_ready=true`, `bm25_ready=true`.

## Этап 1.1. Search Quality v2.2

Статус: выполнено.

Цель: не отправлять raw hybrid top-k в будущий LLM.

Реализовано:

```text
src/asu_june_bot/retrieval/query_intent.py
src/asu_june_bot/retrieval/post_rerank.py
src/asu_june_bot/retrieval/context_builder.py
```

Результат:

- `search_v2` возвращает `query_intent`, `rerank`, `context.primary_sources`, `context.supporting_sources`, `context.excluded_sources`;
- `Паспорт ИС overview` получает обзорный chunk в primary;
- `ФТТ 4.2.5` получает точную строку ФТТ в primary;
- `Интеграции` получают ЦТА/Паспорт ИС/ФТТ/СоИ как primary/supporting context;
- software/support/front matter noise выводится в excluded/supporting и не попадает в primary.

## Этап 1.2. ProjectGuard v2

Статус: выполнено.

Цель: project-only pre-retrieval guard без бесконечного расширения одного словаря out-of-scope.

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

Финальный результат:

```json
{
  "total": 44,
  "passed": 44,
  "failed": 0,
  "false_allow": 0,
  "false_refuse": 0,
  "false_clarify": 0
}
```

Критерий готовности:

- pure project -> allow;
- pure out-of-project -> refused;
- mixed-scope -> refused;
- offensive/security -> refused;
- jailbreak/prompt-injection -> refused;
- ambiguous -> clarify;
- `false_allow = 0`.

## Этап 1.3. API Search MVP

Статус: следующий этап.

Цель: дать HTTP API над готовым search pipeline.

Работы:

1. Вынести search orchestration из CLI в reusable module, если потребуется.
2. Реализовать FastAPI app:

```text
src/asu_june_bot/api/app.py
src/asu_june_bot/api/routes_health.py
src/asu_june_bot/api/routes_search.py
```

3. Реализовать endpoints:

```text
GET /health
POST /search
```

4. `/search` должен повторять CLI pipeline:

```text
QueryIntent -> ProjectGuard v2 -> Retrieval -> PostReranker -> ContextBuilder -> JSON response
```

5. При `refused` и `clarify` retrieval не вызывается.
6. Добавить smoke-команды PowerShell/curl.
7. Обновить runbook.

Критерий готовности:

- `GET /health` возвращает состояние corpus/index/Ollama/guard;
- `POST /search` возвращает тот же формат, что CLI `search_v2 --json`;
- project-запросы возвращают `status=ok` и context;
- out-of-project/mixed/ambiguous возвращают `refused/clarify` без retrieval;
- API smoke пройден.

## Этап 2. Project-only Chat MVP

Статус: после API Search.

Цель: получить `/chat` с ответом или отказом.

Работы:

1. PromptBuilder.
2. LLM client через OpenAI-compatible API.
3. Answer generator.
4. Answer validator.
5. Response formatter.
6. CLI `scripts/asu_june_bot_chat.py`.
7. API `POST /chat`.

Критерий готовности:

- вопрос по проекту получает ответ с sources;
- вопрос вне проекта получает отказ;
- ответ без sources невозможен;
- timeout LLM не превращается в ложный `answered`;
- LLM получает только `ContextBuilder` context, а не raw top-k.

## Этап 3. Evaluation baseline

Статус: частично выполнено для guard, расширить для search/chat.

Готово:

- ProjectGuard v2 regression suite: 44 кейса.

Нужно расширить:

1. Search eval cases:
   - project factual;
   - exact section lookup;
   - cross-document;
   - integration overview;
   - no-answer.
2. Chat eval cases после `/chat`.
3. Runner для сохранения Markdown/JSON.
4. Метрики retrieval/context/answer.

Критерий готовности:

- есть baseline-отчет;
- известно, где слабое место: guard, retrieval, reranker, LLM, validator.

## Этап 4. Улучшение качества retrieval

Статус: продолжается итерационно.

Работы:

1. Better document expansion.
2. Фильтры по типам документов.
3. Специальные retrieval modes:
   - exact_section;
   - document_overview;
   - integration_answer;
   - cross_document_traceability;
   - meeting_decisions.
4. Source links mapping.
5. Дедупликация семейств интеграций.

Критерий готовности:

- вопросы по ФТТ/ПР/ЦТА/ПМИ дают трассируемые ответы;
- бот может объяснить, где требование описано, где реализовано и где проверяется.

## Этап 5. FastAPI + Open WebUI

Статус: после `/chat`.

Цель: дать удобный пользовательский доступ.

Работы:

1. Стабилизировать `/chat`.
2. Стабилизировать `/search`.
3. Подключить Open WebUI через OpenAI-compatible endpoint или tool/server adapter.
4. Добавить режим отображения citations.
5. Добавить историю вопросов локально.

Критерий готовности:

- ботом можно пользоваться как локальным ChatGPT по проекту;
- пользователь видит источники и ограничения.

## Этап 6. GPU migration path

Статус: позже.

Цель: перенести инференс LLM на GPU без переписывания агента.

Работы:

1. Поднять vLLM server.
2. Переключить `LLM_BASE_URL`.
3. Проверить Qwen3 14B / 32B.
4. Сравнить качество и latency.
5. Оставить локальный Ollama как fallback.

Критерий готовности:

- один и тот же API агента работает с Ollama и vLLM;
- качество ответов выросло на eval-наборе.

## Этап 7. Enterprise-hardening

Статус: позже.

Цель: подготовка к корпоративному использованию.

Работы:

1. RBAC.
2. AD/LDAP.
3. Audit logs.
4. Source-level access control.
5. Secrets detection.
6. SIEM/export logs.
7. Human review mode.
8. Права на документы и контуры.
9. NeMo Guardrails / Guardrails AI как possible hardening.

Критерий готовности:

- разные пользователи видят только разрешенные источники;
- все ответы и источники аудируются;
- sensitive-данные не раскрываются.

## Не делать сейчас

- Не строить UI до стабилизации `/chat` и `/search`.
- Не внедрять NeMo Guardrails до baseline.
- Не подключать Dify/RAGFlow как основной backend.
- Не делать мультиагентность.
- Не делать fine-tuning.
- Не добавлять новые regex-патчи в старый `09_chat.py` вместо архитектурной реализации.
- Не возвращаться к бесконечному расширению одного списка regex как основной guard-архитектуре.
