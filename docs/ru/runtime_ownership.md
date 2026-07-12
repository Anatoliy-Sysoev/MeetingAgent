# Границы Runtime И Entrypoints

[English](../en/runtime_ownership.md) | [Русский](runtime_ownership.md)

## Канонический Inventory

`configs/runtime_inventory.yaml` является machine-checked source of truth для
каждого Python package и каждого `.py`/`.ps1` в `scripts/`. Каждый path имеет
статус `current`, `compatibility` или `planned`. Удалённые пустые scaffolds
записаны отдельно. CI падает, если новый path не классифицирован или указан в
нескольких категориях.

## Владение Продуктом

| Область | Владелец | Статус |
|---|---|---|
| `meeting_agent.transcription` | MeetingAgent Core | Канонический offline ASR contract |
| `meeting_agent.diarization` | MeetingAgent Core | Optional speaker diarization |
| `meeting_agent.live_transcription` | MeetingAgent Core | Optional draft live helpers |
| `meeting_agent.evaluation` | MeetingAgent Core | Evaluation meeting artifacts |
| `meeting_agent.shared` | Shared | Config, limits, path safety, JSONL, hashing, prompt safety, LLM clients |
| `asu_june_bot.api/auth/jobs/meetings` | Integrated runtime | MeetingAgent API/UI и local security |
| `asu_june_bot.chat/retrieval/search/guardrails` | Project Knowledge Bot | Project-memory assistant |
| `asu_june_bot.core`, `asu_june_bot.llm` | Compatibility | Import shims поверх `meeting_agent.shared` |

Интегрированное HTTP-приложение остаётся в `asu_june_bot.api`, пока
задокументированные product-split phases не перенесут MeetingAgent-owned routes.
Текущее размещение не делает meeting processing частью бота.

## Поддерживаемые Public Entrypoints

- API/UI: `scripts/asu_june_bot_api.py`;
- project chat/search: `scripts/asu_june_bot_chat.py` и
  `scripts/asu_june_bot_search_v2.py`;
- Telegram adapter: `scripts/asu_june_bot_telegram.py`;
- meeting pipeline: `scripts/20_ingest_meeting.py`, затем `21`, `22`, `23`,
  `24`, `26`, `27`, `28` и `29` по необходимости;
- meeting search/index: `31_meeting_search.py` и
  `32_index_meeting_artifacts.py`;
- optional draft live transcription: `33_live_transcribe_meeting.py`;
- verification: `42_local_preflight.py`, `46_ci_verify.py`,
  `47_dependency_audit.py` и `48_retrieval_coverage.py`.

Inventory задаёт точный список CLI `--help` smoke. Тесты запускают эти команды
в subprocess без сети и model calls.

## Compatibility И Миграция

V1 RAG/evaluation scripts `01_*` ... `18_*` остаются запускаемыми только для
локальной миграции и исторической воспроизводимости. Новая продуктовая
разработка на них не ведётся. Compatibility entrypoint печатает замену и ссылку
на этот guide. Для существующей unattended automation warning можно временно
скрыть через `MEETINGAGENT_SUPPRESS_LEGACY_WARNING=1`.

| Compatibility path | Текущая замена |
|---|---|
| `01_inventory.py`, `02_extract_text.py` | `asu_june_bot_extract_text_v2.py` + `asu_june_bot_build_chunks_v2.py` |
| `03_build_index.py`, `04_build_fts_index.py`, `05_build_numpy_index.py` | `asu_june_bot_build_index_v2.py` |
| `04_query.py`, `asu_june_bot_search.py` | `asu_june_bot_search_v2.py` |
| `06_transcribe_meeting.py` | `22_transcribe_meeting.py` |
| `07_generate_meeting_artifacts.py` | `29_analyze_meeting.py` |
| `08_process_meeting_pipeline.py` | `POST /meetings/{id}/jobs/pipeline` |
| `09_chat.py` | `asu_june_bot_chat.py` |
| legacy review/eval scripts | Review API, guard-case exporter и current eval CLIs |

Retained compatibility paths используют product defaults. Offline
faster-whisper по умолчанию работает на `large-v3-turbo`; `small` доступен
только как явный draft/dev CLI choice.

## Удалённые Scaffolds

Удалены пустые `apps/*`, `templates/*`, unused placeholder packages внутри
`meeting_agent`, а также пустые `tests/integration` и `tests/evaluation`. У них
не было runtime contract или committed near-term implementation. Возвращать
директорию можно только вместе с рабочим кодом, тестами, ownership и docs.
Также удалён сломанный wrapper `set_asu_june_bot_project_root.ps1`: его target
script не существовал; local configuration задаётся через ignored YAML overlays.
