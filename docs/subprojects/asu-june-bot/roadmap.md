# Roadmap Asu June Bot

Обновлено: 2026-05-12.

## Принцип roadmap

Развитие должно идти не от UI и не от модели, а от качества project-only контура:

```text
источники -> поиск -> ответ -> проверка -> API -> UI -> GPU
```

## Этап 0. Документация и архитектурный reset

Цель: отделить Asu June Bot от общего MeetingAgent и остановить разрастание `scripts/09_chat.py`.

Артефакты:

- README подпроекта;
- context.md;
- decisions.md;
- architecture.md;
- mvp.md;
- roadmap.md;
- todo.md;
- eval_questions.md.

Критерий готовности:

- есть полный стартовый контекст для нового треда;
- понятно, что `09_chat.py` — prototype, а не целевой код.

## Этап 1. Базовый Project-only Search

Цель: получить надежный `/search` до генерации ответов.

Работы:

1. Описать chunk schema.
2. Добавить metadata extraction:
   - document_type;
   - module;
   - stage;
   - section;
   - title;
   - source_type.
3. Реализовать vector search adapter поверх текущего numpy index.
4. Реализовать BM25 search.
5. Реализовать hybrid merge.
6. Реализовать source policy.
7. Сделать CLI `asu_june_bot_search.py`.

Критерий готовности:

- `/search` и CLI возвращают релевантные источники по 15 контрольным вопросам;
- точные запросы по пунктам ФТТ/ЦТА не теряются;
- `system_export` не вытесняет проектные документы без необходимости.

## Этап 2. Project-only Chat MVP

Цель: получить `/chat` с ответом или отказом.

Работы:

1. Project guard.
2. Query expansion из YAML.
3. Context builder.
4. Prompt builder.
5. LLM client через OpenAI-compatible API.
6. Answer validator.
7. Response formatter.
8. CLI `asu_june_bot_chat.py`.

Критерий готовности:

- вопрос по проекту получает ответ с sources;
- вопрос вне проекта получает отказ;
- ответ без sources невозможен;
- timeout LLM не превращается в ложный `answered`.

## Этап 3. Evaluation baseline

Цель: сделать качество измеримым.

Работы:

1. Описать 30–50 вопросов.
2. Разделить вопросы:
   - project factual;
   - project analytical;
   - exact section lookup;
   - cross-document;
   - out-of-scope;
   - sensitive;
   - no-answer.
3. Сделать runner.
4. Сохранять результаты в Markdown и JSON.
5. Считать метрики.

Критерий готовности:

- есть baseline-отчет;
- известно, где слабое место: guard, retrieval, reranker, LLM, validator.

## Этап 4. Улучшение качества retrieval

Цель: ответы по проекту становятся точнее и глубже.

Работы:

1. Reranker.
2. Better document expansion.
3. Фильтры по типам документов.
4. Специальные retrieval modes:
   - exact_section;
   - document_overview;
   - integration_answer;
   - cross_document_traceability;
   - meeting_decisions.
5. Source links mapping.

Критерий готовности:

- вопросы по ФТТ/ПР/ЦТА/ПМИ дают трассируемые ответы;
- бот может объяснить, где требование описано, где реализовано и где проверяется.

## Этап 5. FastAPI + Open WebUI

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
