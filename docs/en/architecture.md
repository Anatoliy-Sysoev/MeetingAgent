# Architecture

[English](architecture.md) | [Русский](../ru/architecture.md)

MeetingAgent combines four runtime areas:

```text
MeetingAgent Core
  -> local document and meeting processing

Project Knowledge Bot
  -> source-grounded project search/chat

Quality Pipeline
  -> eval datasets, targeted checks, regression reports

Integrations
  -> FastAPI, Web UI, Telegram adapter, Docker
```

## Core Data Flow

```text
documents / audio / video
  -> extraction / transcription
  -> chunking
  -> indexing
  -> retrieval
  -> source-grounded generation
  -> artifacts and quality reports
```

## Local-First Boundary

Private project data stays local by default. External providers can be used for explicit experiments, but local runtime files, corpora, transcripts, indexes, and credentials must not be committed.

## Detailed Architecture

- [Architecture index](../architecture/ARCHITECTURE.md)
- [MeetingAgent architecture](../meeting_agent_architecture.md)
- [Project Knowledge Bot](../project_knowledge_bot.md)
