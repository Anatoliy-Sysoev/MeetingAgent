# Translation Policy

English is the primary public OSS language for MeetingAgent.

Russian documentation is maintained as a full parallel version for the project owner and Russian-speaking contributors.

When changing public documentation, update both language versions:

- `README.md` / `README.ru.md`;
- `SECURITY.md` / `SECURITY.ru.md`;
- `CONTRIBUTING.md` / `CONTRIBUTING.ru.md`;
- `docs/en/*` / `docs/ru/*`;
- `examples/en/*` / `examples/ru/*`, when examples change.

If a translation is temporarily outdated, add this marker near the top of the translated file:

```text
Translation status: outdated. Source version: <file path>, commit: <sha>.
```

Internal working documents such as `docs/context.md`, `docs/todo.md`, and `docs/decisions.md` may remain in Russian while the public OSS documentation is being stabilized.
