# Работа Агентов

[English](../en/agents.md) | [Русский](agents.md)

MeetingAgent использует agent-like workflows как продуктовые компоненты и maintainer workflows. Текущий runtime не требует multi-agent framework; роли ниже описывают зоны ответственности и review boundaries.

## Product Workflows

- Transcript Processor: нормализует транскрипты встреч и time-coded segments.
- Meeting Summarizer: создаёт source-grounded meeting summaries.
- Decision Extractor: извлекает решения с source references.
- Action Item Extractor: извлекает owners, tasks, due dates и timestamps.
- Risk Extractor: извлекает risks и uncertainty markers.
- Citation Validator: проверяет, что generated claims ссылаются на доступные sources.
- Project Search Assistant: ищет evidence и отвечает только по источникам.

## Maintainer Workflows

- Codex PR Reviewer: проверяет diffs, tests, docs и security-sensitive areas.
- Issue Triage Agent: классифицирует issues как bug, docs, feature, eval или security-sensitive work.
- Release Notes Agent: собирает merged changes для changelogs и releases.
- Security Review Agent: проверяет file handling, secrets, model providers, exports и guardrails.

## Security-Sensitive Areas

- Local files и path handling.
- Meeting transcripts и generated artifacts.
- API keys и external model providers.
- Export formats.
- Tool/prompt boundaries.
- Telegram, Web UI, FastAPI и Docker integrations.
