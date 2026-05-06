# Структура Папок

```text
MeetingAgent/
  .github/
    workflows/
  apps/
    api/
    cli/
    desktop/
    web/
  configs/
    prompts/
    schemas/
  data/
  docs/
    architecture/
    operations/
    product/
    quality/
    references/
    security/
    templates/
  logs/
  scripts/
  src/
    meeting_agent/
      api/
      classification/
      config/
      core/
      document_generation/
      extraction/
      ingest/
      integrations/
      meetings/
      observability/
      rag/
      storage/
      transcription/
  templates/
    documents/
    meetings/
    prompts/
  tests/
    evaluation/
    integration/
    unit/
  vector_db/
  watched_folder/
```

## Пояснения

- `scripts/` содержит текущую рабочую автоматизацию.
- `src/meeting_agent/` - будущая структура Python-пакета.
- `apps/` - будущие продуктовые интерфейсы.
- `data/`, `logs/`, `vector_db/` и `watched_folder/` - локальные runtime-папки, которые игнорируются Git.

