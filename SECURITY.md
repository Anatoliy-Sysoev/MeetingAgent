# Security Policy

[English](SECURITY.md) | [Русский](SECURITY.ru.md)

MeetingAgent is a local-first project memory and meeting intelligence tool. It may process private project documents, meeting transcripts, local indexes, generated artifacts, API keys, and model provider credentials. Treat security and privacy issues as high priority.

## Reporting A Vulnerability

Do not open a public GitHub issue for vulnerabilities, leaked secrets, or private-data exposure.

Report security issues directly to the maintainer through a private channel. If no private channel is available, open a minimal public issue that says a private security report is needed, without including exploit details, tokens, file contents, transcripts, or customer-specific data.

Please include:

- affected version or commit;
- affected command, API route, script, or workflow;
- reproduction steps using synthetic data where possible;
- expected impact;
- suggested mitigation, if known.

## Security-Sensitive Areas

Changes in these areas require extra review:

- local file ingestion and path handling;
- transcript parsing and meeting artifact generation;
- RAG chunking, indexing, retrieval, and source citation logic;
- API keys, `.env` files, provider credentials, and model endpoints;
- export formats such as Markdown, DOCX, JSON, JSONL, SRT, and VTT;
- Telegram, Web UI, FastAPI, Docker, and external model integrations;
- prompt/tool boundaries, guardrails, and out-of-scope request handling;
- generated runtime data under `data/`, `logs/`, `meetings/`, `vector_db/`, and `watched_folder/`.

## Local-First Data Handling

The default architecture is local-first:

- project documents and meeting files should stay on the user's machine;
- runtime outputs are not committed to Git;
- customer-specific corpora and private transcripts must not be published;
- `.env`, `config.yaml`, logs, vector indexes, local caches, and media files are ignored or treated as local-only data.

Before sharing a bug report, test artifact, or pull request, remove or anonymize private names, paths, meeting content, URLs, credentials, and internal identifiers.

## Dependency And Model Provider Risk

MeetingAgent can use local and external model providers. Review provider configuration carefully:

- never commit API keys or access tokens;
- prefer environment variables or local `.env` files for credentials;
- document whether a workflow sends text to an external provider;
- avoid sending private transcripts or customer documents to hosted models unless the user explicitly chooses that mode.

## Maintainer Checklist

Before merging security-sensitive changes:

- run relevant tests and smoke checks;
- inspect new file reads/writes and path handling;
- verify no secrets or runtime data are staged;
- update documentation when behavior affects data handling;
- keep guardrails conservative for unsafe, mixed-scope, or out-of-project requests.
