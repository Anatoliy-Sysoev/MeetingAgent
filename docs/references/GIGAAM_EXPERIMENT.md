# Эксперимент GigaAM

Дата фиксации в документации: 2026-05-25.

## Цель

Проверить, можно ли использовать GigaAM как локальный ASR-вариант для русскоязычных проектных встреч MeetingAgent.

Эксперимент не заменяет основной `faster-whisper` pipeline. Он фиксирует рабочую локальную конфигурацию, чтобы она не потерялась между сессиями и компьютерами.

## Статус

```text
status = completed
основной pipeline = faster-whisper
GigaAM status = экспериментальный fallback / кандидат для сравнения качества
```

GigaAM не включён в `scripts/06_transcribe_meeting.py` и `scripts/08_process_meeting_pipeline.py` как production backend. Для использования в продукте нужен отдельный адаптер и повторяемый benchmark.

## Локальная Среда

GigaAM поднимался отдельно от основного `.venv` MeetingAgent:

```text
%LOCALAPPDATA%\MeetingAgent\gigaam-venv312
```

Причина: не смешивать тяжёлые ASR-зависимости с основным репозиторным окружением и не ломать существующий `faster-whisper` pipeline.

HF token передаётся только через переменные окружения:

```powershell
$env:HF_TOKEN = "<не коммитить>"
$env:HUGGINGFACE_HUB_TOKEN = $env:HF_TOKEN
```

Токены, model cache, chunks, transcript и runtime-артефакты не коммитятся.

## Проверенный Путь

Рабочая модель:

```python
gigaam.load_model(
    "v3_e2e_rnnt",
    fp16_encoder=False,
    device="cpu",
    download_root="..."
)
```

Для длинного MP4 штатный longform-путь оказался менее надёжным из-за внешних зависимостей. Рабочий fallback:

```text
MP4
-> ffmpeg
-> audio_16k_mono.wav
-> 24-second chunks
-> model.transcribe() на каждом chunk
-> incremental append в segments_gigaam_manual.jsonl
-> transcript_gigaam_manual.md
```

## Локальный Прогон

Папка runtime-встречи:

```text
meetings/2026-05-19__asu-novatek-stroycontrol-gigaam/
```

Runtime-артефакты:

```text
source/audio_16k_mono.wav
source/sample_25s.wav
transcript/chunks_24s/
transcript/segments_gigaam_manual.jsonl
transcript/transcript_gigaam_manual.md
artifacts/gigaam_manual_transcribe_report.json
```

Фактический report:

```text
status = completed
chunks_total = 224
chunks_done = 224
errors = []
elapsed_sec_this_run = 1070.2
updated_at = 2026-05-19T19:09:59+0300
```

224 chunk по 24 секунды соответствуют примерно 89.6 минутам аудио.

## Что Сработало

- GigaAM успешно запустился локально на CPU.
- Отдельный Python 3.12 venv не затронул основной `.venv`.
- Ручной chunking позволил обработать длинную запись resumable-способом.
- Сегменты и transcript сохранялись инкрементально.
- Ошибок по chunk processing в зафиксированном прогоне нет.

## Ограничения

- Нет встроенного адаптера в MeetingAgent pipeline.
- Нет формализованного сравнения качества с `faster-whisper small` и `large-v3-turbo`.
- Нет speaker diarization.
- Нет word-level timestamps.
- Требуется Hugging Face token и локальный model cache.
- Runtime-артефакты большие и не должны попадать в Git.

## Решение На Сейчас

Для MeetingAgent по умолчанию оставить:

```text
faster-whisper large-v3-turbo/int8 - качественный offline-профиль
faster-whisper small/int8 - быстрый draft/live профиль
```

GigaAM оставить как экспериментальный локальный ASR fallback и кандидат на отдельное сравнение качества русского текста.

## Когда Вернуться

Вернуться к GigaAM, если:

- `faster-whisper small` стабильно хуже распознаёт русские проектные термины;
- нужна отдельная русскоязычная ASR-линия для важных встреч;
- появится задача сравнить ASR backend по одному набору встреч;
- будет готов адаптер `asr_backend = faster_whisper | gigaam`.

Минимальный следующий шаг:

```text
создать маленький benchmark:
1 запись
3 backend/profile:
- faster-whisper small/int8
- faster-whisper large-v3-turbo/int8
- GigaAM v3_e2e_rnnt CPU
метрики:
- время
- ручная оценка терминов
- количество грубых смысловых ошибок
- пригодность для MAP -> REDUCE -> RENDER
```
