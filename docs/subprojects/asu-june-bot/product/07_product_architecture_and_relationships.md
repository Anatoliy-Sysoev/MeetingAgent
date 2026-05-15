# 07. Архитектура Продукта и Взаимосвязи

Обновлено: 2026-05-15.

## Архитектура На Одной Странице

`Asu June Bot` состоит из четырех связанных слоев:

1. knowledge corpus;
2. retrieval and guard core;
3. answer surface;
4. product workflow and adoption layer.

## Общая Схема

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
    H --> I["Hybrid Retrieval"]
    F --> I
    E --> I
    I --> J["PostReranker"]
    J --> K["ContextBuilder"]
    K --> L["/search API"]
    K --> N["/chat API"]
    N --> O["LLM Answerer"]
    O --> P["Ответ с источниками"]
```

## Взаимосвязь С MeetingAgent

```mermaid
graph LR
    MA["MeetingAgent"] --> DOCS["Корпус проектных документов"]
    MA --> MEET["Артефакты встреч"]
    DOCS --> AJB["Asu June Bot"]
    MEET --> AJB
    AJB --> SEARCH["Project-Only Search"]
    AJB --> CHAT["Project-Only Chat"]
```

Смысл разделения:

- `MeetingAgent` шире и отвечает за общий корпус, встречи и pipeline артефактов;
- `Asu June Bot` уже и отвечает за project-only knowledge interface.

## Поток Пользовательского Вопроса

```mermaid
sequenceDiagram
    participant U as Пользователь
    participant API as API / CLI
    participant INT as QueryIntent
    participant GRD as ProjectGuard v2
    participant RET as Hybrid Retrieval
    participant CTX as ContextBuilder
    participant LLM as LLM Answerer

    U->>API: Вопрос по проекту
    API->>INT: Определить intent
    INT->>GRD: Передать запрос и intent
    GRD-->>API: refused / clarify / allow
    alt allow
        API->>RET: Выполнить retrieval
        RET->>CTX: Передать ranked sources
        CTX-->>API: primary/supporting context
        API->>LLM: Сформировать ответ по context
        LLM-->>API: Ответ
        API-->>U: Ответ с источниками
    else refused or clarify
        API-->>U: Отказ или уточнение без retrieval
    end
```

## Граф Знания На Уровне Предметной Области

```mermaid
graph TD
    FTT["ФТТ"] --> CTA["ЦТА"]
    FTT --> PR["Проектные решения"]
    FTT --> PMI["ПМИ"]
    CTA --> SOI["Соглашения об интеграции"]
    PR --> PMI
    SOI --> PAS["Паспорт ИС"]
    PAS --> GUIDE["Руководства"]
    PROT["Протоколы встреч"] --> DEC["Решения"]
    PROT --> RISK["Риски"]
    PROT --> TASK["Задачи"]
    DEC --> PR
    DEC --> FTT
    TASK --> PMI
```

## Поведенческая Архитектура Использования

```mermaid
graph LR
    T["Рабочий вопрос"] --> A["Запрос к боту"]
    A --> R["Ответ с источниками"]
    R --> C["Доверие к инструменту"]
    C --> H["Повторное использование в следующей задаче"]
```

Это соответствует полезному продукту по `Hooked`, но без искусственной "аддиктивности". Повторяемость здесь строится на рабочей ценности.

## Архитектурные Границы

### Что Является Ядром

- corpus;
- retrieval;
- guard;
- context building;
- answer policy.

### Что Является Поверхностью

- CLI;
- API;
- будущий Open WebUI / web panel;
- отчеты и runbook.

### Что Является Расширением

- meeting integration;
- cross-document analyst mode;
- enriched traceability;
- future UI/timeline/explanations.

## Почему Такая Архитектура Правильна

Она позволяет:

- не смешивать шумный общий AI-чат с project-only продуктом;
- отдельно развивать corpus и answer surface;
- сначала стабилизировать `/search`, а потом строить `/chat`;
- позже подключить встречи, не ломая фундамент;
- держать продукт локальным и воспроизводимым.

## Ключевой Архитектурный Принцип

Интерфейс не должен быть "умнее" ядра.

Сначала должны быть стабильны:

1. corpus;
2. retrieval;
3. guard;
4. context semantics;
5. API;

и только потом chat/UI.
