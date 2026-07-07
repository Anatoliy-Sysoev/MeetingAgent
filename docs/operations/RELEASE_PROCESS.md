# Release process

This document defines the repeatable public OSS release process for MeetingAgent.

## Release Inputs

- `pyproject.toml` version;
- `CHANGELOG.md`;
- `CHANGELOG.ru.md`;
- green CI on `main`;
- no private runtime data staged or committed.

## Checklist

1. Pick the release version, for example `0.1.1`.
2. Update `pyproject.toml` if the package version changes.
3. Add matching sections to both changelogs:

```markdown
## v0.1.1

Short release summary.

### Added

- ...

### Changed

- ...

### Fixed

- ...

### Security

- ...
```

Russian changelog uses the same version heading and localized section names:

```markdown
## v0.1.1

Краткое описание релиза.

### Добавлено

- ...

### Изменено

- ...

### Исправлено

- ...

### Безопасность

- ...
```

Only include sections that have content. The validator currently requires `Added` / `Добавлено` for the release being checked, because the current public release format starts from the initial OSS foundation.

4. Validate changelogs locally:

```powershell
.\.venv\Scripts\python.exe scripts\45_validate_release_notes.py --version 0.1.0
```

5. Run full tests locally:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
git diff --check
```

6. Confirm `git status --short` does not contain private/runtime files:

```text
data/
logs/
meetings/
vector_db/
watched_folder/
models/
.env
config.yaml
*.private.json
```

7. Run GitHub Actions `Release Validation` manually with the target version.
8. Create a Git tag after validation passes:

```powershell
git tag v0.1.0
git push origin v0.1.0
```

9. Create GitHub Release notes from the matching `CHANGELOG.md` block.

## Reusable v0.1.0 Format

The `v0.1.0` release uses this durable format:

```markdown
## v0.1.0

Initial OSS foundation.

### Added

- Local-first project memory architecture.
- Project Knowledge Bot reference runtime.
- RAG/search/chat pipeline with citations.
- Meeting processing pipeline.
- CI workflow and tests.
- Documentation, quality evaluation, and maintainer workflow foundation.
```

Future releases should keep:

- one `## vX.Y.Z` heading per release;
- concise summary paragraph;
- sectioned bullet list;
- same versions in `CHANGELOG.md` and `CHANGELOG.ru.md`;
- no private customer/project/runtime details.

## Automation

Local validator:

```powershell
.\.venv\Scripts\python.exe scripts\45_validate_release_notes.py --version 0.1.0
```

GitHub Actions:

```text
Actions -> Release Validation -> Run workflow -> version
```

The workflow validates bilingual changelogs, compiles Python files and runs tests.
