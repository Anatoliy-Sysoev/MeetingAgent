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
| GigaAM | `requirements-gigaam.txt` + `constraints-gigaam-py312-windows.txt` | Изолированное Windows/Python 3.12 окружение |

## Матрица Совместимости Major-Обновлений

Major- и native-runtime-обновления проверяются независимо. Зелёный результат
одной строки не означает автоматического одобрения другой.

| Контур | Проверенный direct range / exact lock | Статус и доказательства | Откат / tracking |
|---|---|---|---|
| Core и retrieval NumPy | `numpy>=1.26,<3`; Python 3.12 lock `2.5.1` | Одобрено: чистая Windows-установка, `pip check`, advisory audit, загрузка сохранённого в 1.26 `.npy` и retrieval suite с coverage gates | Вернуть range `<2` и lock `1.26.4`; #241 |
| Offline transcription | `faster-whisper>=1.1,<2`; lock `1.2.1`, CTranslate2 `4.8.1`, NumPy `2.5.1` | Проверено без изменения: clean import и canonical transcription tests проходят; ASR model/default в этом compatibility batch не менялись | Сохранить предыдущий exact lock или завести отдельный real-model ASR review; #236 |
| Diarization | `sherpa-onnx>=1.13.2,<2`, `onnxruntime>=1.17,<2`; lock `1.13.4` / `1.27.0`, NumPy `2.5.1` | Одобрено: обе реальные локальные ONNX-модели открываются CPU provider, sherpa diarizer успешно создаётся | Откатить NumPy на `1.26.4` и предыдущий exact graph; #241 |
| Live MIC через sounddevice | `sounddevice>=0.5.5,<0.6`; platform locks `0.5.5` | Одобрено: чистые Windows/Linux-установки, `pip check`, advisory audit, 101 live-тест и не сохраняющий аудио Windows MIC callback smoke на 16 кГц | Вернуть range `<0.5` и locks `0.4.7`; #242 |
| Изолированный GigaAM ONNX/TorchAudio | Python 3.12 lock: `onnx 1.22.0`, `onnxruntime 1.23.2`, `torch 2.13.0+cpu`, `torchaudio 2.11.0+cpu` | Одобрено: чистая Windows-установка, `pip check`, audit без advisory, импорт upstream source, загрузка модели, импорт ONNX utilities и детерминированный short-speech inference | Пересобрать изолированный venv по этому lock; проверенный GigaAM commit `6e4b027c...`; #243 |
| Тема документации | `mkdocs-material==9.7.6`; MkDocs `1.6.1` | Одобрено: чистая Python 3.12 docs-установка, `pip check`, audit lock без advisory, strict build и встроенная проверка targets/anchors | Откатить Material на `9.5.50`; оценить Zensical до завершения maintenance support; #244 |

Общий review отслеживается в #236. Эти строки нельзя снова объединять в один
автоматический dependency PR.

Python-обновления Dependabot намеренно не группируются. Каждый PR обязан вместе
обновить соответствующие direct range и exact lock, затем выполнить smoke из
своей строки compatibility matrix. Unit contract запрещает catch-all группу
`patterns: ["*"]`, потому что раньше она объединила NumPy, audio, GigaAM и docs
в непроверяемый batch. GitHub Actions можно оставить grouped: их majors отдельно
ограничивает workflow allowlist test.

Live runtime на Windows:

```powershell
.\.venv\Scripts\python.exe -m pip install `
  -c constraints-py312.txt `
  -c constraints-live-py312-windows.txt `
  -r requirements.txt `
  -r requirements-live.txt
.\.venv\Scripts\python.exe -m pip check
```

На Linux замените второй constraints на
`constraints-live-py312-linux.txt`. Оба platform lock используют
`https://download.pytorch.org/whl/cpu` и не устанавливают CUDA packages. На
Windows при отключённой поддержке long paths используйте короткий путь
окружения, например `C:\ma-live`: иначе Torch может завершить распаковку с
`WinError 206`.

GigaAM устанавливается только в отдельное Windows/Python 3.12 окружение:

```powershell
py -3.12 -m venv C:\ma-gigaam312
C:\ma-gigaam312\Scripts\python.exe -m pip install `
  -c constraints-gigaam-py312-windows.txt `
  -r requirements-gigaam.txt
C:\ma-gigaam312\Scripts\python.exe -m pip check
```

Используйте source tree `salute-developers/GigaAM` на проверенном commit
`6e4b027c6fb554e09e8b9059b757a175295ab879`. Upstream фиксирует ONNX 1.19, но
эта линия содержит известные advisory, поэтому inference-only profile
MeetingAgent намеренно использует ONNX 1.22.0. Проверены загрузка Torch-модели,
короткая речевая транскрибация и импорт `gigaam.onnx_utils`. Экспорт GigaAM в
ONNX не входит в поддерживаемый product path.

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
.\.venv-lock\Scripts\python.exe -m piptools compile --resolver=backtracking --strip-extras --allow-unsafe `
  --output-file constraints-gigaam-py312-windows.txt requirements-gigaam-lock-py312.in
.\.venv\Scripts\python.exe scripts\47_dependency_audit.py
```

Linux live lock собирается той же командой в Python 3.12 Linux environment с
output `constraints-live-py312-linux.txt`. После изменения live ranges нужны
оба lock-файла, clean install, `pip check`, imports и загрузка Silero model.

Перед merge просмотрите полный diff lock-файла и запустите canonical test suite.
Нельзя вручную менять один transitive pin без проверки полного resolver graph.

Material for MkDocs 9.7 находится в maintenance mode: получает критические
bug/security fixes, но не новые функции. MeetingAgent использует только
стабильную тему Material и search plugin, без deprecated projects/typeset
plugins. Текущий сайт остаётся на 9.7.6, а возможный переход на Zensical должен
быть отдельным архитектурным решением. Release gate запускает
`mkdocs build --strict` со встроенной в MkDocs 1.6 проверкой отсутствующих
document targets, нераспознанных относительных ссылок и anchors. См. официальное
[объявление 9.7](https://squidfunk.github.io/mkdocs-material/blog/2025/11/11/insiders-now-free-for-everyone/)
и [MkDocs validation](https://www.mkdocs.org/user-guide/configuration/#validation).

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
имеет собственный reviewed Windows lock и отдельный scheduled audit entry из-за
особого Torch/runtime profile; смешивать его с core или live environment нельзя.

Первичные источники: [pip-audit](https://github.com/pypa/pip-audit),
[pip-tools](https://pip-tools.readthedocs.io/en/stable/) и
[GitHub Dependabot](https://docs.github.com/en/code-security/dependabot).
