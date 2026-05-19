# 07. Архитектура продукта и взаимосвязи

Обновлено: 2026-05-16.

## Архитектура на одной странице

Project Knowledge Bot состоит из пяти связанных слоев:

1. knowledge corpus;
2. ingestion/chunking/index;
3. retrieval and guard core;
4. answer surface;
5. observability/evaluation layer.

## Общая схема

```mermaid
graph TD
    A["Проектные документы"] --> B["Extraction v2.1"]
    M["Артефакты встреч"] --> B
    B --> C["Chunking v2.1"]
    C --> D["Embeddings Cache v2"]
    C --> E["BM25 Corpus"]
    D --> F["Numpy Index v2"]
    Q["Запрос пользователя"] --> G["QueryIntent"]
    G --> H["ProjectGuard v2"]
    H -->|refused/clarify| R0["Ответ без retrieval/LLM"]
    H -->|allow| I["Hybrid Retrieval"]
    F --> I
    E --> I
    I --> J["PostReranker"]
    J --> K["ContextBuilder"]
    K --> L["/search API"]
    K --> N["ChatService"]
    N --> O["PromptBuilder + LLMClient"]
    O --> P["AnswerValidator"]
    P --> X["/chat API: ответ с источниками"]
    N --> LOG["ChatRunsLogger"]
    LOG --> EV["Eval Baseline"]
```

## Взаимосвязь с базовым репозиторием

```mermaid
graph LR
    MA["MeetingAgent"] --> DOCS["Корпус проектных документов"]
    MA --> MEET["Артефакты встреч"]
    DOCS --> PKB["Project Knowledge Bot"]
    MEET --> PKB
    PKB --> SEARCH["Project-only Search"]
    PKB --> CHAT["Project-only Chat"]
    PKB --> EVAL["Quality Baseline"]
```

Смысл разделения:

- базовый репозиторий шире и включает обработку встреч, транскрибацию и общий RAG baseline;
- Project Knowledge Bot уже и отвечает за project-only knowledge interface;
- при выделении в отдельный репозиторий бот должен сохранить собственные docs, runtime scripts, API, eval cases и runbook.

## Поток пользовательского вопроса

```mermaid
sequenceDiagram
    participant U as Пользователь
    participant API as API / CLI
    participant SS as SearchService
    participant INT as QueryIntent
    participant GRD as ProjectGuard v2
    participant RET as Hybrid Retrieval
    participant CTX as ContextBuilder
    participant CHAT as ChatService
    participant LLM as LLMClient
    participant VAL as AnswerValidator
    participant LOG as ChatRunsLogger

    U->>API: Вопрос
    API->>CHAT: ChatRequest
    CHAT->>SS: search(query)
    SS->>INT: Определить intent
    INT->>GRD: Передать запрос и intent
    GRD-->>SS: refused / clarify / allow
    alt refused or clarify
        SS-->>CHAT: status refused/clarify без retrieval
        CHAT-->>API: ответ без LLM
        CHAT->>LOG: записать run
        API-->>U: отказ или уточнение
    else allow
        SS->>RET: Выполнить retrieval
        RET->>CTX: Передать ranked sources
        CTX-->>SS: primary/supporting/excluded
        SS-->>CHAT: SearchResponse ok
        CHAT->>LLM: prompt по curated context
        LLM-->>CHAT: raw answer
        CHAT->>VAL: structural validation
        CHAT->>LOG: записать run
        CHAT-->>API: ChatResponse
        API-->>U: ответ с источниками
    end
```

## Граф знания на уровне предметной области

```mermaid
graph TD
    REQ["Требования"] --> ARCH["Архитектура"]
    REQ --> DESIGN["Проектные решения"]
    REQ --> TEST["Испытания"]
    ARCH --> INT["Интеграции"]
    DESIGN --> TEST
    INT --> PAS["Паспорт ИС"]
    PAS --> GUIDE["Руководства"]
    PROT["Протоколы встреч"] --> DEC["Решения"]
    PROT --> RISK["Риски"]
    PROT --> TASK["Задачи"]
    DEC --> DESIGN
    DEC --> REQ
    TASK --> TEST
```

## Поведенческая архитектура использования

```mermaid
graph LR
    T["Рабочий вопрос"] --> A["Запрос к боту"]
    A --> R["Ответ / отказ / уточнение"]
    R --> S["Источники и diagnostics"]
    S --> C["Доверие к инструменту"]
    C --> H["Повторное использование"]
    H --> E["Новые eval cases и улучшения"]
```

Повторяемость строится не на искусственной вовлекаемости, а на рабочей ценности: быстрее найти, проверить и объяснить.

## Архитектурные границы

### Ядро

```text
corpus
extraction/chunking/index
retrieval
guard
context building
answer policy
validation
eval baseline
```

### Поверхность

```text
CLI
FastAPI
будущий OpenWebUI / web panel
smoke reports
runbook
```

### Расширение

```text
meeting integration
cross-document analyst mode
traceability matrix
source quality filter
parent expansion
future UI/timeline/explanations
GPU inference
```

## Почему такая архитектура правильна

Она позволяет:

- не смешивать generic AI-chat с project-only продуктом;
- отдельно развивать corpus, retrieval, chat и UI;
- сначала стабилизировать `/search`, потом `/chat`, потом UI;
- подключать встречи, не ломая фундамент;
- держать продукт локальным и воспроизводимым;
- измерять качество изменений через baseline.

## Ключевой архитектурный принцип

Интерфейс не должен быть умнее ядра.

Сначала должны быть стабильны:

1. corpus;
2. retrieval;
3. guard;
4. context semantics;
5. API;
6. chat validation;
7. eval baseline.

И только потом UI, deployment hardening и расширенная аналитика.

## Текущий статус архитектуры

```text
/search API: готов
/chat API: готов с ограничениями
observability/eval: реализованы, baseline и after_qh eval выполнены
source quality filter: реализован в QH-2
parent expansion: реализован в QH-3
```
