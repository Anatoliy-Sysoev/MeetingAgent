# Sample Meeting Protocol

[English](sample_protocol.md) | [Русский](../ru/sample_protocol.md)

Synthetic public output example based on `sample_transcript.md`.

## 1. General Information

- Title: Weekly Project Sync
- Date: 2026-06-01
- Source: `examples/en/sample_transcript.md`

## 2. Participants

- Analyst
- Developer
- Project Manager

## 3. Summary

The team agreed on the initial document ingestion scope, identified a source-reference quality risk, and assigned a DOCX extraction smoke test.

## 4. Decisions

- DOCX and PDF processing are required for the first release; XLSX remains optional. Source: `[00:00:38]`

## 5. Action Items

- Developer: add a DOCX extraction smoke test and update the quickstart. Source: `[00:00:26]`

## 6. Risks

- Generated summaries should not be accepted when source references are missing. Source: `[00:00:50]`

## 7. Open Questions

- Should Telegram be enabled in the default Docker profile? Source: `[00:01:04]`
