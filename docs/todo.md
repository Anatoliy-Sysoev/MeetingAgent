# Todo

Обновлено: 2026-06-08.

## Сейчас

- Live-транскрибация начата: есть optional Vosk backend, `scripts/33_live_transcribe_meeting.py`, schema support для `live_*` artifacts и unit tests без реального ASR.
- Скачать Vosk RU модель в ignored `models/vosk/` и выполнить локальный smoke:
  `scripts/33_live_transcribe_meeting.py --meeting-dir <meeting> --engine vosk --model-path models/vosk/vosk-model-small-ru-0.22 --input-wav <meeting>\source\audio_16k_mono.wav --source MIX --duration-sec 30 --force`.
- После file-smoke проверить microphone capture (`--source MIC`) и отдельно определить Windows loopback/system-audio путь для `SYS`.
- Провести сравнительный live-ASR эксперимент Vosk vs T-one на 2-3 реальных русскоязычных встречах; не делать T-one default без проверки качества на широкополосном meeting audio.
- Meeting smoke в Docker доведен до local indexed state: transcript import, speaker merge, chunks, enrichment, meeting chunk/artifact export и `31_meeting_search.py` прошли на локальной private встрече.
- Перезапустить Ollama через `.\scripts\start_ollama_local.ps1 -Restart`, чтобы активный server использовал canonical `C:\ollama-models`.
- Проверить `ollama list`, `ollama show qwen3.5:4b`, `ollama show bge-m3` и `/api/tags` из Docker.
- После подтверждения `qwen3.5:4b` повторить `scripts/29_analyze_meeting.py --mode ollama-map-reduce --model qwen3.5:4b --force --recompute-partials` на локальной meeting card.
- После успешного LLM map-reduce заново выполнить `scripts/32_index_meeting_artifacts.py` и smoke `scripts/31_meeting_search.py` по решениям, задачам, рискам и открытым вопросам.
- Зафиксировать public-safe выводы по времени и качеству `large-v3-turbo` ASR и `sherpa-onnx` diarization без публикации реальных meeting artifacts.
- Добавить/проверить Docker cache для HuggingFace models, чтобы `large-v3-turbo` не скачивался заново в каждом одноразовом контейнере.
- Закоммитить public-safe docs/config изменения отдельным коммитом.
- Проверить публичное дерево на приватные строки перед следующим push.
- При каждом новом публичном артефакте сверяться с `AGENTS.md`: Git хранит только public-safe код/docs/examples/tests, приватные corpus/runtime/eval остаются локально.
- P0 по corpus key закрыт: live `/health` при `ASU_JUNE_BOT_ACTIVE_CORPUS=ntk` подтверждает `corpus_key=ntk` и пути `data/asu_june_bot_ntk/*`.
- Targeted live Q030/Q031 закрыт: оба ответа дают `Этап 3 (ФТ3)` и `finish_reason=stop`.
- Targeted live Q041-Q044 закрыт: ответы содержат требуемые ФТТ anchors и `finish_reason=stop`.
- Открытый live дефект: Q040 про протокол передачи данных остается false `no_answer`, хотя HTTPS anchor доступен в контексте. Следующий фикс должен запрещать false no_answer при strong ФТТ evidence для protocol intent или улучшать selection/prompt для Q040.
- Для Windows/Ollama canonical runbook зафиксирован в `docs/operations/OLLAMA_LOCAL_RUNTIME.md`; следующий шаг - после проверки аккуратно решить, удалять ли дубли model store.
- До нового pivot собрать и проверить локальный `gold.jsonl`: manual review уже давал ошибочные метки, поэтому pivot без gold key нельзя считать надежным основанием для выбора следующего bucket.
- Разметить generated `manual_review` файл из ignored `data/diagnostics/` и затем пересчитать pivot через `scripts/diagnostics/pivot_manual_review.py`.
- Расширить локальный `gold.jsonl` точными `expected_answer_facts` / `negative_facts` для табличных и конфликтных вопросов.
- Следующий retrieval bucket: table expansion для запросов вида "перечисли требования Этапа 3" без изменения persisted chunks и без реэмбеддинга.
- `integration_ftt` required-anchor source selection закрыт на targeted Q040-Q044 для локального qwen3.5:4b.
- Следующий quality bucket: исправить Q040 false no_answer, затем ручная проверка ответов Q040-Q044 после source selection, затем held-out integration questions вне Q040-Q044, и только после этого пересчет pivot по 100 вопросам.
- Если Q040-Q044 ручная проверка подтвердит качество, следующий retrieval bucket выбирать по обновленному pivot, а не по старой сводке.
- При ручной разметке и eval считать `status=truncated` отдельным дефектом: это не `answered/ok`, даже если часть ответа выглядит правдоподобно.
- Для демо через Telegram держать API на `corpus_key=ntk`, модель `qwen3.5:4b`, Telegram `max_tokens=1400`; перед показом проверять `/health`, `ollama ps` и короткий `/chat` без `finish_reason=length`.
- Вернуть Track B в отдельный roadmap/implementation bucket: source hygiene и свежесть корпуса, исключение `Архив`/черновиков/шаблонов/temp-файлов, канонизация версий, дедупликация, инкрементальная синхронизация и политика ссылок на актуальные документы.
- Все новые chat/eval прогоны запускать на `qwen3.5:4b`; старые model-comparison артефакты считать historical baseline.
- Guard bucket для ПМИ/ПСИ/этапов/сервисов/out-of-scope закрыт targeted: project/testing/stage/service queries -> allow, weather/currency/drawing/coding/math -> refused, mixed project + drawing/weather/code -> refused.
- Поддерживать tracked quality/docs только в синтетическом или обезличенном виде.
- Не коммитить runtime outputs из `data/`, `logs/`, `vector_db/`, `watched_folder/`, `meetings/`.
- Если потребуется полная очистка GitHub history, выполнить отдельную согласованную history purge процедуру.

## OSS Packaging

- Сохранять открытыми текущие GitHub issues как публичный backlog.
- Добавить маленький public sample dataset без реальных документов и транскриптов.
- Добавить короткий transcript-to-protocol CLI quickstart на синтетическом примере.
- Настроить release workflow и changelog automation.
- Улучшить parity между English/Russian docs.
- Рассмотреть GitHub Pages для публичной документации.
- Подготовить `v0.1.1` release после documentation cleanup.

## Product Backlog

- UI для запуска транскрибации локального видео.
- Live transcription UI/API: старт/стоп live session, просмотр partials/final segments, safe handoff в offline transcript pipeline.
- Silero VAD для live endpointing/noise handling после базовой проверки Vosk/T-one.
- Speaker diarization: проверить `sherpa-onnx` на 2-3 реальных встречах, подобрать `num_speakers`/`cluster_threshold`/`num_threads`, затем решить нужен ли optional pyannote backend.
- Для diarization добавить CLI/config параметр `--num-threads`; текущий CPU runtime чувствителен к числу потоков.
- Зафиксировать ограничение maximum-overlap: длинный ASR-сегмент с двумя говорящими получает одного speaker; будущий слой - re-segmentation или word-level timestamps.
- Ручной speaker mapping `SPEAKER_XX -> имя/роль`.
- DOCX export для протокола встречи.
- Quality eval для meeting artifacts на синтетических наборах.
- API/Telegram integration для meeting search без обхода source-grounding.

## Security / Privacy

- Добавить anonymization pipeline для приватных transcripts.
- Добавить pre-commit или CI check на запрещенные пути, секреты и приватные corpus names.
- Если требуется полная очистка GitHub history, выполнить отдельный согласованный `git filter-repo`/BFG проход и пересоздать release/tag.
