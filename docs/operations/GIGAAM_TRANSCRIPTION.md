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

## Изолированный Пилот Multilingual CTC (#340)

`multilingual_ctc` (220M) устанавливается отдельно от штатной `v3_e2e_rnnt`.
Это не GigaAM v4 и не автоматическая миграция API/UI. Не обновляйте рабочие
исходники, venv, config.yaml или кэш v3 ради эксперимента.

Ревизия исходников пилота:
`7447938d791c4f3e643386ee22c33777004293a5`. Старый штатный source revision
не содержит Multilingual. Пилот использует отдельный inference-only CPU lock
с Hydra 1.3.7 и override ONNX 1.22 вместо upstream pin 1.19; source импортируется
через явный PYTHONPATH/--gigaam-root, а не через pip install upstream с заменой
зависимостей. Для общего CLI дополнительно нужен jsonschema из core constraints.
Longform/pyannote, Transformers и CUDA для коротких 24-секундных чанков не нужны.

Из корня MeetingAgent, в отдельном PowerShell-окне:

```powershell
$pilot = "C:\ma-gigaam-multilingual"
py -3.12 -m venv "$pilot\venv"
git clone https://github.com/salute-developers/GigaAM.git "$pilot\source"
git -C "$pilot\source" checkout 7447938d791c4f3e643386ee22c33777004293a5
& "$pilot\venv\Scripts\python.exe" -m pip install `
  -c constraints-gigaam-multilingual-py312-windows.txt `
  -r requirements-gigaam-multilingual-py312.in
& "$pilot\venv\Scripts\python.exe" -m pip check
$env:PYTHONPATH = "$pilot\source"
```

При уже существующем каталоге сначала проверьте его назначение; команды
создания/clone не предназначены для перезаписи существующей установки.
Запускать загрузку в память и ASR только после завершения других тяжёлых
ASR/diarization/LLM задач и проверки свободной ОЗУ. Веса скачиваются локально
из официального CDN, для `multilingual_ctc` не нужен HF_TOKEN:

```powershell
& "$pilot\venv\Scripts\python.exe" -c "import gigaam; gigaam.load_model('multilingual_ctc', device='cpu', download_root=r'C:\ma-gigaam-multilingual\cache'); print('model loaded')"
```

Только доверенные официальные веса: upstream использует pickle-based
torch.load(weights_only=False). Сравните checksum с закреплённым source;
MD5 upstream проверяет целостность, но не заменяет доверенный источник.
Скачанный checkpoint занимает 883212109 байт (около 842 MiB). SHA-256
проверенного файла:
`24aa92be5994fa8b9f1ce40fe59fc9693de0ce6af415011b7c0b4480c7fcf733`.

Для проверки транскрибации создайте отдельную карточку, не используйте --force
над результатом рабочей v3. После завершения всех других тяжёлых задач:

```powershell
& "$pilot\venv\Scripts\python.exe" scripts/22_transcribe_meeting.py `
  --meeting-dir "meetings/<отдельная-pilot-карточка>" `
  --engine gigaam --model multilingual_ctc `
  --gigaam-root "$pilot\source" --gigaam-cache-root "$pilot\cache"
```

CLI передаёт явные model/source/cache в worker; без --model сохраняется
`v3_e2e_rnnt`. Runtime installation/freeze reports, аудио, веса и результаты
сравнений не коммитятся. Успешные install/download/import не доказывают
качество ASR: отдельно фиксируйте реальный smoke, время/память, термины,
пунктуацию и таймкоды. Короткий smoke не заменяет сравнение с v3/Whisper.

Первый аудит исходного dependency graph выявил три advisory Hydra 1.3.4.
В пилоте они устранены обновлением до 1.3.7; повторный аудит установленного
окружения не нашёл известных уязвимостей. Не используйте старый GigaAM lock
для повторной установки пилота. Обновление штатного v3 вынесено в #341 и
не выполняется под работающим worker. Даже исправленная Hydra не является
песочницей для недоверенных конфигураций или checkpoint-файлов.

Реальная проверка пилота: 10 секунд русской речи на CPU, два потока;
загрузка около 9 секунд, ASR около 4 секунд, 20 слов с допустимыми границами.
Общий CLI создаёт canonical exports и report, но в coarse wrapper обнаружен
старый дефект #342: для короткого последнего чанка end/report duration могут
завышаться до полного chunk_seconds. Не считайте этот span точной границей
речи. Новые пословные timestamps прямого API пока не сохраняются wrapper-ом.
Качество терминов/пунктуации и сравнение с v3/Whisper ещё не оценивались.

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
