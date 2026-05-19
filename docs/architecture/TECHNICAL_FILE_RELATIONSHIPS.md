# Диаграммы технических файлов MeetingAgent

Обновлено: 2026-05-19.

## 1. Карта технических контуров

```mermaid
flowchart TD
    Repo["MeetingAgent repo"] --> RootDocs["README / AGENTS / docs/context / docs/todo"]
    Repo --> RAGv1["Baseline RAG v1"]
    Repo --> Meetings["Meeting processing"]
    Repo --> Bot["Project Knowledge Bot"]
    Repo --> Quality["Quality / dataset pipeline"]

    RAGv1 --> RAGScripts["scripts/01..05, 04_query.py, rag_numpy_backend.py"]
    RAGv1 --> RAGData["data/manifest, extracted_text, chunks, embeddings_cache, numpy_index"]

    Meetings --> MeetingSchema["configs/schemas/meeting.schema.json"]
    Meetings --> MeetingScripts["scripts/06, 07, 08"]
    Meetings --> MeetingPrompts["configs/prompts/meeting_*.md"]
    Meetings --> MeetingDocs["docs/architecture/MEETING_ARTIFACTS_PIPELINE.md"]

    Bot --> BotSrc["src/asu_june_bot/*"]
    Bot --> BotScripts["scripts/asu_june_bot_*.py"]
    Bot --> BotDocs["docs/subprojects/asu-june-bot/*"]
    Bot --> BotEval["eval/cases + tests/asu_june_bot"]

    Quality --> QualityDocs["docs/quality/*"]
    Quality --> QualityScripts["scripts/10..14 + rag_common.py"]
    Quality --> RuntimeLogs["data/query_log*.jsonl"]
```

## 2. Baseline RAG v1: вызовы файлов

```mermaid
sequenceDiagram
    participant User as Пользователь
    participant Run as run_full_rag.ps1
    participant Inv as 01_inventory.py
    participant Ext as 02_extract_text.py
    participant Build as 03_build_index.py
    participant Numpy as 05_build_numpy_index.py
    participant Query as 04_query.py

    User->>Run: запуск полной сборки
    Run->>Inv: создать data/manifest.jsonl
    Run->>Ext: извлечь текст
    Run->>Build: chunks + embeddings_cache
    Run->>Numpy: numpy_index
    User->>Query: вопрос
    Query->>Numpy: top-k sources
    Query-->>User: compact/raw/LLM answer
```

## 3. Meeting pipeline: структура и поведение

```mermaid
stateDiagram-v2
    [*] --> new
    new --> transcribing: 06_transcribe_meeting.py
    transcribing --> transcribed: transcript + segments
    transcribed --> processing: 08_process_meeting_pipeline.py
    processing --> summarized: artifacts ready
    new --> failed
    transcribing --> failed
    processing --> failed
```

```mermaid
flowchart LR
    MeetingJson["meeting.json"] --> Schema["meeting.schema.json"]
    MeetingJson --> Source["source media"]
    Source --> Transcribe["06_transcribe_meeting.py"]
    Transcribe --> Segments["transcript/segments.jsonl"]
    Segments --> Pipeline["08_process_meeting_pipeline.py"]
    Pipeline --> Partials["artifacts/_partials/window_*.json"]
    Partials --> FinalJson["decisions/tasks/risks/open_questions.json"]
    FinalJson --> Markdown["memo.md / protocol.md"]
```

## 4. Quality pipeline: query -> review -> candidates

```mermaid
flowchart TD
    Q1["04_query.py"] --> Log["data/query_log.jsonl"]
    Q2["09_chat.py legacy"] --> Log
    Log --> Review["10_review_queries.py"]
    Review --> ReviewFile["data/query_log_review.jsonl"]
    ReviewFile --> Candidates["13_build_eval_candidates.py"]
    Candidates --> CandidateFile["data/eval_candidates.jsonl"]
    CandidateFile --> Approval["ручное утверждение"]
    Approval --> Regression["постоянный regression/eval corpus"]

    Seed["docs/quality/synthetic_seed_queries.jsonl"] --> SeedRun["11_run_synthetic_seed.py"]
    SeedRun --> SeedReport["data/synthetic_seed_report.jsonl"]
    SeedReport --> SeedAnalysis["12_analyze_seed_report.py"]
    SeedAnalysis --> SeedSummary["data/synthetic_seed_summary.md"]

    Realistic["docs/quality/realistic_100_queries.jsonl"] --> RealRun["14_run_realistic_100_eval.py"]
    RealRun --> RealReport["data/realistic_100_eval_report.jsonl"]
```

## 5. Объектная модель ключевых JSON/JSONL

```mermaid
classDiagram
    class MeetingJson {
      string meeting_id
      string processing_status
      object source
      object artifacts
      object retention
      object rag
    }

    class Segment {
      float start
      float end
      string text
      string source
    }

    class QueryLog {
      string ts
      string source
      string question
      string status
      array top_sources
      object params
    }

    class ReviewRow {
      string query_id
      string review_verdict
      string review_comment
    }

    class EvalCandidate {
      string id
      string query
      string expected_behavior
      array expected_sources
    }

    MeetingJson --> Segment
    QueryLog --> ReviewRow
    ReviewRow --> EvalCandidate
```

## 6. Что не смешивать

| Контур | Канонические файлы | Не считать основным runtime |
| --- | --- | --- |
| MeetingAgent RAG v1 | `scripts/01..05`, `04_query.py`, `data/numpy_index/` | ChromaDB / `vector_db/` |
| Project Knowledge Bot | `src/asu_june_bot/`, `scripts/asu_june_bot_*.py` | `scripts/09_chat.py` |
| Meeting artifacts | `06_transcribe_meeting.py`, `08_process_meeting_pipeline.py`, `meeting.schema.json` | `07_generate_meeting_artifacts.py extractive` как финальный генератор |
| Quality pipeline | `docs/quality/*`, `scripts/10..14` | fine-tuning / auto-promotion |
