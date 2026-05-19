# MVP / ФТТ Project Knowledge Bot

Обновлено: 2026-05-16.

## 1. Назначение документа

Документ фиксирует функционально-технический состав MVP Project Knowledge Bot, критерии готовности, статус реализации, закрытые и открытые задачи.

Документ используется вместе с:

```text
README.md
architecture.md
roadmap.md
decisions.md
RUNBOOK_V2.md
TOMORROW_START.md
QH_STATUS.md
todo.md
smoke_report_*.md
```

## 2. Цель MVP

Создать локального project-only AI-агента, который:

- принимает вопрос пользователя;
- определяет, относится ли вопрос к загруженному корпусу проектной документации;
- не запускает retrieval/LLM для внепроектных, смешанных и неоднозначных запросов;
- ищет релевантные источники в локальном индексе;
- формирует управляемый context из primary/supporting sources;
- снижает риск слабых primary sources через QH-2;
- расширяет слабые источники ограниченным parent/neighbor context через QH-3;
- генерирует ответ только по найденным источникам;
- возвращает citations;
- добавляет warning-only semantic diagnostics через QH-4;
- логирует chat-запуски;
- позволяет измерять качество через eval baseline;
- предоставляет локальный Web UI и Telegram adapter для демонстрации и пользовательского доступа.

## 3. Scope MVP

### 3.1 Входит

```text
локальный запуск
CLI
FastAPI API
GET /health
POST /search
POST /chat
GET / и GET /ui
Telegram adapter поверх локального /chat
extraction/chunking/index/search pipeline
ProjectGuard v2
SearchService
ChatService
hybrid retrieval: BM25 + vector
PostReranker
ContextBuilder
QH-2 Source Quality Filter
QH-3 Parent Expansion
PromptBuilder
LLMClient через Ollama OpenAI-compatible API
AnswerValidator structural checks
QH-4 Semantic Warnings / Manual Labels
ChatRunsLogger
Eval baseline runner
QH-5 release gate
JSON/Markdown eval reports
```

### 3.2 Не входит

```text
многопользовательский режим
RBAC по источникам
автоматическая синхронизация прав доступа
внешние enterprise-коннекторы
fine-tuning
LLM-as-judge runtime
NLI groundedness model
DSPy runtime
LangGraph agent runtime
Dify/RAGFlow runtime
production deployment
Docker до фактического QH-5 passed
```

## 4. Функционально-технические требования MVP

### AJB-FTT-01. Project-only режим

Бот должен отвечать только по загруженным проектным источникам.

Критерии приёмки:

```text
out-of-project query -> refused
mixed-scope query -> refused
ambiguous query -> clarify
refused/clarify -> LLM не вызывается
```

Статус:

```text
Реализовано
```

### AJB-FTT-02. Pre-retrieval guard

Guard должен выполняться до retrieval.

Критерии приёмки:

```text
refused -> retrieval_called=false
clarify -> retrieval_called=false
allow -> retrieval_called=true
false_allow = 0
```

Статус:

```text
Реализовано
```

### AJB-FTT-03. Извлечение текста из проектных документов

Система должна извлекать текстовые blocks из основных форматов документов.

Форматы MVP:

```text
DOCX
XLSX
XLSB
PDF
PPTX
HTML
TXT/MD/JSON/YAML
```

Статус:

```text
Реализовано
```

### AJB-FTT-04. Chunking v2

Система должна формировать chunks с metadata для поиска и цитирования.

Критерии приёмки:

```text
chunks_v2.jsonl сформирован
parent/child chunks поддерживаются
table_row chunks поддерживаются
metadata содержит source_type/document_type/sections/requirement_id
```

Статус:

```text
Реализовано
```

### AJB-FTT-05. Индексация и embeddings cache

Система должна строить возобновляемый embeddings cache и локальный индекс.

Критерии приёмки:

```text
embedding_model = bge-m3
embeddings_cache_v2.jsonl заполнен
numpy_index_v2 построен
manifest count совпадает с metadata count
```

Статус:

```text
Реализовано
```

### AJB-FTT-06. Гибридный поиск

Система должна поддерживать смысловой и точный поиск.

Статус:

