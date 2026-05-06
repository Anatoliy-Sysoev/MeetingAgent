# Folder Structure

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

## Notes

- `scripts/` contains current working automation.
- `src/meeting_agent/` is the future package structure.
- `apps/` will contain product surfaces.
- `data/`, `logs/`, `vector_db/`, and `watched_folder/` are local runtime folders and are ignored by git.

