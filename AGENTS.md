# Инструкции Для Агентов

## Восстановление Контекста

- Перед изменениями прочитай `README.md`, `AGENTS.md`, `docs/context.md` и `docs/todo.md`.
- В новом треде дополнительно посмотри `git log --oneline -10`.
- Один каталог считается одним пет-проектом и одним Git-репозиторием.
- Преамбул и контекст не пересказывай: они уже в этом файле, `docs/context.md` и `docs/todo.md`.

## Работа С Git

- Всегда фиксируй значимые изменения проекта в Git.
- Один task = один атомарный коммит.
- Предпочитай небольшие коммиты с понятными сообщениями.
- Проверяй `git status --short` перед изменениями и перед завершением работы.
- Ветка нужна только для работы или PR; после merge в `main` ветку нужно удалить.
- Новые реализации и каноническое состояние проекта искать сначала в `main`.
- Если нужная реализация есть только в feature-ветке, сначала влить её в `main` или явно зафиксировать, почему она остаётся вне `main`.
- Не перезаписывай и не откатывай изменения пользователя без прямой просьбы.
- Не коммить секреты, `.env`, локальные конфиги, build-артефакты, `node_modules`, `.venv`, `venv`, `dist`, настройки IDE, рабочие логи, локальные поисковые индексы, медиафайлы и сгенерированные проектные данные.
- Перед завершением каждой задачи обновляй `docs/context.md` и `docs/todo.md`.
- В конце сессии показывай или кратко пересказывай `git status`.

## Правила MeetingAgent

- Продукт по умолчанию должен оставаться локальным.
- Local-first, CPU-first, Windows + PowerShell + `.venv`.
- Никаких облачных сервисов и GPU-допущений без явной задачи.
- Тяжёлые шаги ASR / diarization / LLM выполняются с `concurrency=1`.
- Не коммить `config.yaml`, `data/`, `logs/`, `vector_db/`, `watched_folder/` и `.venv/`.
- Каждый вызов Ollama `/api/embeddings` должен включать `options.num_ctx=8192`.
- Не меняй значение модели embeddings в cache с `bge-m3`, если пользователь явно не запускает миграцию cache.
- Сохраняй resumability: не удаляй `data/embeddings_cache.jsonl` при восстановлении после сбоев.
- Watchdog может перезапускать Ollama, но не должен убивать живой процесс `03_build_index.py`.
- Предпочитай продуктовые документы и небольшие шаги реализации большим переписываниям.

## RULE-CODE

Do not restate preamble/context. Read `AGENTS.md`, `docs/context.md`, `docs/todo.md` yourself.

Every task MUST:
- update `docs/context.md`;
- update `docs/todo.md`;
- stay inside task scope;
- produce one atomic commit only if checks pass.

`docs/context.md` is rolling, not append-only:

```md
## Now
- last commit: <sha msg>
- in progress: <TASK|none>

## Done latest
- <2-4 bullets only>

## Next
- <2-3 task IDs>

## Open decisions / blockers
- <short|none>
```

`docs/todo.md` format:

```md
- [ ] TASK-ID — title
- [~] TASK-ID — title
- [x] TASK-ID — title — <commit sha>
```

Output ONLY:

```text
TASK: <ID>
FILES: <changed paths, one line>
DIFF: <unified diff, changed lines only>
CHECKS: pytest <N passed/M failed> | py_compile ok|fail | git diff --check ok|fail | schema ok|n/a
CTX/TODO: updated — <one line: changed / remains>
BLOCKERS: none | [Requires clarification]: <question>
```

Forbidden:
- no plan recap;
- no full unchanged files;
- no full test logs;
- no narrative;
- no out-of-scope edits;
- no commit if blockers/checks fail.

If blocked, output only `BLOCKERS` and stop.

## RULE-REVIEW

Review by `DIFF` + `docs/context.md` + `docs/todo.md`.
Ask for a full file ONLY when diff is insufficient. Name exactly one file.

Output ONLY:

```text
VERDICT: APPROVE | CHANGES
CHANGES:
1. <file:place> — <what and why>
2. ...
NEXT: <next TASK-ID | hold>
```

Limits:
- no code rewrites unless required;
- no context restatement;
- no essays;
- max ~10 lines unless a real defect requires detail.

## TASK FORMAT

```text
ID: <TASK-ID>
Scope: <files/areas allowed>
Do not touch: <files/areas forbidden>
Acceptance:
- <checkable item>
- <checkable item>
Checks:
- pytest ...
- py_compile ...
- git diff --check
Commit:
- <message>
```

## Ритуал Завершения Дня

Когда пользователь просит завершить рабочий день:

1. Обнови `docs/context.md`.
2. Обнови `docs/todo.md`.
3. Выполни `git status --short`.
4. Если изменения готовы и безопасны, сделай commit и push.