```text
Реализовано
```

### AJB-FTT-07. ContextBuilder

Система должна разделять найденные источники на buckets.

Buckets:

```text
primary_sources
supporting_sources
excluded_sources
```

Критерии приёмки:

```text
primary/supporting передаются в /search context
excluded_sources не передаются в LLM prompt
```

Статус:

```text
Реализовано
```

### AJB-FTT-08. Search API

Система должна предоставлять диагностический endpoint поиска.

Endpoint:

```text
POST /search
```

Статус:

```text
Реализовано
```

### AJB-FTT-09. Chat Service

Система должна формировать ответ по context.

Критерии приёмки:

```text
project query -> llm_called=true
refused query -> llm_called=false
clarify query -> llm_called=false
empty LLM response -> llm_empty_response
answer without citation -> validation_failed
```

Статус:

```text
Реализовано
```

### AJB-FTT-10. Chat API

Система должна предоставлять endpoint осмысленного ответа.

Endpoint:

```text
POST /chat
```

Статус:

```text
Реализовано
```

### AJB-FTT-11. Structural Answer Validation

Система должна блокировать структурно неприемлемые ответы.

Проверки MVP:

```text
пустой ответ
нет sources
нет citations [Sx]
unknown citations
answer length
citation density / coverage
external knowledge markers
```

Статус:

```text
Реализовано
```

Ограничение:

```text
semantic/factual validation не является hard-fail
```

### AJB-FTT-12. Observability

Система должна логировать chat-запуски для последующего накопления dataset.

Файл:

```text
data/asu_june_bot/chat_runs.jsonl
```

Критерии приёмки:

```text
каждый chat-запуск пишет JSONL record
logger не ломает /chat при ошибке записи
есть latency_ms
есть sources/diagnostics/model/status
есть semantic_warnings
есть manual_label/manual_issue placeholders
```

Статус:

```text
Реализовано и проверено локально
```

### AJB-FTT-13. Eval Baseline

Система должна иметь baseline-набор проверок качества.

Файлы:

```text
eval/cases/base.jsonl
eval/golden_answers/*.md
scripts/asu_june_bot_chat_eval.py
```

Статус:

```text
Реализовано
```

### AJB-FTT-14. Local Web UI

Система должна предоставлять минимальный локальный интерфейс для `/chat`.

Endpoint:

```text
GET /
GET /ui
```

Критерии приёмки:

```text
страница открывается в браузере
пользователь вводит query
query отправляется в POST /chat
ответ и sources отображаются на странице
работает счетчик MAX_QUERY_CHARS
```

Статус:

```text
Реализовано, HTTP smoke пройден
```

### AJB-FTT-15. Telegram adapter

Система должна позволять задавать вопросы через Telegram.

Файлы:

```text
src/asu_june_bot/telegram_bot.py
scripts/asu_june_bot_telegram.py
docs/subprojects/asu-june-bot/telegram.md
```

Критерии приёмки:

```text
adapter принимает текстовое сообщение
вызывает локальный POST /chat
возвращает answer + sources
поддерживает /start /help /health
поддерживает allowed chat ids
не хранит token в Git
```

Статус:

```text
Реализовано, local smoke закрыт
```

### AJB-FTT-16. Input limits

Система должна ограничивать длину пользовательского запроса.

Критерий:

```text
MAX_QUERY_CHARS = 2000
```

Применяется:

```text
SearchRequest
ChatRequest
POST /search
POST /chat
Web UI
Telegram adapter
```

Статус:

```text
Реализовано
```

### AJB-FTT-17. QH-2 Source Quality Filter

Система должна снижать риск использования слабых sources как primary evidence.

Реализация:

```text
src/asu_june_bot/retrieval/source_quality.py
src/asu_june_bot/retrieval/context_builder.py
```

Критерии:

```text
короткие UML/diagram/heading fragments помечаются как weak
weak source получает reasons
weak hard fragment демотируется из primary
diagnostics содержит source_quality_filter
raw retrieval не меняется
индекс не пересобирается
```

Статус:

```text
Реализовано и проверено локально
```

### AJB-FTT-18. QH-3 Parent Expansion

