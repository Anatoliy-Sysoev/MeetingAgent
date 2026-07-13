# Структура Папок

Текущее дерево отражает только реализованные или явно совместимые контуры.
Каноническая классификация packages/scripts хранится в
`configs/runtime_inventory.yaml` и проверяется тестами.

```text
MeetingAgent/
  .github/
    workflows/                  CI, audit, release и docs workflows
  configs/
    asu_june_bot/               публичные default + ignored local overlays
    prompts/                    используемые prompt templates
    schemas/                    meeting и structured artifact schemas
    runtime_inventory.yaml      current/compatibility ownership inventory
  data/                         ignored runtime data
  docs/                         architecture, operations, security, quality
  eval/                         публичные synthetic eval cases
  examples/                     public-safe examples
  logs/                         ignored runtime logs/state
  meetings/                     meeting cards; реальные карточки ignored
  scripts/                      current и compatibility entrypoints/tools
  src/
    asu_june_bot/               optional Project Knowledge Bot + integrated app
      api/ chat/ retrieval/ search/ guardrails/ ...
      core/ llm/ auth/ jobs/ meetings/ compatibility shims
    meeting_agent/
      api/                      independent core API/UI
      auth/ jobs/ meetings/     local security и meeting lifecycle
      live_sessions/            durable live capture lifecycle
      transcription/            canonical offline ASR contract/backends
      diarization/              optional sherpa-onnx diarization
      live_transcription/       optional draft live helpers
      evaluation/               meeting artifact evaluation
      shared/                   shared config/security/LLM utilities
  tests/                        unit, API, e2e и regression tests
  vector_db/                    ignored legacy Chroma runtime path
  watched_folder/               ignored local input path
```

## Пояснения

- Поддерживаемые public entrypoints и migration paths описаны в
  `docs/ru/runtime_ownership.md`.
- `scripts/meeting_agent_api.py` запускает core отдельно;
  `src/asu_june_bot/api` остаётся integrated bridge и добавляет PKB routes.
  Следующие product-split phases описаны в `PRODUCT_BOUNDARIES.md`.
- `data/`, `logs/`, `meetings/`, `vector_db/` и `watched_folder/` не являются
  source tree для приватных runtime outputs.
- Пустые `apps/*`, `templates/*` и placeholder packages удалены. Новая папка
  появляется только вместе с работающим кодом, тестами и ownership.
- `configs/schemas/meeting.schema.json` является формальным контрактом
  `meeting.json`.
