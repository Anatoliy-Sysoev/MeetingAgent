# Archive — Project Knowledge Bot

Обновлено: 2026-05-16.

## Назначение

Папка содержит исторические документы, дизайн-драфты и материалы, которые полезны для контекста, но больше не являются активной проектной документацией.

Активные документы находятся уровнем выше:

```text
docs/subprojects/asu-june-bot/README.md
docs/subprojects/asu-june-bot/context.md
docs/subprojects/asu-june-bot/architecture.md
docs/subprojects/asu-june-bot/mvp.md
docs/subprojects/asu-june-bot/roadmap.md
docs/subprojects/asu-june-bot/decisions.md
docs/subprojects/asu-june-bot/todo.md
docs/subprojects/asu-june-bot/RUNBOOK_V2.md
docs/subprojects/asu-june-bot/product/README.md
```

## Правила архивирования

Документ переносится в архив, если:

- описывает уже реализованный design draft;
- содержит старый план, который заменён актуальным roadmap/MVP/RUNBOOK;
- может ввести в заблуждение как активная инструкция;
- нужен для истории решений, но не для текущего запуска/разработки.

Не архивировать:

- smoke reports, если они являются доказательством прохождения этапа;
- ADR, если решение всё еще влияет на архитектуру;
- runbook, если он является актуальной инструкцией запуска;
- eval cases, если они используются текущим baseline.

## Архивированные документы

```text
archive/design/api_search_mvp_design.md
```

Причина:

```text
API Search MVP реализован. Активное состояние отражено в architecture.md, mvp.md, roadmap.md, RUNBOOK_V2.md и smoke_report_api_search_mvp.md.
```

## Case-conflict runbook

Ранее в истории репозитория встречались два файла, отличавшиеся только регистром:

```text
RUNBOOK_V2.md
runbook_v2.md
```

Канонический активный файл:

```text
RUNBOOK_V2.md
```

Файл `runbook_v2.md` не должен возвращаться в активную папку, потому что на Windows это создает конфликт путей.
