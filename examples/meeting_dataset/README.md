# Public Synthetic Meeting Dataset

This folder contains a small synthetic meeting dataset for documentation, demos, tests, and benchmarks.

The dataset is safe to publish:

- no real customer names;
- no private project names;
- no local filesystem paths;
- no tokens, logs, recordings, or runtime indexes;
- no real transcripts.

## Dataset

```text
synthetic-support-handoff/
  meeting.json
  transcript/
    segments.jsonl
    speaker_transcript.jsonl
    transcript.md
  artifacts/
    summary.md
    protocol.md
    decisions.json
    tasks.json
    risks.json
    open_questions.json
```

The sample demonstrates the artifact contract expected by MeetingAgent:

- transcript segments with timestamps;
- speaker-labelled utterances;
- summary and protocol markdown;
- structured decisions, tasks, risks and open questions;
- source refs with timestamps and speaker refs.

Do not commit real customer transcripts or runtime meeting cards. Use `scripts/43_anonymize_transcript.py` before preparing any public sample derived from local data, then review manually.
