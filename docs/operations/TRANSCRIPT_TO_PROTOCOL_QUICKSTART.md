# Transcript to protocol quickstart

This guide shows the shortest reproducible path from transcript segments to meeting protocol artifacts.

It uses only the public synthetic dataset from `examples/meeting_dataset/`. Real customer transcripts, recordings, runtime meeting cards and generated artifacts must stay local and must not be committed.

## Synthetic demo

Start from a clean checkout:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c constraints-py312.txt -r requirements.txt
```

Create a local runtime copy of the public sample:

```powershell
$sample = "examples\meeting_dataset\synthetic-support-handoff"
$meeting = "meetings\2026-01-15__synthetic-support-handoff"

Remove-Item -Recurse -Force $meeting -ErrorAction SilentlyContinue
Copy-Item -Recurse $sample $meeting

$card = Get-Content "$meeting\meeting.json" -Encoding UTF8 | ConvertFrom-Json
$card.processing_status = "processing"
$card.artifacts = @{}
$card.rag = @{ index_policy = "do_not_index" }
$card | ConvertTo-Json -Depth 32 | Set-Content "$meeting\meeting.json" -Encoding UTF8
```

Import the transcript segments into the canonical transcript contract:

```powershell
.\.venv\Scripts\python.exe scripts\22_transcribe_meeting.py `
  --meeting-dir $meeting `
  --engine from-segments `
  --segments-path "$sample\transcript\segments.jsonl" `
  --language en `
  --force
```

Create a speaker transcript. The public sample does not include diarization input for this run, so speakers are assigned as `SPEAKER_UNKNOWN`; this is acceptable for the shortest quickstart.

```powershell
.\.venv\Scripts\python.exe scripts\24_merge_transcript_speakers.py `
  --meeting-dir $meeting `
  --force
```

Build meeting chunks:

```powershell
.\.venv\Scripts\python.exe scripts\26_chunk_meeting.py `
  --meeting-dir $meeting `
  --force
```

Enrich chunks with deterministic heuristics:

```powershell
.\.venv\Scripts\python.exe scripts\27_enrich_meeting_chunks.py `
  --meeting-dir $meeting `
  --force
```

Generate summary, protocol and structured artifacts without an LLM:

```powershell
.\.venv\Scripts\python.exe scripts\29_analyze_meeting.py `
  --meeting-dir $meeting `
  --mode extractive `
  --force
```

Expected output paths:

```text
meetings/2026-01-15__synthetic-support-handoff/
  transcript/segments.jsonl
  transcript/transcript.md
  transcript/speaker_transcript.jsonl
  transcript/chunks.jsonl
  artifacts/enriched_chunks.jsonl
  artifacts/summary.md
  artifacts/protocol.md
  artifacts/decisions.json
  artifacts/tasks.json
  artifacts/risks.json
  artifacts/open_questions.json
```

Open the protocol:

```powershell
Get-Content "$meeting\artifacts\protocol.md" -Encoding UTF8
```

## Real private transcript

For a real transcript, use the same stages, but keep all inputs and outputs under ignored local runtime folders:

```powershell
.\.venv\Scripts\python.exe scripts\22_transcribe_meeting.py `
  --meeting-dir "meetings\<your-meeting-id>" `
  --engine from-segments `
  --segments-path "<local-private-path>\segments.jsonl" `
  --language ru
```

Then run:

```powershell
.\.venv\Scripts\python.exe scripts\24_merge_transcript_speakers.py --meeting-dir "meetings\<your-meeting-id>"
.\.venv\Scripts\python.exe scripts\26_chunk_meeting.py --meeting-dir "meetings\<your-meeting-id>"
.\.venv\Scripts\python.exe scripts\27_enrich_meeting_chunks.py --meeting-dir "meetings\<your-meeting-id>"
.\.venv\Scripts\python.exe scripts\29_analyze_meeting.py --meeting-dir "meetings\<your-meeting-id>" --mode extractive
```

Use `--mode ollama-map-reduce` only when local Ollama is running and the configured chat model is available.

## Privacy boundary

- `examples/meeting_dataset/` is tracked public synthetic data.
- `meetings/`, `data/`, `logs/`, indexes, model caches and real transcripts are runtime/private data.
- Before turning any local transcript into a public example, run `scripts/43_anonymize_transcript.py` and manually review the result.
