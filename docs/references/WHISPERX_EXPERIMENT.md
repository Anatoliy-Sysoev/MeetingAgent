# Эксперимент WhisperX

Дата: 2026-05-08.

## Цель

Проверить, даёт ли WhisperX практическое преимущество по сравнению с текущими `faster-whisper` профилями:

- `small/int8`;
- `large-v3-turbo/int8`;
- `whisperx + large-v3-turbo/int8 + alignment`.

Тестовая запись:

```text
meetings/2026-05-08__test-meeting/source/2026-05-07 10-17-18.mp4
```

Запись содержит разбор замечаний к документации, пересечения с ФТТ, Паспортом ИС, ЦТА и руководствами.

## Ограничения Эксперимента

- Diarization не запускалась: для неё нужны отдельные HuggingFace-модели и токены.
- WhisperX запускался только как ASR + alignment.
- Результаты лежат в runtime-папке встречи и не коммитятся:

```text
meetings/2026-05-08__test-meeting/transcript/model_compare/
```

## Окружение

Основной `.venv` MeetingAgent использует Python 3.14. WhisperX не удалось поставить туда напрямую: версия, доступная для Python 3.14, тянула несовместимый `ctranslate2`.

Решение: отдельный экспериментальный venv на Python 3.12 вне репозитория:

```text
%LOCALAPPDATA%\MeetingAgent\whisperx-venv312
```

Команда установки:

```powershell
py -3.12 -m venv $env:LOCALAPPDATA\MeetingAgent\whisperx-venv312
& $env:LOCALAPPDATA\MeetingAgent\whisperx-venv312\Scripts\python.exe -m pip install --upgrade pip
& $env:LOCALAPPDATA\MeetingAgent\whisperx-venv312\Scripts\python.exe -m pip install whisperx
```

## Windows-Обходы

Silero VAD внутри WhisperX через `torch.hub` не смог открыть cache-файл из пути с кириллицей:

```text
C:\Users\Сотрудник\.cache\torch\hub\...
```

Обход: использовать ASCII-путь для `TORCH_HOME`:

```powershell
$env:TORCH_HOME = "C:\Temp\meetingagent_torch_cache"
```

Также WhisperX показал предупреждение по `torchcodec` и FFmpeg 8. В этом прогоне оно не заблокировало ASR/alignment, но для стабильного production-пути это нужно перепроверить отдельно.

## Результаты

| Pipeline | Модель | Время всего | ASR | Alignment | RT-factor | Segments | Слов | Символов |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| faster-whisper | `small` | 448.357s | 445.157s | - | 0.3573 | 398 | 2012 | 13099 |
| faster-whisper | `large-v3-turbo` | 1260.678s | 1254.12s | - | 1.0074 | 463 | 2180 | 14165 |
| whisperx | `large-v3-turbo` | 1944.121s | 703.956s | 1221.888s | 1.5583 | 225 | 1817 | 12241 |

Счётчики терминов:

| Термин | small | large-v3-turbo | WhisperX large-v3-turbo |
|---|---:|---:|---:|
| ФТТ | 0 | 1 | 2 |
| ПМИ | 0 | 0 | 0 |
| ЦТА | 1 | 2 | 3 |
| АСУ | 0 | 0 | 0 |
| Паспорт | 9 | 9 | 8 |
| ИБ | 4 | 7 | 3 |
| ИС | 42 | 45 | 39 |
| руководство | 5 | 6 | 4 |
| администратор | 2 | 2 | 1 |
| инструкция | 0 | 0 | 0 |
| замечания | 4 | 5 | 4 |

## Наблюдения По Качеству

WhisperX лучше сегментирует длинную речь и даёт alignment по словам, но в этом прогоне текст не стал однозначно лучше `large-v3-turbo` через `faster-whisper`.

Плюсы WhisperX:

- есть word-level alignment;
- ASR-часть оказалась быстрее полного faster-whisper turbo-прогона;
- лучше поднимаются отдельные термины вроде `ФТТ` и `ЦТА`.

Минусы WhisperX:

- alignment занял больше времени, чем само распознавание;
- итоговый pipeline медленнее всех текущих вариантов;
- местами появились повторы и деградация текста, например повтор слова `Документ`;
- Windows-окружение требует дополнительных обходов cache/torchcodec;
- diarization без отдельного токена и моделей не проверялась.

## Решение

Для ближайшего MVP:

- `small/int8` оставить для быстрого черновика и live MVP;
- `large-v3-turbo/int8` оставить основным профилем финальной offline-транскрибации важных встреч;
- WhisperX не включать в основной pipeline до появления явной потребности в word-level timestamps или diarization.

Когда вернуться к WhisperX:

- если нужен просмотр transcript с подсветкой слова в видео;
- если нужна diarization и есть готовый HuggingFace-токен;
- если появится локальный GPU или отдельный cloud-lab на обезличенных данных;
- если решим делать редактор transcript с точной привязкой слов к таймкоду.

