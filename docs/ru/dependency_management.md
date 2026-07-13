# Управление Зависимостями

[English](../en/dependency_management.md) | [Русский](dependency_management.md)

## Поддерживаемый Lock

Python 3.12 является канонической воспроизводимой средой для локальной
разработки, CI, release validation и Docker. Direct requirements задают
допустимые диапазоны, а `constraints-py312.txt` фиксирует проверенный точный
resolver result для core, offline-транскрибации, optional diarization,
документации и dev tools.

| Группа | Файл | Установка по умолчанию |
|---|---|---|
| Core API/RAG | `requirements.txt` | Да |
| Offline ASR | `requirements-transcription.txt` | Product install и image |
| Development/audit | `requirements-dev.txt` | Только development и CI |
| Browser UI smoke | `requirements-browser.txt` | Отдельные CI/local browser tests |
| Live/Vosk | `requirements-live.txt` | Изолированный optional runtime |
| Diarization | `requirements-diarization.txt` | Optional image/окружение |
| GigaAM | `requirements-gigaam.txt` | Изолированное Python-окружение |

Создание product environment:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c constraints-py312.txt `
  -r requirements.txt -r requirements-transcription.txt
.\.venv\Scripts\python.exe -m pip check
```

Для разработки:

```powershell
.\.venv\Scripts\python.exe -m pip install -c constraints-py312.txt `
  -r requirements-dev.txt
```

Для browser-level проверки product UI установите test-only library и Chromium:

```powershell
.\.venv\Scripts\python.exe -m pip install -c constraints-py312.txt `
  -r requirements-browser.txt
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\browser -q
```

## Обновление Lock

Сначала обновите direct ranges, затем пересоберите lock на Python 3.12:

```powershell
py -3.12 -m venv .venv-lock
.\.venv-lock\Scripts\python.exe -m pip install "pip-tools==7.5.3"
.\.venv-lock\Scripts\python.exe -m piptools compile --resolver=backtracking --strip-extras --allow-unsafe `
  --output-file constraints-py312.txt requirements-lock-py312.in
.\.venv\Scripts\python.exe scripts\47_dependency_audit.py
```

Перед merge просмотрите полный diff lock-файла и запустите canonical test suite.
Нельзя вручную менять один transitive pin без проверки полного resolver graph.

## Политика Advisory

Scheduled и release workflows запускают `pip-audit` по точному pinned graph.
Известная уязвимость или ошибка сбора зависимостей ломает gate. Дочерний
audit-процесс всегда использует UTF-8 I/O, поэтому Windows checkout под профилем
с не-ASCII символами даёт тот же результат, что CI, не меняя окружение
родительского PowerShell. Исключение допускается только в
`security/dependency-audit-exceptions.json` и обязано иметь:

- идентификатор CVE, GHSA или PYSEC;
- конкретное обоснование;
- issue этого репозитория для устранения;
- ISO-дату истечения.

Просроченное, дублирующееся, malformed или неописанное исключение отклоняется
fail-closed. Активных исключений сейчас нет. `pip-audit` проверяет известные
package advisories, но не обнаруживает malware и не заменяет code review.

Optional diarization разрешается в `constraints-py312.txt`, но устанавливается
только явно. GigaAM и live audio остаются вне этого lock, потому что доступность
Torch/audio wheels и device bindings зависит от платформы. Держите эти окружения
изолированными, используйте bounded direct requirements, запускайте `pip check`
и audit установленного environment перед deployment.

Первичные источники: [pip-audit](https://github.com/pypa/pip-audit),
[pip-tools](https://pip-tools.readthedocs.io/en/stable/) и
[GitHub Dependabot](https://docs.github.com/en/code-security/dependabot).
