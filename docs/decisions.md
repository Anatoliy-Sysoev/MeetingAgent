# Решения

## 2026-05-06 - Одна Папка, Один Git-Репозиторий

Решение: каждый пет-проект получает отдельную папку и отдельный Git-репозиторий.

Почему:

- зависимости остаются изолированными;
- история остается читаемой;
- проекты можно независимо переносить, пушить, архивировать и удалять;
- Codex может восстановить контекст по файлам репозитория.

## 2026-05-06 - Обязательные Файлы Памяти Проекта

Решение: в каждом пет-проекте должны быть `README.md`, `AGENTS.md`, `docs/context.md`, `docs/decisions.md`, `docs/todo.md` и `.env.example`.

Почему:

- новые треды быстрее восстанавливают контекст;
- решения не теряются;
- следующие действия остаются явными;
- секреты и локальное состояние не попадают в Git.

## 2026-05-06 - Local-First По Умолчанию

Решение: MeetingAgent по умолчанию обрабатывает проектные документы, встречи, транскрипты, индексы и артефакты локально.

Почему:

- рабочие документы и записи встреч могут быть конфиденциальными;
- локальные ASR/RAG/LLM workflows уменьшают риск утечки данных;
- cloud-интеграции должны быть явным opt-in.

## 2026-05-06 - Не Коммитить Локальные Рабочие Данные

Решение: игнорировать `.env`, `config.yaml`, `.venv/`, `data/`, `logs/`, `vector_db/`, `watched_folder/`, runtime meeting cards, media files и private eval reports.

Почему:

- эти файлы могут быть большими;
- они могут содержать конфиденциальные документы, транскрипты, индексы или токены;
- это machine-specific runtime state, а не исходники продукта.

## 2026-05-06 - bge-m3 С num_ctx 8192

Решение: каждый Ollama embedding-запрос должен отправлять `options.num_ctx=8192` и `keep_alive=24h`.

Почему:

- Ollama может по умолчанию запускать embedding model с меньшим context window;
- реальные chunks после токенизации могут превышать дефолтный лимит;
- явный контекст предотвращает context overflow.

## 2026-05-07 - Numpy/Faiss Friendly Retrieval

Решение: держать retrieval backend локальным и переносимым, с возможностью numpy/faiss индекса вместо тяжелой обязательной vector database.

Почему:

- public OSS quickstart должен быть воспроизводимым на обычном локальном ПК;
- индексы являются runtime artifacts и не должны публиковаться;
- backend можно менять без изменения canonical chunk/transcript contracts.

## 2026-05-08 - Meeting Card Как Каноническая Единица

Решение: встреча хранится как папка с `meeting.json`, исходником, transcript, chunks, artifacts и logs.

Почему:

- pipeline можно перезапускать по шагам;
- артефакты встречи остаются трассируемыми;
- downstream search/protocol/export получают стабильный контракт.

## 2026-06-04 - Public Tree Не Содержит Private Runtime/Eval Artifacts

Решение: private corpora, runtime reports, real transcripts, local indexes and customer-specific setup docs are not tracked in Git.

Почему:

- репозиторий открыт публично;
- реальные документы и отчеты могут раскрывать внутренний контекст;
- для OSS достаточно синтетических examples и обезличенных quality templates.

## 2026-06-05 - qwen3.5:4b Как Единая Локальная Chat-Модель

Решение: Project Knowledge Bot, CLI/API/Telegram defaults, public examples and local `config.yaml` use `qwen3.5:4b` as the only штатная chat-модель.

Почему:

- targeted quality checks на локальном корпусе подтвердили рабочий baseline для `qwen3.5:4b`;
- единая модель упрощает regression runs, сравнение качества и диагностику false negatives;
- альтернативные модели больше не должны попадать в штатные quickstarts/defaults без отдельного эксперимента.

Следствия:

- embeddings остаются на `bge-m3`;
- runtime indexes and chunks не пересобираются из-за смены chat-модели;
- historical eval artifacts с прежними моделями остаются историческими снимками и не переписываются.

## 2026-06-08 - sherpa-onnx Как Default Speaker Diarization

