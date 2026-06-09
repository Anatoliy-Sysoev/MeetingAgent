# Documentation Parity Guide

MeetingAgent keeps both English and Russian documentation for core public-facing
materials. This guide helps contributors update one language without accidentally
leaving the paired document behind.

## Documents That Should Usually Stay In Sync

- `README.md` / `README.ru.md`
- `CONTRIBUTING.md` / `CONTRIBUTING.ru.md`
- `CODE_OF_CONDUCT.md` / `CODE_OF_CONDUCT.ru.md`
- `SECURITY.md` / `SECURITY.ru.md`
- `CHANGELOG.md` / `CHANGELOG.ru.md`

Project-specific docs under `docs/` may not always have a translated pair, but
contributors should call out when a change only exists in one language.

## Recommended Workflow

1. Identify whether the file you changed has a translated counterpart.
2. If the counterpart exists, update it in the same PR whenever possible.
3. If exact translation is not possible in the same PR, note the intentional gap in the PR body.
4. Keep headings, section ordering, and command examples aligned unless language-specific explanation requires a difference.

## What Must Match

- feature availability statements
- setup and runtime commands
- security and privacy warnings
- public/private data handling rules
- release or support expectations

## What Can Differ

- language-specific examples
- wording that improves clarity for a local audience
- links to language-specific supporting material

## PR Checklist

Before opening a docs PR, ask:

- Did I check whether a paired `*.ru.md` or English file exists?
- Did I keep command examples consistent?
- Did I note any intentional translation gap?
- Did I avoid changing product claims in only one language?

## Suggested PR Note

If you cannot update both languages immediately, use a note like:

> English and Russian docs are not fully updated in the same PR. This change updates the source document first; the paired translation needs follow-up to restore parity.
