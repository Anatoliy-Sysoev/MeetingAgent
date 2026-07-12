# MeetingAgent Documentation

[English](en/index.md) | [Русский](ru/index.md)

MeetingAgent is a local-first open-source tool for meeting intelligence and project memory.

Use this documentation site for browsable public docs. The repository `README.md` remains the primary GitHub landing page, and all Markdown files remain readable directly on GitHub.

## Start

- [English documentation](en/index.md)
- [Русская документация](ru/index.md)
- [Meeting pipeline](operations/MEETING_PIPELINE.md)
- [Transcript to protocol quickstart](operations/TRANSCRIPT_TO_PROTOCOL_QUICKSTART.md)
- [API and Auth Setup](en/API_AUTH_SETUP.md)

## Build Locally

```powershell
.\.venv\Scripts\python.exe -m pip install -c constraints-py312.txt -r requirements-docs.txt
.\.venv\Scripts\python.exe -m mkdocs build
```

The generated static site is written to ignored `site/`.