Решение: для локальной diarization по умолчанию использовать optional `sherpa-onnx` backend с ONNX-моделями `sherpa-onnx-pyannote-segmentation-3-0/model.onnx` и `wespeaker_en_voxceleb_resnet34_LM.onnx`.

Почему:

- путь работает CPU-first и не требует HuggingFace token/license acceptance в runtime;
- зависимости изолированы в `requirements-diarization.txt` и optional Docker image, чтобы не конфликтовать с GigaAM/faster-whisper;
- ONNX-модели хранятся локально в ignored `models/diarization/`, а не в Git;
- результат сохраняется в стабильный контракт `transcript/diarization.jsonl` и затем используется `scripts/24_merge_transcript_speakers.py`.

Следствия:

- `pyannote.audio` остается optional high-quality/fallback направлением, но не является текущим default;
- реальные имена людей не определяются автоматически: используется `SPEAKER_XX`, ручной mapping остается отдельным будущим слоем;
- качество нужно проверять на 2-3 реальных русскоязычных встречах с подбором `num_speakers`, `cluster_threshold` и числа потоков.

## 2026-06-08 - large-v3-turbo Для Качественной Offline-Транскрибации

Решение: для продуктового offline ASR профиля использовать `faster-whisper large-v3-turbo` с `language=ru` и `compute_type=int8`; `small` оставлять только для черновых smoke/live сценариев.

Почему:

- встречные протоколы, задачи и решения зависят от качества transcript;
- `small` быстрее, но может ухудшать смысловые артефакты и последующий RAG;
- текущий реальный smoke на встрече 2026-06-08 должен валидировать именно `large-v3-turbo`.

Следствия:

- если `small` был запущен случайно и transcript artifacts еще не созданы, его можно останавливать без потери результата;
- Docker/HuggingFace cache нужно настроить так, чтобы `large-v3-turbo` не скачивался заново при каждом запуске одноразового контейнера.

## 2026-06-08 - Единый ASCII Ollama Model Store

Решение: для локального Windows runtime закрепить canonical Ollama model store `C:\ollama-models` и запускать Ollama через `scripts/start_ollama_local.ps1`.

Почему:

- `qwen3.5:4b` и `qwen3.5:9b` уже лежали в `C:\ollama-models`, но активный Ollama server после перезагрузки смотрел в другой store;
- Docker-контейнеры MeetingAgent обращаются к активному Ollama API через `host.docker.internal:11434`, а не читают model store напрямую;
- `bge-m3` может падать при загрузке blob из Unicode-пути профиля Windows;
- один ASCII store снижает риск расхождения между CLI, Docker, API и Telegram.

Следствия:

- перед meeting analysis, API или bot smoke нужно проверять `ollama list` и `/api/tags`;
- дубли `C:\Users\<user>\.ollama\models` и `C:\ollama_models` не удаляются автоматически;
- очистку дублей делать только после ручного подтверждения, что `C:\ollama-models` используется активным `ollama serve`.

## 2026-06-08 - Vosk Как Первый Live ASR Backend

Решение: для первого локального live-transcription MVP использовать optional Vosk backend через `scripts/33_live_transcribe_meeting.py`.

Почему:

- Vosk поддерживает streaming/partial ASR и локальный CPU-first запуск без cloud API;
- backend подходит для чернового live transcript с таймкодами и источником `MIC`/`SYS`/`MIX`;
- зависимости вынесены в `requirements-live.txt`, чтобы не утяжелять основной offline/RAG runtime;
- final transcript для протоколов и RAG остается offline-проходом через `scripts/22_transcribe_meeting.py` (`large-v3-turbo`, GigaAM или импорт готовых segments).

Следствия:

- live outputs пишутся отдельно в `transcript/live/` и не перезаписывают canonical `transcript/segments.jsonl`;
- `live_partials.jsonl` является черновым runtime artifact и не должен индексироваться как источник истины;
- T-one остается кандидатом для отдельного сравнительного прогона на 2-3 реальных встречах, потому что модель ориентирована на телефонный домен;
- Silero VAD остается будущим слоем для устойчивого endpointing/noise handling, а не обязательной зависимостью первого live MVP.
