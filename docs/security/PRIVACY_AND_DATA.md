# Privacy And Data

MeetingAgent is designed as a local-first product.

## Sensitive Data

Project documents, transcripts, protocols, and generated documents may contain confidential project information.

## Repository Rules

Do not commit:

- `.venv/`;
- `config.yaml`;
- `data/`;
- `logs/`;
- `vector_db/`;
- `watched_folder/`;
- raw media files;
- generated transcripts or protocols from real projects.

Commit only:

- source code;
- templates;
- documentation;
- example configuration;
- synthetic test data.

## Local Model Policy

Default processing should use local Ollama and local Whisper-compatible models.

Any cloud integration must be explicit, documented, and disabled by default.

