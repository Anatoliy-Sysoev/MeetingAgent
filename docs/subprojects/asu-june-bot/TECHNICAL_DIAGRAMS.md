# Технические диаграммы Project Knowledge Bot

Обновлено: 2026-05-19.

## 1. Диаграмма компонентов

```mermaid
flowchart TD
    User["Пользователь"] --> Entrypoints["CLI / FastAPI / Web UI / Telegram"]
    Entrypoints --> API["src/asu_june_bot/api"]
    Entrypoints --> CLIScripts["scripts/asu_june_bot_*.py"]

    API --> SearchService["search/service.py"]
    CLIScripts --> SearchService
    API --> ChatService["chat/service.py"]
    CLIScripts --> ChatService

    SearchService --> Guard["guardrails/project_guard.py"]
    SearchService --> Retrieval["retrieval/*"]
    Retrieval --> BM25["bm25.py"]
    Retrieval --> Vector["vector.py"]
    Retrieval --> Hybrid["hybrid.py"]
    Retrieval --> Context["context_builder.py"]
    Context --> SourceQuality["source_quality.py"]
    Context --> ParentExpansion["parent_expansion.py"]

    ChatService --> Prompt["prompt_builder.py"]
    ChatService --> LLM["llm/ollama_openai.py"]
    ChatService --> Validator["answer_validator.py"]
    ChatService --> Warnings["semantic_warnings.py"]
    ChatService --> Formatter["response_formatter.py"]
    ChatService --> Runs["observability/chat_runs.py"]

    Health["health/service.py"] --> API
    QH["qh/release_gate.py"] --> Tests["tests/asu_june_bot/*"]
```

## 2. Диаграмма вызова `/chat`

```mermaid
sequenceDiagram
    participant Client as CLI/API/UI/Telegram
    participant Chat as ChatService
    participant Search as SearchService
    participant Guard as ProjectGuard v2
    participant Context as ContextBuilder
    participant LLM as Ollama LLM
    participant Validator as AnswerValidator
    participant Log as ChatRunsLogger

    Client->>Chat: question
    Chat->>Search: search request
    Search->>Guard: classify scope
    alt refused or clarify
        Guard-->>Search: decision
        Search-->>Chat: no retrieval / no LLM
        Chat->>Log: write run
        Chat-->>Client: refusal or clarification
    else allow
        Guard-->>Search: allow
        Search->>Context: BM25 + vector + rerank + buckets
        Context-->>Search: primary/supporting/excluded sources
        Search-->>Chat: context
        Chat->>LLM: prompt with sources
        LLM-->>Chat: answer
        Chat->>Validator: structural checks
        Chat->>Log: write run and diagnostics
        Chat-->>Client: answer with citations
    end
```

## 3. Диаграмма технических файлов

```mermaid
flowchart LR
    Config["config.yaml / configs/asu_june_bot/*.yaml"] --> Ingest["asu_june_bot_extract_text_v2.py"]
    Ingest --> Blocks["data/asu_june_bot/extracted_v2/blocks.jsonl"]
    Blocks --> ChunksScript["asu_june_bot_build_chunks_v2.py"]
    ChunksScript --> Chunks["data/asu_june_bot/chunks_v2.jsonl"]
    Chunks --> IndexScript["asu_june_bot_build_index_v2.py"]
    IndexScript --> Cache["embeddings_cache_v2.jsonl"]
    IndexScript --> Index["numpy_index_v2/"]

    Index --> Vector["src/asu_june_bot/retrieval/vector.py"]
    Chunks --> BM25["src/asu_june_bot/retrieval/bm25.py"]
    Vector --> Hybrid["hybrid.py"]
    BM25 --> Hybrid
    Hybrid --> Search["src/asu_june_bot/search/service.py"]
    Search --> Chat["src/asu_june_bot/chat/service.py"]
    Chat --> API["src/asu_june_bot/api/app.py"]
    Chat --> CLI["scripts/asu_june_bot_chat.py"]
    API --> Telegram["scripts/asu_june_bot_telegram.py"]
```

