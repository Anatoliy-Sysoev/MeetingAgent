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
- генерирует ответ только по найденным источникам;
- возвращает citations;
- логирует chat-запуски;
- позволяет измерять качество через eval baseline.

## 3. Scope MVP

### 3.1 Входит

```text
локальный запуск
CLI
FastAPI API
GET /health
POST /search
POST /chat
extraction/chunking/index/search pipeline
ProjectGuard v2
SearchService
ChatService
hybrid retrieval: BM25 + vector
PostReranker
ContextBuilder
PromptBuilder
LLMClient через Ollama OpenAI-compatible API
AnswerValidator structural checks
ChatRunsLogger
Eval baseline runner
JSON/Markdown eval reports
```

### 3.2 Не входит

```text
полноценный web UI
многопользовательский режим
RBAC по источникам
автоматическая синхронизация прав доступа
внешние коннекторы
fine-tuning
LLM-as-judge
NLI groundedness model
DSPy runtime
LangGraph agent runtime
Dify/RAGFlow runtime
production deployment
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

Доказательство:

```text
ProjectGuard v2 regression
API /search smoke
API /chat smoke
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

Критерии приёмки:

```text
DOCX читается с учетом paragraph/table blocks
XLSX читается через openpyxl
табличные строки попадают в blocks/chunks
временные и технические выгрузки исключаются
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

Критерии приёмки:

```text
BM25 работает по точным идентификаторам
vector search работает по смысловым вопросам
hybrid mode объединяет результаты
```

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

Критерии приёмки:

```text
project query -> status ok
out-of-project query -> status refused
mixed query -> status refused
ambiguous query -> status clarify
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

Критерии приёмки:

```text
project query -> answered
out-of-project query -> refused
sources возвращаются в response
request_id возвращается в diagnostics/header
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
semantic/factual validation не реализована
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
```

Статус:

```text
Реализовано, ожидает локальный smoke после pull
```

### AJB-FTT-13. Eval Baseline

Система должна иметь baseline-набор проверок качества.

Файлы:

```text
eval/cases/base.jsonl
eval/golden_answers/*.md
scripts/asu_june_bot_chat_eval.py
```

Критерии приёмки:

```text
eval runner читает JSONL cases
eval runner запускает ChatService
eval runner формирует JSON/Markdown reports
checks deterministic, без LLM-as-judge
```

Статус:

```text
Реализовано, ожидает локальный baseline-прогон
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

### Этап 1. Corpus v2.1

Статус:

```text
Закрыт
```

Результаты:

```text
extraction v2
chunking v2
source audit
exclude rules
```

### Этап 2. Index/Search v2

Статус:

```text
Закрыт
```

Результаты:

```text
embeddings cache
numpy index
BM25
hybrid search
health check
```

### Этап 3. Search Quality v2.2

Статус:

```text
Закрыт
```

Результаты:

```text
QueryIntent
PostReranker
ContextBuilder
primary/supporting/excluded sources
```

### Этап 4. ProjectGuard v2

Статус:

```text
Закрыт
```

Результаты:

```text
pre-retrieval guard
mixed-scope policy
project + unknown tail policy
regression suite
```

### Этап 5. SearchService + API Search MVP

Статус:

```text
Закрыт
```

Результаты:

```text
SearchService
GET /health
POST /search
API smoke reports
```

### Этап 6. Chat MVP

Статус:

```text
Закрыт с ограничениями
```

Результаты:

```text
ChatService
PromptBuilder
LLMClient
AnswerValidator
ResponseFormatter
CLI chat
POST /chat
API chat smoke
```

Ограничение:

```text
semantic/factual validation пока отсутствует
```

### Этап 7. QH-1 Observability + Eval Baseline

Статус:

```text
Реализован в коде, ожидает локальную проверку
```

Результаты:

```text
ChatRunsLogger
chat_runs.jsonl
eval cases
eval runner
JSON/Markdown reports
```

### Этап 8. QH-2 Source Quality Filter

Статус:

```text
Открыт
```

Условие старта:

```text
после baseline eval
```

### Этап 9. QH-3 Parent Expansion

Статус:

```text
Открыт
```

Условие старта:

```text
если QH-2 не решит проблему коротких chunks
```

## 8. Закрытые задачи

```text
case-conflict runbook выявлен
project-only guard реализован
retrieval не вызывается при refused/clarify
/search реализован
/chat реализован
qwen2.5 выбрана как MVP model
chat_runs logger добавлен
baseline eval skeleton добавлен
```

## 9. Открытые задачи

```text
локально прогнать QH-1 regression tests
локально прогнать baseline eval
проанализировать failures
актуализировать eval cases по фактическим результатам
реализовать QH-2 source quality filter
реализовать QH-3 parent expansion при необходимости
добавить no_answer/insufficient status позже
подготовить выделение в отдельный репозиторий
```

## 10. Definition of Done MVP

MVP считается технически закрытым, когда:

```text
health ok
/search ok/refused/clarify работает
/chat answered/refused/clarify работает
LLM не вызывается при refused/clarify
ProjectGuard false_allow = 0
ChatService tests passed
API tests passed
chat_runs.jsonl пишется
baseline eval report формируется
активная документация синхронизирована
устаревшие документы вынесены в archive
```
