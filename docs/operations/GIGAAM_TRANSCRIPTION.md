# GigaAM-Транскрибация

## Назначение

Локальный fallback-путь для ручной транскрибации видео и аудио через установленный `GigaAM`.

Основной ASR-путь MeetingAgent остается `faster-whisper`, но `GigaAM` полезен для точечных прогонов, когда нужно сравнить качество русской речи или быстро получить transcript из внешней записи.

## Что Уже Настроено На Этом ПК

- исходники GigaAM: `%USERPROFILE%\GigaAM`;
- модель: `gigaam/v3_e2e_rnnt`;
- рабочий ASCII-cache: `%ProgramData%\gigaam_cache`;
- Python: глобальный `python`;
- `ffmpeg` и `ffprobe` доступны из PATH.

Причина ASCII-cache: `sentencepiece` в GigaAM может падать на пути к tokenizer с кириллицей в `%USERPROFILE%\.cache\gigaam`. Поэтому wrapper использует `%ProgramData%\gigaam_cache` и при необходимости копирует туда уже скачанные файлы модели.

## Команда Повторного Прогона

```powershell
.\scripts\run_gigaam_transcribe.ps1 `
  -InputPath "$env:USERPROFILE\Downloads\input.mp4" `
  -OutputDir "$env:USERPROFILE\Downloads\gigaam_input"
```

Для файла с пробелами и кириллицей передавай полный путь в кавычках:

```powershell
.\scripts\run_gigaam_transcribe.ps1 `
  -InputPath "$env:USERPROFILE\Downloads\Схема уровня поддержки.mp4" `
  -OutputDir "$env:USERPROFILE\Downloads\gigaam_support_scheme"
```

## Выходные Файлы

Wrapper создает:

```text
audio_16k_mono.wav
chunks_24s/chunk_0000.wav
segments_gigaam.jsonl
transcript_gigaam.md
transcript_gigaam.txt
```

Эти файлы являются runtime/output-артефактами и не коммитятся в Git. Для Git фиксируется только отчет о прогоне или выдержка в `docs/references/`.

## Ограничения

- используется короткий режим GigaAM, поэтому аудио режется на чанки по 24 секунды;
- diarization не выполняется;
- границы фраз могут обрываться на границах чанков;
- результат требует ручной проверки перед использованием в протоколе или сдачных документах.
