# Архитектура

[English](../en/architecture.md) | [Русский](architecture.md)

MeetingAgent объединяет четыре runtime-зоны:

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

## Local-First Граница

Private project data по умолчанию остаётся локально. Внешние providers можно использовать для явных экспериментов, но local runtime files, corpora, transcripts, indexes и credentials нельзя коммитить.

## Подробная Архитектура

- [Architecture index](../architecture/ARCHITECTURE.md)
- [MeetingAgent architecture](../meeting_agent_architecture.md)
- [Project Knowledge Bot](../project_knowledge_bot.md)
