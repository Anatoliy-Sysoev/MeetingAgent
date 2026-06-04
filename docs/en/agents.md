# Agent Workflows

[English](agents.md) | [Русский](../ru/agents.md)

MeetingAgent uses agent-like workflows as product components and maintainer workflows. The current repository does not require a multi-agent framework for runtime orchestration; these roles describe responsibilities and review boundaries.

## Product Workflows

- Transcript Processor: normalizes meeting transcripts and time-coded segments.
- Meeting Summarizer: creates source-grounded meeting summaries.
- Decision Extractor: extracts decisions with source references.
- Action Item Extractor: extracts owners, tasks, due dates, and timestamps.
- Risk Extractor: extracts risks and uncertainty markers.
- Citation Validator: checks that generated claims reference available sources.
- Project Search Assistant: retrieves project evidence and answers only from sources.

## Maintainer Workflows

- Codex PR Reviewer: checks diffs, tests, docs, and security-sensitive areas.
- Issue Triage Agent: classifies issues into bug, docs, feature, eval, or security-sensitive work.
- Release Notes Agent: summarizes merged changes for changelogs and releases.
- Security Review Agent: reviews file handling, secrets, model providers, exports, and guardrails.

## Security-Sensitive Areas

- Local files and path handling.
- Meeting transcripts and generated artifacts.
- API keys and external model providers.
- Export formats.
- Tool/prompt boundaries.
- Telegram, Web UI, FastAPI, and Docker integrations.
