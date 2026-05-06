# Roadmap

## Phase 0 - Stabilize Local RAG

Status: in progress.

- Finish full project index.
- Validate embedding cache resume behavior.
- Verify ChromaDB collection count.
- Add RAG query smoke tests.
- Document operational recovery steps.

## Phase 1 - Project Search

- Improve `scripts/04_query.py` output with source citations.
- Add source previews and chunk metadata.
- Add evaluation questions for FTT, architecture, Passport IS, and delivery docs.
- Create query templates for common project roles.

## Phase 2 - Meeting Processing

- Watch incoming media folder.
- Transcribe video/audio.
- Generate transcript with timestamps.
- Generate memo, protocol, decisions, risks, and tasks.
- Create meeting-card folder per recording.
- Link meeting content to RAG sources.

## Phase 3 - Classification

- Classify every document and meeting by:
  - project stage;
  - FTT section;
  - deliverable;
  - task;
  - decision/risk/action type.
- Store classification metadata.
- Add manual override and correction flow.

## Phase 4 - Document Generation

- Create generation briefs and templates:
  - Passport IS;
  - FTT summary;
  - project solution;
  - architecture note;
  - meeting protocol;
  - delivery checklist.
- Generate drafts with source citations.
- Export to Markdown and DOCX.

## Phase 5 - Local Product UI

- Add local API.
- Add inbox/status screen.
- Add project search UI.
- Add meeting-card view.
- Add document generation flow.

## Phase 6 - Quality and Governance

- Add regression evaluation dataset.
- Track retrieval quality.
- Track generation quality.
- Add retention policies.
- Add protected records.
- Add backup/export workflow.

