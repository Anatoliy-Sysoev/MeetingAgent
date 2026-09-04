# Паритет Документации

[English](../en/documentation_parity.md) | [Русский](documentation_parity.md)

MeetingAgent ведёт публичную документацию на английском и русском языках. Английский язык считается основным для OSS-аудитории; русская документация поддерживается как параллельная версия для владельца проекта и русскоязычных contributors.

## Документы, Которые Должны Оставаться Парными

- `README.md` / `README.ru.md`
- `SECURITY.md` / `SECURITY.ru.md`
- `CONTRIBUTING.md` / `CONTRIBUTING.ru.md`
- `CODE_OF_CONDUCT.md` / `CODE_OF_CONDUCT.ru.md`
- `CHANGELOG.md` / `CHANGELOG.ru.md`
- `docs/en/*.md` / `docs/ru/*.md`
- `examples/en/*` / `examples/ru/*`, если меняются публичные examples

## Обязательные Правила Паритета

- В публичных документах должен быть переключатель языка в верхней части файла.
- Возможности продукта, security warnings, команды запуска, Docker/API behavior и правила обращения с приватными данными должны быть отражены в обеих версиях.
- Если перевод намеренно отстаёт, рядом с началом файла нужно добавить marker:

```text
Translation status: outdated. Source version: <file path>, commit: <sha>.
```

- Нельзя добавлять private customer names, реальные транскрипты, локальные пути, runtime indexes или private generated reports при обновлении любой языковой версии.

## Workflow Для Contributors

1. Проверьте, есть ли у изменённого публичного файла paired translation.
2. По возможности обновляйте обе версии в одном PR.
3. Если точный перевод нельзя сделать сразу, добавьте outdated marker и объясните gap в PR body.
4. Сохраняйте эквивалентность команд, имён переменных окружения, endpoint names и security constraints.
5. Перед PR запускайте parity tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_docs_parity.py -q
```

## Допустимые Отличия

Две языковые версии могут отличаться формулировками, локальными Windows examples или contributor notes. Они не должны расходиться в описании поведения продукта, security expectations, правил runtime data handling и поддерживаемых команд.
