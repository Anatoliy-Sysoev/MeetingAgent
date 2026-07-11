# Решения

## 2026-07-10 - Host Allowlist И Bootstrap DNS-Rebinding Defense

Решение: MeetingAgent проверяет каждый HTTP/WebSocket `Host` через встроенный allowlist middleware. Local bootstrap bypass требует одновременно direct loopback peer, trusted local Host и отсутствие proxy headers.

Почему:

- loopback peer без Host validation уязвим к browser DNS rebinding;
- `security.allowed_hosts` раньше был только advisory config и не влиял на runtime;
- стандартный Starlette middleware в используемой версии делит Host по первому `:` и некорректно обрабатывает bracketed IPv6, поэтому используется собственный строгий parser для hostname/port/IPv6;
- `allowed_origins` не является заменой Host validation.

Следствия:

- safe local hosts включены по умолчанию; Docker profile явно добавляет service host `api`;
- self-hosted mode без явного host allowlist не стартует;
- `*`, schemes, paths, ports, malformed and duplicate Host values rejected;
- custom hosts задаются через `security.allowed_hosts` или `MEETINGAGENT_ALLOWED_HOSTS`.

## 2026-07-10 - Telegram Adapter Fail-Closed

Решение: Telegram adapter обращается к защищённому `/chat` только с machine Bearer token из `MEETINGAGENT_API_TOKEN`. Доступ к Telegram по умолчанию запрещён без `ASU_JUNE_BOT_ALLOWED_CHAT_IDS`; allow-all требует отдельного явного opt-in.

Почему:

- после включения API auth запросы Telegram без Bearer token всегда получают 401;
- публичный Telegram token без chat allowlist превращает private project assistant в доступный извне сервис;
- raw HTTP bodies, local paths и exception URLs не должны пересылаться пользователям или попадать в console logs вместе с Telegram token.

Следствия:

- bot startup завершается fail-closed при placeholder/missing token или access policy;
- Telegram errors и health messages используют bounded public-safe fields;
- Docker and PowerShell получают secrets только из process environment / ignored `.env`.

## 2026-07-10 - Public Tree И Private Config Overlays

Решение: публичный Git содержит только synthetic/default corpus configuration. Customer-specific corpus profiles and vocabulary хранятся в ignored `configs/asu_june_bot/*.local.yaml`; loader накладывает local overlay поверх публичного YAML.

Почему:

- ignore rules не защищают данные, которые уже были tracked;
- customer-specific eval questions, transcript excerpts, names и corpus paths не являются частью OSS-продукта;
- локальный overlay сохраняет private runtime без dirty tracked config;
- очистка текущего дерева и переписывание опубликованной Git history имеют разный риск и выполняются отдельными задачами.

Следствия:

- `docs/quality/` ограничен curated allowlist и synthetic fixtures;
- public-safety regression test проверяет allowlist, known private markers и literal Windows user-profile paths;
- history purge выполняется только после backup и явного согласования force-push.

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
- дубли `%USERPROFILE%\.ollama\models` и `C:\ollama_models` не удаляются автоматически;
- очистку дублей делать только после ручного подтверждения, что `C:\ollama-models` используется активным `ollama serve`.

## 2026-06-08 - Vosk Как Первый Live ASR Backend

Решение: для первого локального live-transcription MVP использовать optional Vosk backend через `scripts/33_live_transcribe_meeting.py`.

Почему:

- Vosk поддерживает streaming/partial ASR и локальный CPU-first запуск без cloud API;
- backend подходит для чернового live transcript с таймкодами и источником `MIC`/`SYS`/`MIX`;
- зависимости вынесены в `requirements-live.txt`, чтобы не утяжелять основной offline/RAG runtime;
- final transcript для протоколов и RAG остается offline-проходом через `scripts/22_transcribe_meeting.py` (`large-v3-turbo`, GigaAM или импорт готовых segments).

Следствия:

- live outputs пишутся отдельно в source-scoped файлы `transcript/live/live_segments.MIC.jsonl`, `live_segments.SYS.jsonl` или `live_segments.MIX.jsonl` и не перезаписывают canonical `transcript/segments.jsonl`;
- Ctrl+C в live backend считается штатным graceful stop: накопленные segments/partials финализируются и записываются;
- завершение live draft оставляет `processing_status=processing`, чтобы финальный offline ASR мог стартовать без `--force`;
- `live_partials.jsonl` является черновым runtime artifact и не должен индексироваться как источник истины;
- T-one остается кандидатом для отдельного сравнительного прогона на 2-3 реальных встречах, потому что модель ориентирована на телефонный домен;
- Silero VAD остается будущим слоем для устойчивого endpointing/noise handling, а не обязательной зависимостью первого live MVP.

## 2026-06-08 - Silero VAD Как Optional Live Preprocessing

Решение: добавить Silero VAD как optional preprocessing слой для live/file-smoke ASR через `scripts/33_live_transcribe_meeting.py --vad silero`.

Почему:

- VAD должен быть backend-agnostic: один слой speech detection перед Vosk, T-one или будущим backend;
- Silero VAD локальный, легкий и подходит для CPU-first speech detection;
- optional режим позволяет сравнить baseline `--vad none` против `--vad silero` на реальных встречах без смены основного ASR-контракта.

Следствия:

- зависимости остаются в `requirements-live.txt`, а не в основном `requirements.txt`;
- первый реализованный режим Silero VAD работает для `--input-wav`, где можно заранее получить speech windows;
- microphone/system-loopback streaming VAD остается следующим шагом, потому что нужно сохранить корректные live таймкоды и endpointing.

## 2026-07-07 - Auth Providers Через Локальный RBAC

Решение: внешние browser identity providers должны только аутентифицировать пользователя, а права в MeetingAgent остаются локальными ролями `viewer`, `editor`, `admin`; machine/API fallback остаётся отдельным `MEETINGAGENT_API_TOKEN`.

Почему:

- browser users и scripts/automation имеют разные threat models;
- внешний provider email/subject не должен автоматически давать `editor` или `admin`;
- CLI, Telegram adapter, локальные smoke/eval workflows должны продолжать работать через Bearer token без OAuth;
- будущие Yandex ID, Telegram, Google, Microsoft Entra или Keycloak providers должны подключаться как adapters без переписывания RBAC.

Следствия:

- текущий local login остаётся рабочим MVP/self-hosted вариантом;
- Yandex ID фиксируется как первый planned external provider, но не как единственный возможный provider;
- admin console должна требовать browser user session + local `admin`, а machine token не должен открывать admin UI;
- подробный ADR: `docs/architecture/ADR-0039-auth-providers.md`.

## 2026-07-07 - Admin Console Как Отдельная Admin Surface

Решение: admin console должен быть отдельной browser-user surface для `admin` роли, а не расширением machine/API токена.

Почему:

- machine token нужен для automation, CLI и service-to-service, а не для интерактивного управления пользователями;
- user/role changes, token rotation, destructive meeting actions и diagnostics требуют audit trail и явных подтверждений;
- текущий admin API уже покрывает users/security status, но UI и aggregate jobs/audit/settings должны развиваться по отдельному контракту.

Следствия:

- machine principal не получает admin UI доступ по умолчанию;
- admin mutations требуют cookie session + CSRF;
- admin API/UI не должны возвращать raw secrets, OAuth tokens, session tokens, local paths или raw tracebacks;
- контракт: `docs/architecture/ADMIN_CONSOLE.md`.

## 2026-07-11 - Public Liveness Отделён От Runtime Diagnostics

Решение: публичный `GET /health` возвращает только `status`, `service` и
`version`, не обращаясь к корпусу, индексу или Ollama. Подробная проверка
перенесена в `GET /admin/diagnostics/health` и требует browser-сессию с
`users.manage`; machine token туда не допускается.

Почему:

- liveness probe должен быть быстрым и не зависеть от доступности Ollama;
- абсолютные пути, corpus metadata, список локальных моделей и счётчики индекса
  раскрывают лишнюю информацию неаутентифицированному клиенту;
- тексты сетевых исключений могут содержать URL, proxy credentials, response
  body или локальные пути.

Следствия:

- Docker и внешние monitor probes продолжают использовать `/health`;
- операторская диагностика доступна только локальному admin user через RBAC;
- ошибки Ollama в API представлены стабильным кодом `ollama_unavailable`, без
  исходного текста исключения.
