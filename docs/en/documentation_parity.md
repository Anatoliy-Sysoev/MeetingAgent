# Documentation Parity

[English](documentation_parity.md) | [Русский](../ru/documentation_parity.md)

MeetingAgent keeps public documentation in English and Russian. English is the primary OSS language; Russian documentation is maintained as a parallel version for the project owner and Russian-speaking contributors.

## Documents That Must Stay Paired

- `README.md` / `README.ru.md`
- `SECURITY.md` / `SECURITY.ru.md`
- `CONTRIBUTING.md` / `CONTRIBUTING.ru.md`
- `CODE_OF_CONDUCT.md` / `CODE_OF_CONDUCT.ru.md`
- `CHANGELOG.md` / `CHANGELOG.ru.md`
- `docs/en/*.md` / `docs/ru/*.md`
- `examples/en/*` / `examples/ru/*`, when public examples change

## Required Parity Rules

- Public docs must include a language switch near the top.
- Product capabilities, security warnings, setup commands, Docker/API behavior, and data privacy rules must be represented in both languages.
- If a translation intentionally lags, mark it near the top with:

```text
Translation status: outdated. Source version: <file path>, commit: <sha>.
```

- Do not add private customer names, real transcripts, local paths, runtime indexes, or generated private reports while updating either language.

## Contributor Workflow

1. Check whether the changed public file has a paired translation.
2. Update both files in the same PR when possible.
3. If exact translation is not possible, add the outdated marker and explain the gap in the PR body.
4. Keep commands, environment variable names, endpoint names, and security constraints equivalent.
5. Run documentation parity tests before opening a PR:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_docs_parity.py -q
```

## Intentional Differences

The two languages may differ in explanatory wording, local Windows examples, or contributor notes. They must not disagree on product behavior, security expectations, runtime data handling, or supported commands.
