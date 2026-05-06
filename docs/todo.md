# Todo

Last updated: 2026-05-06.

## Now

- Let the current RAG build continue.
- Monitor `data/embeddings_cache.jsonl` growth and watchdog output.
- After completion, verify the done marker and ChromaDB collection count.
- Run smoke queries against the finished RAG index.

## Next

- Improve `scripts/04_query.py` output with compact source citations.
- Add a small RAG evaluation question set.
- Add an incremental `update_rag.ps1` flow for new, changed, and removed documents.
- Add a first meeting ingestion script for files appearing in `watched_folder/`.

## Product Next

- Define the meeting-card artifact structure.
- Create prompt templates for memo, protocol, decisions, risks, tasks, and classification.
- Add document-generation briefs for Passport IS, FTT extracts, architecture notes, and protocols.
- Design a minimal local API surface.

## Later

- Add local web UI.
- Add speaker diarization.
- Add manual classification corrections.
- Add DOCX export.
- Add retention/protected-record policies.

## Known Risks

- Full RAG build is long-running and depends on Ollama stability.
- Some spreadsheet files have extraction errors due to non-standard stylesheets.
- Query quality is not validated until the index is complete.
- Generated documents need strict source citation review.

