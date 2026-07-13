# Управление Зависимостями

[English](../en/dependency_management.md) | [Русский](dependency_management.md)

## Поддерживаемый Lock

Python 3.12 является канонической воспроизводимой средой для локальной
разработки, CI, release validation и Docker. Direct requirements задают
допустимые диапазоны, а `constraints-py312.txt` фиксирует проверенный точный
resolver result для core, offline-транскрибации, optional diarization,
документации и dev tools.

Optional live runtime имеет отдельные точные lock-файлы:
`constraints-live-py312-windows.txt` и
`constraints-live-py312-linux.txt`. Они совместимы с core constraints, но не
добавляют Torch/Vosk в базовую установку.

| Группа | Файл | Установка по умолчанию |
|---|---|---|
| Core API/RAG | `requirements.txt` | Да |
| Offline ASR | `requirements-transcription.txt` | Product install и image |
| Development/audit | `requirements-dev.txt` | Только development и CI |
| Browser UI smoke | `requirements-browser.txt` | Отдельные CI/local browser tests |
| Live/Vosk | `requirements-live.txt` | Изолированный optional runtime |
| Diarization | `requirements-diarization.txt` | Optional image/окружение |
| GigaAM | `requirements-gigaam.txt` | Изолированное Python-окружение |

## Матрица Совместимости Major-Обновлений

Major- и native-runtime-обновления проверяются независимо. Зелёный результат
одной строки не означает автоматического одобрения другой.

| Контур | Проверенный direct range / exact lock | Статус и доказательства | Откат / tracking |
|---|---|---|---|
| Core, retrieval и diarization NumPy | `numpy>=1.26,<3`; Python 3.12 lock `2.5.1` | Одобрено: чистая Windows-установка, `pip check`, advisory audit, загрузка сохранённого в 1.26 `.npy`, retrieval suite, ONNX Runtime sessions обеих diarization-моделей и создание sherpa diarizer | Вернуть range `<2` и lock `1.26.4`; #241 |
| Live MIC через sounddevice | `sounddevice>=0.4.6,<0.5`; platform locks сохраняют `0.4.7` | Ожидается отдельный Windows callback/device smoke | Сохранить `0.4.7`; #242 |
| Изолированный GigaAM ONNX/TorchAudio | `onnx==1.19.*`, `onnxruntime==1.25.*`, `torchaudio>=2.6` | Ожидается exact isolated Python 3.12 lock и реальный smoke короткого аудио | Сохранить существующий изолированный runtime; #243 |
| Тема документации | `mkdocs-material==9.5.50` | Ожидается strict build и link validation на 9.7.x | Сохранить `9.5.50`; #244 |

Общий review отслеживается в #236. Эти строки нельзя снова объединять в один
автоматический dependency PR.

Live runtime на Windows:

```powershell
.\.venv\Scripts\python.exe -m pip install `
  -c constraints-py312.txt `
  -c constraints-live-py312-windows.txt `
  -r requirements-live.txt
.\.venv\Scripts\python.exe -m pip check
```

На Linux замените второй constraints на
`constraints-live-py312-linux.txt`. Оба platform lock используют
`https://download.pytorch.org/whl/cpu` и не устанавливают CUDA packages.

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
.\.venv-lock\Scripts\python.exe -m piptools compile --resolver=backtracking --strip-extras --allow-unsafe `
  --output-file constraints-live-py312-windows.txt requirements-live-lock-py312.in
.\.venv\Scripts\python.exe scripts\47_dependency_audit.py
```

Linux live lock собирается той же командой в Python 3.12 Linux environment с
output `constraints-live-py312-linux.txt`. После изменения live ranges нужны
оба lock-файла, clean install, `pip check`, imports и загрузка Silero model.

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

Официальный CPU index маркирует Torch wheels local-version суффиксом `+cpu`,
который `pip-audit` не может напрямую разрешить через PyPI. Audit projection
удаляет index directive и только для reviewed `torch`/`torchaudio` `+cpu` pins
использует ту же публичную базовую версию при advisory lookup. Любой другой
local-version pin отклоняется fail-closed.

Optional diarization разрешается в `constraints-py312.txt`, но устанавливается
только явно. Live audio использует отдельные Windows/Linux CPU locks; scheduled
workflow проверяет core, live-linux и live-windows graphs независимо. GigaAM
остаётся вне reviewed locks из-за отдельного Torch/runtime profile. Держите его
изолированным, запускайте `pip check` и audit environment перед deployment.

Первичные источники: [pip-audit](https://github.com/pypa/pip-audit),
[pip-tools](https://pip-tools.readthedocs.io/en/stable/) и
[GitHub Dependabot](https://docs.github.com/en/code-security/dependabot).