Система должна ограниченно расширять weak source соседним/родительским контекстом.

Реализация:

```text
src/asu_june_bot/retrieval/parent_expansion.py
src/asu_june_bot/retrieval/context_builder.py
```

Критерии:

```text
expansion применяется только к weak source
используются только уже найденные кандидаты
есть max_parent_chars
diagnostics содержит parent_expansion
нет обращения к индексу во время expansion
```

Статус:

```text
Реализовано и проверено локально
```

### AJB-FTT-19. QH-4 Semantic Warnings / Manual Labels

Система должна добавлять warning-only слой качества без hard-fail semantic validation.

Реализация:

```text
src/asu_june_bot/chat/semantic_warnings.py
src/asu_june_bot/chat/service.py
src/asu_june_bot/observability/chat_runs.py
```

Критерии:

```text
warnings.semantic возвращается в /chat
semantic_warnings пишется в diagnostics
semantic_warnings логируется в chat_runs.jsonl
manual_label/manual_issue placeholders есть в chat_runs
warnings не блокируют answered
```

Статус:

```text
Реализовано и проверено локально
```

### AJB-FTT-20. QH-5 Release Gate

Система должна иметь явный gate перед Docker/release stabilization.

Реализация:

```text
src/asu_june_bot/qh/release_gate.py
scripts/asu_june_bot_qh_gate.py
```

Критерии:

```text
до локальной проверки status = pending_local_validation
после local-validation-done + baseline-compared status = passed
Docker не начинается до фактического passed
```

Статус:

```text
Реализовано, QH-5 = PASSED
```

## 5. Текущие метрики корпуса

Последний подтвержденный срез:

```text
documents = 213
blocks = 31076
chunks_v2 = 31302
indexed_chunks = 31285
embedding_model = bge-m3
embedding_dim = 1024
skipped_code_chunks = 17
```

## 6. Рабочая модель LLM

Рекомендуемая модель MVP:

```text
qwen2.5:7b-instruct
```

Параметры smoke:

```text
temperature = 0.0
max_tokens = 500
timeout_sec = 300
top_k = 5
```

## 7. План-график MVP

```text
Этап 1. Corpus v2.1                         Закрыт
Этап 2. Index/Search v2                     Закрыт
Этап 3. Search Quality v2.2                 Закрыт
Этап 4. ProjectGuard v2                     Закрыт
Этап 5. SearchService + API Search MVP      Закрыт
Этап 6. Chat MVP                            Закрыт с ограничениями
Этап 7. UI + Telegram adapter               Закрыт local smoke
Этап 8. QH-1 Observability + Eval Baseline  Реализован
Этап 9. QH-2 Source Quality Filter          Реализован и проверен
Этап 10. QH-3 Parent Expansion              Реализован и проверен
Этап 11. QH-4 Semantic Warnings             Реализован и проверен
Этап 12. QH-5 Release Gate                  PASSED
Этап 13. Docker                             Следующий этап
```

## 8. Закрытые задачи

```text
case-conflict runbook выявлен
project-only guard реализован
retrieval не вызывается при refused/clarify
/search реализован
/chat реализован
UI реализован
Telegram adapter реализован
input limit реализован
qwen2.5 выбрана как MVP model
chat_runs logger добавлен
baseline eval skeleton добавлен
QH-2 source quality filter реализован
QH-3 parent expansion реализован
QH-4 semantic warnings/manual labels реализован
QH-5 release gate реализован
```

## 9. Открытые задачи

```text
Docker packaging
полный realistic 100 eval
QH-6 Feedback Dataset Loop
подготовить выделение в отдельный репозиторий после Docker
```

## 10. Definition of Done MVP

MVP считается технически закрытым, когда:

```text
health ok
/search ok/refused/clarify работает
/chat answered/refused/clarify работает
UI открывается и вызывает /chat
Telegram adapter отвечает через локальный /chat
LLM не вызывается при refused/clarify
ProjectGuard false_allow = 0
ChatService tests passed
API tests passed
QH tests passed
chat_runs.jsonl пишется
baseline/after_qh eval reports формируются
QH gate фактически passed
активная документация синхронизирована
устаревшие документы вынесены в archive
```