## 4. Структурная диаграмма пакета

```mermaid
flowchart TD
    Src["src/asu_june_bot"] --> Core["core: config, limits"]
    Src --> Ingestion["ingestion: models, utils"]
    Src --> Retrieval["retrieval: chunks, bm25, vector, hybrid, context"]
    Src --> Guardrails["guardrails: segmenter, classifier, policy"]
    Src --> Search["search: request/response models, service"]
    Src --> Chat["chat: prompt, validation, formatting, warnings"]
    Src --> LLM["llm: local Ollama client"]
    Src --> API["api: FastAPI routes, errors, middleware"]
    Src --> Observability["observability: chat runs"]
    Src --> Eval["eval: cases, runner, reports"]
    Src --> QH["qh: release gate"]
    Src --> Telegram["telegram_bot.py"]
```

## 5. Объектная модель runtime

```mermaid
classDiagram
    class SearchRequest {
      question
      mode
      top_k
    }
    class SearchResponse {
      status
      context
      diagnostics
    }
    class ContextBucket {
      primary_sources
      supporting_sources
      excluded_sources
    }
    class ChatRequest {
      question
      model
      max_tokens
    }
    class ChatResponse {
      status
      answer
      sources
      warnings
    }
    class GuardDecision {
      decision
      reason
      segments
    }
    class ChatRun {
      ts
      question
      status
      diagnostics
      manual_label
    }

    SearchRequest --> GuardDecision
    SearchRequest --> SearchResponse
    SearchResponse --> ContextBucket
    ChatRequest --> SearchRequest
    ChatResponse --> ContextBucket
    ChatResponse --> ChatRun
```

## 6. Поведенческая диаграмма QH-гейта

```mermaid
stateDiagram-v2
    [*] --> Implemented
    Implemented --> LocalSmoke: tests + API + UI smoke
    LocalSmoke --> TelegramSmoke: Telegram token/chat id available
    LocalSmoke --> Pending: Telegram smoke skipped
    TelegramSmoke --> EvalCompared: after_qh eval + baseline comparison
    EvalCompared --> Passed: qh_gate --local-validation-done --baseline-compared
    Pending --> LocalSmoke: resume validation
    Passed --> DockerReady
```

## 7. Quality feedback loop

```mermaid
flowchart TD
    ChatRuns["data/asu_june_bot/chat_runs.jsonl"] --> Review["manual review"]
    Review --> Labels["manual_label / manual_issue"]
    Labels --> EvalCases["eval/cases/*.jsonl"]
    EvalCases --> EvalRun["scripts/asu_june_bot_chat_eval.py"]
    EvalRun --> Reports["eval/reports/*.md"]
    Reports --> Improvements["retrieval / guardrails / context changes"]
    Improvements --> Tests["tests/asu_june_bot/*"]
    Tests --> ChatRuns
```

## 8. Правило ответственности файлов

| Задача | Основные файлы |
| --- | --- |
| Сбор корпуса | `asu_june_bot_extract_text_v2.py`, `asu_june_bot_build_chunks_v2.py` |
| Индексация | `asu_june_bot_build_index_v2.py`, `retrieval/vector.py`, `retrieval/bm25.py` |
| Поиск | `search/service.py`, `asu_june_bot_search_v2.py`, `routes_search.py` |
| Project-only guard | `guardrails/*`, `tests/asu_june_bot/test_project_guard_v2*.py` |
| Ответ с citations | `chat/service.py`, `prompt_builder.py`, `answer_validator.py` |
| API/UI | `api/app.py`, `routes_*.py`, `routes_ui.py` |
| Telegram | `telegram_bot.py`, `scripts/asu_june_bot_telegram.py` |
| QH/eval | `eval/*`, `qh/release_gate.py`, `tests/asu_june_bot/qh/*` |
