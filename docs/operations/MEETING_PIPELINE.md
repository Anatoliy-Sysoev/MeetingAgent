# Meeting Pipeline

## Goal

Turn every meeting recording into reusable project knowledge.

## Target Flow

1. New video/audio appears in `watched_folder/`.
2. Watcher waits until the file is stable.
3. Transcription runs with Whisper-compatible model.
4. Transcript is saved with timestamps.
5. AI generates:
   - short memo;
   - formal protocol;
   - decisions;
   - action items;
   - risks;
   - open questions.
6. RAG classifies relation to:
   - project stage;
   - FTT;
   - task;
   - deliverable;
   - existing document.
7. Artifacts are saved into a meeting-card folder.
8. Transcript and generated artifacts are added to RAG.

## Meeting Card

Each processed meeting should have:

- original media reference;
- transcript;
- memo;
- protocol;
- decisions;
- tasks;
- classification metadata;
- source links to related project documents.

## Later Enhancements

- speaker diarization;
- speaker profiles;
- transcript-player synchronization;
- manual correction UI;
- export to DOCX/Markdown.

