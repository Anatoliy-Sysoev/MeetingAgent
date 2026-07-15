# Diart: Изолированный Пилот Live-Диаризации

Обновлено: 2026-07-15.

Diart используется как опциональный CPU-sidecar для предварительного
определения говорящих на SYS-дорожке. Он не заменяет Vosk/Whisper/GigaAM: ASR
создаёт текст, а Diart создаёт интервалы `кто говорил когда`.

## Граница Пилота

- основной API, GigaAM и sherpa-onnx не получают зависимости Diart;
- контейнер работает на Python 3.10 и Ubuntu 22.04/FFmpeg 4.4;
- CPU Torch ставится из официального CPU wheel index, CUDA-пакеты запрещены;
- synthetic streaming smoke не скачивает модели и не требует токена;
- реальные модели загружаются только после явного `--load-models`;
- модельные cache/output находятся в ignored `data/diart_*`.

Проверенный стек:

```text
diart 0.9.2
pyannote.audio 3.1.1
torch / torchaudio 2.2.2+cpu
torchvision 0.17.2+cpu
numpy 1.26.4
onnxruntime 1.18.0
```

Upstream рекомендует `pyannote.audio<3.1` для воспроизведения результатов
исследования. В пилоте используется 3.1.1: версия 3.0.1 жёстко тянет
`onnxruntime-gpu`, что противоречит CPU-only deployment. Качество поэтому
обязательно сравнивается с offline sherpa-onnx на реальных встречах.

## Установка И Synthetic Smoke

```powershell
docker compose --profile diart build diart
docker compose --profile diart run --rm diart
```

Первая чистая сборка скачивает системные пакеты и CPU Torch, поэтому требует
сети и на проверенном Windows/Docker Desktop заняла около 6 минут. Повторные
сборки и запуски используют Docker layers; образ без model cache занимает
около 575 MB.

Успешный результат содержит:

```json
{"ok": true, "runtime": "diart-isolated-cpu", "synthetic_stream": {"tracks": 1}}
```

Этот smoke проверяет импорт полного стека, создание incremental pipeline,
подачу 16 kHz WAV как потока и получение speaker track. Он не оценивает
качество реальных моделей.

## Доступ К Реальным Моделям

1. Принять условия `pyannote/segmentation-3.0` и `pyannote/embedding` на
   Hugging Face.
2. Создать read-only Hugging Face token.
3. Добавить `HF_TOKEN=...` только в локальный `.env`.
4. Запустить:

```powershell
docker compose --profile diart run --rm diart --json --load-models
```

Токен не печатается и не записывается в Git. Cache сохраняется в
`data/diart_cache/`, поэтому после первой загрузки модель не скачивается заново.
Hugging Face, pyannote, Torch, XDG и Matplotlib cache paths явно направлены в
этот volume; контейнеру не требуется запись в read-only домашний каталог.

Проверенный real-model preflight возвращает `ok: true` и строит pipeline с
обеими моделями. Legacy `pyannote/embedding` при загрузке предупреждает, что
checkpoint обучен на старых версиях pyannote.audio/Torch; поэтому успешная
загрузка не заменяет quality benchmark на русской встрече.

Если старый профиль завершается с `Read-only file system: /home/meetingagent/.cache`,
обновите `main` и повторите команду: начиная с #259 Torch/XDG cache не использует
домашний каталог контейнера.

## Localhost Sidecar

После успешного real-model preflight включите интеграцию только в локальном
ignored `config.yaml`:

```yaml
live:
  diarization:
    enabled: true
    base_url: "http://127.0.0.1:8765"
    timeout_seconds: 900
```

Запустите sidecar и Core API:

```powershell
docker compose --profile diart-live up -d diart-api
.\.venv\Scripts\python.exe scripts\meeting_agent_api.py --host 127.0.0.1 --port 8000
```

Проверка sidecar:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/health
```

Контейнер видит `meetings/` только read-only, принимает только безопасный
`meeting_id` и обрабатывает `source/live_audio.SYS.wav`. После Stop Core:

1. получает speaker turns через localhost HTTP;
2. связывает их с финальными Vosk-сегментами по максимальному overlap;
3. атомарно пишет `transcript/live/live_diarization.SYS.json`;
4. перестраивает no-index MIX timeline со `SPEAKER_XX`;
5. при недоступном sidecar сохраняет запись и добавляет bounded warning вместо
   перевода live-сессии в failed.

Артефакт и live draft не индексируются. Имена/роли назначаются существующим
Speaker Mapping UI, а offline sherpa-onnx остаётся канонической диаризацией.

## Следующий Streaming Этап

Diart должен получать непрерывный 16 kHz mono SYS-поток до удаления тишины,
чтобы сохранить реальную временную шкалу. MIC известен как локальный
пользователь и не требует кластеризации. Speaker turns Diart связываются с
финальными Vosk-сегментами по максимальному временному overlap. Live labels
остаются предварительными; после встречи sherpa-onnx выполняет offline
refinement, а существующий Speaker Mapping UI назначает имена и роли.

## Известные Ограничения

- без `HF_TOKEN` реальные gated-модели не загружаются;
- labels являются анонимными и могут изменяться по ходу разговора;
- legacy embedding checkpoint выдаёт compatibility warnings на современном
  CPU runtime; влияние оценивается только реальным benchmark;
- одновременная речь, эхо и компрессия conferencing-клиента ухудшают качество;
- pilot image имеет размер около 575 MB без model cache;
- текущая интеграция запускает Diart после финализации SYS WAV; speaker labels
  не появляются chunk-by-chunk во время активной записи;
- автоматическая reconciliation предварительных labels с offline sherpa пока
  не реализована.
