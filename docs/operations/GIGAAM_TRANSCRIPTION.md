# GigaAM-Транскрибация

## Назначение

Локальный backend для транскрибации видео и аудио через установленный `GigaAM`.

Основной ASR-путь MeetingAgent остается `faster-whisper`, но `GigaAM` встроен в общий entrypoint `scripts/22_transcribe_meeting.py` и может писать результат прямо в карточку встречи.

## Требования К Локальному Runtime

- локальные исходники или установленный пакет GigaAM;
- модель: `gigaam/v3_e2e_rnnt`;
- рабочий ASCII-cache: `%ProgramData%\gigaam_cache`;
- отдельное окружение Python 3.12 обязательно для проверенного runtime;
- `ffmpeg` и `ffprobe` доступны из PATH.

Опциональные ranges backend-а зафиксированы в `requirements-gigaam.txt`, а
точный Windows/Python 3.12 graph - в
`constraints-gigaam-py312-windows.txt`. Проверенный source revision:
`salute-developers/GigaAM@6e4b027c6fb554e09e8b9059b757a175295ab879`.

```powershell
git clone https://github.com/salute-developers/GigaAM.git "$env:USERPROFILE\GigaAM"
git -C "$env:USERPROFILE\GigaAM" checkout 6e4b027c6fb554e09e8b9059b757a175295ab879
py -3.12 -m venv C:\ma-gigaam312
C:\ma-gigaam312\Scripts\python.exe -m pip install `
  -c constraints-gigaam-py312-windows.txt `
  -r requirements-gigaam.txt
C:\ma-gigaam312\Scripts\python.exe -m pip check
```

Короткий ASCII path для venv снижает риск `WinError 206` при распаковке Torch.
Upstream pin ONNX 1.19 не используется: в нём есть известные advisory. Exact
lock фиксирует проверенный inference-only override ONNX 1.22.0; модельная
загрузка, short-speech ASR и импорт `gigaam.onnx_utils` проходят. ONNX export
модели не является поддерживаемым сценарием MeetingAgent.

Причина ASCII-cache: `sentencepiece` в GigaAM может падать на пути к tokenizer с кириллицей в `%USERPROFILE%\.cache\gigaam`. Поэтому wrapper использует `%ProgramData%\gigaam_cache` и при необходимости копирует туда уже скачанные файлы модели.

## Основная Команда В Карточку Встречи

```powershell
C:\ma-gigaam312\Scripts\python.exe scripts\22_transcribe_meeting.py `
  --meeting-dir meetings\YYYY-MM-DD__slug `
  --engine gigaam `
  --model v3_e2e_rnnt `
  --language ru `
  --force
```

Выход внутри карточки:

```text
transcript/_gigaam/
  audio_16k_mono.wav
  chunks_24s/
  raw_segments.jsonl

transcript/segments.jsonl
transcript/transcript.txt
transcript/transcript.md
transcript/transcript.srt
transcript/transcript.vtt
transcript/transcript.json
transcript/transcription_report.json
```

`transcript/_gigaam/raw_segments.jsonl` - сырой worker output. `transcript/segments.jsonl` - canonical MeetingAgent contract.

## Legacy Wrapper Для Ручного Прогона В Downloads

```powershell
.\scripts\run_gigaam_transcribe.ps1 `
  -InputPath "$env:USERPROFILE\Downloads\input.mp4" `
  -OutputDir "$env:USERPROFILE\Downloads\gigaam_input"
```

Для файла с пробелами и кириллицей передавай полный путь в кавычках:

```powershell
.\scripts\run_gigaam_transcribe.ps1 `
  -InputPath "$env:USERPROFILE\Downloads\input meeting.mp4" `
  -OutputDir "$env:USERPROFILE\Downloads\gigaam_output"
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

Эти файлы являются runtime/output-артефактами и не коммитятся в Git. В публичной документации фиксируются только обезличенные технические выводы без transcript excerpts, customer names, локальных путей и runtime output.

## Импорт Готового GigaAM JSONL

Если transcript уже был получен старым wrapper-ом или внешним инструментом:

```powershell
.\.venv\Scripts\python.exe scripts\22_transcribe_meeting.py `
  --meeting-dir meetings\YYYY-MM-DD__slug `
  --engine from-segments `
  --segments-path "$env:USERPROFILE\Downloads\gigaam_output\segments_gigaam.jsonl" `
  --force
```

Скрипт нормализует внешний JSONL в canonical `transcript/segments.jsonl`, пересобирает все transcript exports и обновляет `meeting.json`.

## Ограничения

- используется короткий режим GigaAM, поэтому аудио режется на чанки по 24 секунды;
- diarization не выполняется;
- границы фраз могут обрываться на границах чанков;
- результат требует ручной проверки перед использованием в протоколе или сдачных документах.
