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
- это ограничение снято решением от 2026-07-13 ниже: MIC/SYS используют incremental VAD и отдельную карту исходного времени.

## 2026-07-13 - Streaming Silero VAD С Картой Исходного Времени

Решение: для live MIC/SYS применять один incremental Silero `VADIterator` к
canonical mono 16 kHz PCM, но передавать в Vosk только принятые speech frames.
Каждый принятый блок сохраняет диапазон исходных capture frames; word timestamps
Vosk переводятся обратно из сжатой шкалы accepted audio в wall-clock шкалу
исходной дорожки.

Почему:

- простой discard silence сжимает время Vosk и делает таймкоды непригодными для
  перехода к оригиналу;
- общий consumer гарантирует одинаковую семантику для MIC и SYS после
  WASAPI/SoXR canonicalization;
- 512-frame stateful inference соответствует streaming-контракту Silero и не
  требует загружать всю встречу в память;
- offline `--input-wav` остается детерминированным precomputed-window режимом,
  поэтому существующие smoke-сценарии не меняются.

Следствия:

- partial/final outputs используют исходную временную шкалу и finalized segments
  принудительно остаются монотонными и непересекающимися;
- параметры VAD ограничены сверху, чтобы ошибочная локальная конфигурация не
  создавала неограниченный pre-speech buffer;
- `live_report.<SOURCE>.json` содержит принятые/отфильтрованные frames, длительность
  фильтрации, speech windows, short-speech drops и warnings;
- Silero остается optional dependency из `requirements-live.txt`;
- native idle-read безопасность WASAPI вынесена в #213 и не смешивается с
  алгоритмом VAD.

## 2026-07-13 - Non-Blocking WASAPI Loopback Clock

Решение: SYS capture не вызывает blocking `stream.read()` вслепую. Runtime
проверяет `get_read_available()`, читает не больше доступного числа native frames
и ведет monotonic wall-clock с коротким startup grace. Если output device не
выдает packet, соответствующий интервал заполняется нулевым PCM до SoXR/VAD.

Почему:

- PyAudio blocking read ожидает запрошенные frames и на полностью idle WASAPI
  loopback может не вернуться в пределах `--duration-sec`;
- PortAudio гарантирует, что `get_read_available()` сообщает число frames,
  доступных без blocking wait;
- вставка native-rate silence сохраняет elapsed time и не сдвигает последующую
  речь, а Silero при включенном VAD отфильтровывает эту тишину;
- polling с фиксированным quantum предотвращает busy loop на микроскопических
  приращениях monotonic clock.

Следствия:

- duration-limited idle SYS завершается около заданной длительности плюс время
  открытия устройства/startup grace;
- Ctrl+C обрабатывается Python loop и сохраняет накопленный draft;
- short/non-PCM reads, отрицательный available count и backend exceptions
  завершаются fail closed;
- report содержит poll/read/error/idle frames и seconds без device names или
  локальных путей.

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

## 2026-07-11 - Docker Runtime Deny-By-Default И Non-Root

Решение: production image получает только явный allowlist runtime-файлов,
работает как UID/GID `10001:10001`, а Compose по умолчанию публикует порт только
на `127.0.0.1`. Non-loopback publish требует явного
`MEETINGAGENT_DEPLOYMENT_MODE=self_hosted`.

Почему:

- `.gitignore` не ограничивает Docker build context, поэтому `COPY .` мог
  включить ignored `.env`, private corpus или runtime outputs;
- root process и writable rootfs увеличивают последствия RCE/path traversal;
- Compose-порт без host IP открывался на всех интерфейсах;
- hardcoded `container_name` мешал безопасно запускать изолированные project
  stacks и конфликтовал с остановленными контейнерами.

Следствия:

- `.dockerignore` сначала исключает всё и разрешает только runtime Python,
  public configs и requirements;
- code/config в image root-owned, writable только host-mounted runtime paths;
- Compose включает read-only rootfs, `no-new-privileges`, `cap_drop: ALL` и
  отдельный `/tmp` tmpfs;
- runtime dependencies живут в `requirements.txt`, test/dev tools — в
  `requirements-dev.txt`;
- `scripts/43_container_smoke.py` проверяет non-root UID, private sentinel,
  отсутствие pytest и writable runtime directories на реально собранном image;
- self-hosted mode дополнительно использует существующий startup safety
  validator для token strength, Host allowlist и auth/proxy policy.

## 2026-07-11 - Один Full Verification Runner Для Local И CI

Решение: `scripts/46_ci_verify.py` является canonical командой проверки и
локально, и в GitHub Actions. Она выполняет `git diff --check`, compileall для
всего Python-кода и полный `pytest -q` без ограничения одним подпроектом.

Почему:

- прежний PR workflow запускал только `tests/asu_june_bot`, поэтому unit/e2e и
  live/transcription regressions могли пройти с зелёным CI;
- обычный `git diff --check` в clean CI checkout ничего не проверяет, если не
  указать base/head диапазон;
- разные local и CI команды создают дрейф и ложное ощущение воспроизводимости.

Следствия:

- Actions передаёт runner точные base/head SHA, локально runner проверяет и
  working tree, и staged index;
- PR workflow имеет только `contents: read`, fetch-depth 0, pip cache,
  20-minute timeout и отменяет устаревший run той же ветки;
- push CI запускается только для `main`, поэтому PR не получает второй
  дублирующий run от branch push;
- hardware/model/private-runtime tests могут skip только с явной причиной;
  runtime corpus/model services не требуются для deterministic CI.

## 2026-07-11 - Public Meeting Metadata Отделена От Storage Diagnostics

Решение: `GET /meetings`, `GET /meetings/{id}`, `GET
/meetings/{id}/artifacts` и `GET /meetings/{id}/media` возвращают только
явные public DTO. Файлы представлены стабильными `artifact_id`/`media_id` и
API URL, а не storage paths. Raw `meeting.json` и абсолютный путь карточки
доступны только browser-admin через `GET
/admin/diagnostics/meetings/{meeting_id}`.

Почему:

- `meeting.json` содержит исходные пути, внутренние artifact paths, RAG
  metadata и диагностические сообщения;
- сериализация карточки целиком делает новый внутренний ключ публичным по
  умолчанию и создаёт повторные утечки при расширении схемы;
- machine token предназначен для automation, а не для доступа к сырым
  локальным diagnostics.

Следствия:

- public DTO используют `extra=forbid`, bounded machine tokens и generic
  parse/read errors;
- абсолютные, drive-letter и traversal paths не попадают в meeting/media/
  artifact metadata;
- admin diagnostics остаются отдельной явно чувствительной surface, требуют
  `users.manage` и не доступны machine Bearer principal;
- внутренний pipeline может продолжать читать raw card через service layer,
  но API route не должен возвращать её напрямую.

## 2026-07-11 - Meeting Ingest Ограничен И Транзакционно Дедуплицирован

Решение: HTTP ingest ограничен `meetings.max_upload_bytes` (default 2 ГиБ),
проверяет размер до копирования и на каждом chunk, а операция `find SHA ->
allocate meeting_id -> create card` выполняется под одним thread/process-safe
advisory lock для `meetings_root`.

Почему:

- unbounded upload может заполнить системный диск временными файлами;
- check-then-create без lock позволяет двум workers создать две карточки для
  одного SHA-256;
- raw `OSError`/schema messages могут раскрывать temp/storage paths;
- FastAPI multipart parser не заменяет внешний request-body limit.

Следствия:

- oversize возвращает `413 upload_too_large`, partial temp удаляется при
  oversize, I/O failure, cancellation и после успешного create/duplicate;
- concurrent identical uploads детерминированно дают один `201` и `409` для
  остальных запросов;
- filename ограничен 255 символами, title 500 символами; public errors не
  включают исходный exception text;
- self-hosted reverse proxy должен иметь body limit не выше application limit,
  чтобы отбрасывать oversized multipart до parser/spool;
- lock file остаётся служебным runtime metadata и не коммитится.

## 2026-07-11 - Source Identity Уникальна Между Search Context Buckets

Решение: query-specific source promotion в Project Knowledge Bot использует
`chunk_id/db_id/source_id` как identity и сохраняет каждый key ровно в одном
bucket: primary либо supporting. Первый primary источник выигрывает collision;
новые matching supporting sources перемещаются в primary в исходном порядке.

Почему:

- прежняя ветка добавляла non-matching primary в supporting, не удаляя его из
  primary;
- проверка existing matching primary была недостижима, потому что его key уже
  находился в `primary_keys`;
- дубликаты раздувают prompt, искажают citation coverage и создают ложные
  diagnostics о promotion.

Следствия:

- existing primary остаётся primary и не считается promotion;
- supporting source с key, уже присутствующим в primary, удаляется как
  duplicate;
- diagnostics `ad_cc_role_mapping_promotion` появляется только при реальном
  переносе supporting -> primary и содержит только перемещённые keys;
- порядок выбранных источников детерминирован: promoted supporting в исходном
  порядке, затем исходные unique primary.

## 2026-07-11 - Job State Переживает Рестарт API, Но Pipeline Не Продолжается Автоматически

Решение: API runner хранит один active stage, один aggregate pipeline,
ограниченную историю и журнал переходов в `logs/jobs_state.json`. Snapshot
обновляется атомарно под thread/process advisory lock. После рестарта живой
дочерний процесс с совпавшим PID identity получает статус `orphaned`, а
исчезнувший процесс переводится в `failed` и открывает явный retry/resume.

Почему:

- in-memory runner забывал active job после рестарта API и позволял запустить
  вторую тяжёлую обработку поверх ещё работающего ASR;
- один PID недостаточен: ОС может переиспользовать его для другого процесса;
- Python coroutine pipeline восстановить безопасно нельзя, даже если её child
  process ещё жив;
- бесконечный event log и неограниченное чтение state создают локальный DoS.

Следствия:

- новая работа сначала получает durable reservation; stale runner/process не
  может обойти глобальный concurrency=1;
- process tree завершается только при совпадении PID и platform-specific start
  identity; несовпадение оставляет job управляемым `orphaned`;
- Windows использует `taskkill /T /F`, Linux/Unix — отдельную process session и
  сигналы process group;
- потерянный aggregate pipeline не продолжается автоматически: оператор
  отменяет живой orphan либо запускает Resume после terminal recovery;
- state file ограничен 4 МиБ, history — 20 stage и 20 pipeline records, events
  — 200; повреждённый/oversized snapshot останавливает API вместо silent reset;
- production runtime поддерживает один API worker. Межпроцессный lock защищает
  от двойного запуска, но routing статуса между несколькими workers не является
  распределённым job scheduler.

## 2026-07-12 - Python 3.12 Constraints Является Каноническим Dependency Lock

Решение: direct requirement files хранят bounded version ranges по назначению,
а `constraints-py312.txt` фиксирует единый reviewed resolver result для core,
offline transcription, optional diarization, documentation и development/audit
tools. CI, release validation и Docker устанавливают пакеты только под этим
constraints file.

Почему:

- unpinned fresh install менялся со временем и мог отличаться от проверенной
  локальной среды;
- `faster-whisper` утяжелял API/RAG-only install, хотя нужен только offline ASR;
- локальный `pip list` уже демонстрировал dependency drift;
- отсутствие advisory gate позволяло известной уязвимости попасть в release.

Следствия:

- `requirements.txt` содержит core, `requirements-transcription.txt` —
  faster-whisper, `requirements-dev.txt` — core + transcription + test/audit
  tools;
- diarization остаётся отдельным optional install profile, но его Windows/Linux
  wheels входят в общий lock и advisory gate;
- GigaAM остаётся отдельным profile вне reviewed locks; live использует
  отдельные platform-specific CPU locks и не входит в core constraints;
- scheduled и release workflows запускают `pip-audit --strict --no-deps` по
  pinned graph; текущий graph не имеет известных advisories;
- исключение допускается только с advisory ID, обоснованием, repository issue
  и ISO expiry; malformed/expired исключение ломает audit fail-closed;
- Dependabot раз в неделю предлагает обновления Python и GitHub Actions;
- lock фиксирует версии, но не hashes артефактов. Переход к hash-checking mode
  рассматривается отдельно, если появится distribution/high-assurance контур.

## 2026-07-12 - Ranking Rules Являются Набором Policies С Characterization Gate

Решение: BM25 intent adjustment, hybrid fusion и post-rerank используют общий
immutable `RankingProfile` и набор именованных typed policies. Перед изменением
правил фиксируется public synthetic characterization dataset. Каждый
boost/penalty сохраняет policy, label, multiplier и score before/after в
deterministic diagnostics trace.

Почему:

- монолитные условные блоки были главным источником скрытых ranking regressions;
- end-to-end ответ LLM не показывает, на каком этапе потерян релевантный source;
- customer terminology в generic Python code мешает публичной поставке и
  независимому использованию продукта;
- общий line coverage не гарантирует прохождение ranking branches.

Следствия:

- публичные/default marker groups хранятся в
  `configs/asu_june_bot/ranking_profile.yaml`, private additions — только в
  ignored `ranking_profile.local.yaml`;
- `ranking_profile.local.yaml` заменяет указанные list groups целиком, поэтому
  local group обязан сохранить нужные default markers;
- policy unit tests и characterization cases проверяются без Ollama, сети и LLM;
- `scripts/48_retrieval_coverage.py` отдельно контролирует ranking core и
  source-routing modules; `scripts/46_ci_verify.py` запускает gate после полного
  pytest;
- изменение коэффициентов, marker groups или порядка policies требует сначала
  обновить characterization evidence и объяснить behavior change в PR.

## 2026-07-12 - Runtime Inventory Является Канонической Картой Ownership

Решение: каждый Python package и каждый `.py`/`.ps1` в `scripts/` обязан быть
ровно один раз классифицирован в `configs/runtime_inventory.yaml` как
`current`, `compatibility` или `planned`. Empty scaffolds без committed contract
удаляются. Retained compatibility entrypoints остаются запускаемыми, но печатают
видимое migration warning с текущей заменой.

Почему:

- пустые `apps/*`, `templates/*` и placeholder packages создавали ложное
  впечатление о готовых продуктовых поверхностях;
- параллельные v1/v2 имена не позволяли покупателю или contributor определить
  поддерживаемый entrypoint;
- документация без machine check быстро расходится с деревом файлов;
- fallback `small` в нескольких retained ASR paths противоречил каноническому
  product profile `large-v3-turbo`.

Следствия:

- новый script/package не пройдёт тесты, пока не получит ownership status;
- current public CLI проходит реальный `--help` smoke без сети/model calls;
- `asu_june_bot.core` и `asu_june_bot.llm` явно остаются compatibility shims;
- v1 scripts не удаляются внезапно, existing automation может временно скрыть
  warning через `MEETINGAGENT_SUPPRESS_LEGACY_WARNING=1`;
- `DEFAULT_FASTER_WHISPER_MODEL` является единственным code default для offline
  faster-whisper, а `small` разрешён только как явный draft/dev выбор;
- scaffold directory возвращается только вместе с кодом, тестами, ownership и
  документацией.

## 2026-07-12 - Product UI Использует Versioned Assets И Restrictive CSP

Решение: `/`, `/ui`, `/MeetingAgent` и meeting Workspace отдают только
package-data HTML templates и внешние CSS/JavaScript из `/assets/v1/`. Product
pages получают restrictive Content-Security-Policy: scripts/styles/connect
разрешены только с `self`, inline script/style и `eval` не разрешены, framing и
object embedding запрещены. Dynamic runtime data строится через DOM/text APIs.

Почему:

- monolithic Python string templates смешивали routing, layout и behavior и
  делали review почти невозможным;
- inline handlers/styles не позволяли включить CSP без `unsafe-inline`;
- строковые unit tests не исполняли JavaScript и уже пропустили реальный UX-баг
  speaker-mapping status;
- wheel install обязан содержать UI так же, как editable Git checkout.

Следствия:

- `pyproject.toml` явно включает templates/assets в wheel package data;
- `/assets/v1/*` имеет годовой immutable cache. После изменения содержимого
  public asset URL/version необходимо поднять, а templates переключить на
  новый path; изменять закэшированный v1 после release нельзя;
- CSRF остаётся в памяти страницы, browser auth — в HttpOnly cookie; Web Storage
  для credentials, tokens и ответов запрещён тестами;
- `requirements-browser.txt` и отдельный CI job устанавливают Chromium и
  запускают browser smoke без ASR, embeddings и LLM calls;
- Swagger `/docs` не получает product-only CSP, пока не будет переведён на
  self-hosted assets отдельной задачей.

## 2026-07-13 - Meeting Embedding Cache Остаётся JSONL, Но Пишется Как Atomic Store

Решение: `data/meeting_embeddings_cache.jsonl` сохраняет совместимый JSONL
контракт, но больше не дополняется plain append. First-fill и rebuild выполняют
read/deduplicate/write transaction под общим advisory lock для threads и local
processes; новый snapshot создаётся во временном файле, синхронизируется через
`fsync` и публикуется `os.replace`.

Почему:

- параллельные первые Q&A-запросы могли повторно считать одни chunk embeddings
  и записывать дубли или перемешанные JSONL bytes;
- локальный CPU-first продукт уже использует `concurrency=1` для тяжёлых
  стадий, поэтому сериализация только первого cache fill приемлема;
- SQLite/новая vector DB для одного append-only cache увеличила бы packaging и
  migration surface без продуктовой пользы;
- lexical fallback обязан работать даже при lock timeout, повреждённом cache
  или недоступной файловой системе.

Следствия:

- identity остаётся `meeting_id + chunk_id + text_sha256 + embedding_model`;
- lock удерживается во время вычисления отсутствующих chunk embeddings, поэтому
  конкурентный процесс после ожидания повторно читает cache и не делает ту же
  работу;
- malformed/truncated/invalid и duplicate rows безопасно пропускаются при
  чтении и удаляются при следующей atomic записи;
- vector с размерностью, отличной от текущего query embedding, считается
  повреждённым и переэмбеддится, а не участвует в усечённом `zip` cosine;
- `scripts/49_rebuild_meeting_vector_cache.py --dry-run` проверяет cache, а
  запуск без `--dry-run` детерминированно compact/rebuild-ит его;
- query embedding не кэшируется, а ошибка cache/backend возвращает `None` в
  retriever и сохраняет штатный lexical retrieval path.

## 2026-07-13 - Public Anonymization Metadata Не Содержит Original-Value Hashes

Решение: публичные anonymized JSONL/report сохраняют только placeholders,
категории и counts. Исходные значения и их SHA-256 разрешены только в явно
запрошенном `*.private.json`. Поля speaker/source работают fail-closed:
сохраняются только allowlisted технические labels `SPEAKER_XX`,
`SPEAKER_UNKNOWN`, `MIC`, `SYS`, `MIX`; любое другое непустое значение
принудительно заменяется placeholder независимо от эвристик распознавания PII.

Почему:

- unsalted SHA-256 имени, email или короткого внутреннего термина допускает
  dictionary attack и не является public-safe anonymization;
- одиночные имена и произвольные source labels могут не совпасть с regex и
  остаться в структурных полях даже при очищенном тексте;
- стабильные технические labels нужны downstream chunking, citations и speaker
  mapping, поэтому полное удаление этих полей сломало бы контракт.

Следствия:

- public report нельзя использовать для восстановления или проверки исходного
  значения; локальная сверка требует `--write-private-map`;
- новые speaker/source-подобные поля должны быть добавлены в fail-closed
  metadata policy и покрыты синтетическим regression test;
- anonymization остаётся эвристической для свободного текста и требует ручной
  проверки перед публикацией.

## 2026-07-13 - Live Source Preflight Разделяет Device И Backend Readiness

Решение: live preflight не открывает audio stream и отдельно сообщает
`device_available`, `capture_supported` и итоговый `available`. MIC может быть
готов к запуску текущим Vosk backend. Windows WASAPI output device считается
только SYS loopback candidate; пока реальный loopback/resampling не реализован,
SYS и MIX возвращают blocked reason и не запускают microphone fallback.

Почему:

- наличие output device не доказывает, что PortAudio backend умеет захватить
  его как loopback source;
- прежний draft мог принять наличие MIC за доступность MIX, затем записать MIC
  и сохранить неверный source label;
- preflight нужен для automation/UI и должен отвечать на вопрос «можно ли
  запустить сейчас», не только «видно ли похожее устройство»;
- `--input-wav` не использует hardware capture и остаётся безопасным
  детерминированным smoke-path для любого source label.

Следствия:

- `--preflight-source` возвращает exit code `0` для runnable source и `2` для
  blocked source;
- inventory может показывать loopback candidates, не объявляя feature готовой;
- real SYS/MIX capture, streaming VAD, session API/UI и offline refinement
  реализуются отдельными задачами поверх стабильного контракта.

## 2026-07-13 - Windows SYS Использует PyAudioWPatch И Stateful SoXR

Решение: live-источник `SYS` на Windows захватывается через virtual WASAPI
loopback input из PyAudioWPatch. Native signed 16-bit PCM читается с реальными
channel count/sample rate устройства и stateful-конвертером SoXR HQ приводится
к canonical mono 16 kHz PCM перед передачей в Vosk.

Почему:

- high-level API `sounddevice` не предоставляет надёжный portable loopback
  stream, хотя видит Windows output devices;
- PyAudioWPatch предоставляет отдельные WASAPI loopback input devices и не
  требует маскировать системный звук под microphone capture;
- системные устройства обычно работают в stereo 44.1/48 kHz, а Vosk-контракт
  MeetingAgent использует mono 16 kHz;
- stateful resampling сохраняет непрерывность между capture blocks и стабильную
  шкалу времени;
- выбранный device index является source-specific и не объединяется с индексами
  `sounddevice` в единое пространство.

Следствия:

- `requirements-live.txt` ставит PyAudioWPatch только на Windows, а SoXR остаётся
  optional live dependency на всех платформах;
- preflight не открывает stream, а runtime повторно проверяет, что выбранный
  device действительно является loopback input;
- отчёт хранит только технические числовые метрики capture/conversion без имени
  устройства и абсолютных локальных путей;
- аппаратный `MIX` остаётся fail-closed до отдельной реализации синхронного
  захвата и смешивания MIC+SYS.

## 2026-07-13 - MIC Backpressure Сохраняет Новые Блоки И Wall-Clock

Решение: callback микрофона пишет `TimedAudioBlock` с абсолютными frame offsets
в ограниченную очередь. Callback использует только non-blocking операции. При
переполнении удаляется самый старый ожидающий блок, а новый сохраняется. Consumer
восстанавливает пропущенный интервал нулевым PCM до обработки следующего блока.

Почему:

- неограниченная очередь позволяет памяти расти, если Vosk/Silero медленнее
  PortAudio callback;
- блокировка callback вызывает новые потери на стороне аудиодрайвера;
- сохранение самых новых блоков ограничивает live latency;
- простое удаление PCM сжало бы временную шкалу, поэтому пропущенные frames
  должны оставаться частью canonical stream как тишина.

Следствия:

- ёмкость задаётся `--mic-queue-max-blocks` (32 блока по умолчанию, 1..1024);
- transcript timestamps после overflow остаются привязаны к capture wall-clock;
- report содержит capacity/peak/overflow/drop/gap metrics без device names и
  локальных путей, а потеря аудио поднимает warning `mic_audio_dropped`;
- качество текста на потерянном интервале восстановить нельзя: метрики и warning
  делают деградацию явной для UI/оператора.

## 2026-07-13 - Live Runtime Имеет Отдельные CPU Locks По Платформам

Решение: optional live runtime фиксируется в
`constraints-live-py312-windows.txt` и `constraints-live-py312-linux.txt`.
Оба файла строятся из `requirements-live-lock-py312.in` под Python 3.12,
наследуют shared pins из core constraints и используют официальный PyTorch CPU
index. Core `constraints-py312.txt`, base install и Docker image live packages
не содержат.

Почему:

- Windows resolver не видит Linux-only зависимости PyPI Torch, поэтому единый
  platform-generated lock не является точным для обеих ОС;
- обычный PyPI Torch на Linux тянет CUDA graph, хотя MeetingAgent live является
  local CPU workload;
- PyAudioWPatch нужен только Windows WASAPI loopback и не должен попадать в
  Linux lock;
- constraints отделяют воспроизводимость optional runtime от его установки по
  умолчанию.

Следствия:

- Windows install использует core constraints + Windows live constraints;
  Linux install - core constraints + Linux live constraints;
- оба lock-файла фиксируют `torch`/`torchaudio` CPU builds и не содержат CUDA;
- scheduled dependency audit запускает отдельные core, live-linux и
  live-windows jobs, поэтому platform marker PyAudioWPatch проверяется на
  Windows;
- для advisory lookup только reviewed `torch`/`torchaudio` pins с суффиксом
  `+cpu` проецируются на ту же публичную базовую версию; любой другой local
  version pin отклоняется fail-closed;
- изменение direct live ranges требует пересборки обоих locks, clean install,
  `pip check`, import smoke и проверки загрузки Silero model;
- GigaAM остаётся отдельным несовместимым runtime profile и не смешивается с
  live environment.

## 2026-07-13 - Live Session API Использует Bounded Polling И Single-Owner State

Решение: lifecycle live-записи управляется отдельным аутентифицированным API.
Один background worker владеет одной парой meeting/source, stop передаётся в
Vosk через `threading.Event`, а клиент читает bounded partial/final/status events
по курсору `after`. Status и final events сохраняются в atomic JSON snapshot;
частые partial hypotheses остаются memory-only. State path удерживает
process-level owner lock на всё время жизни API.

Почему:

- запуск capture из HTTP request не должен удерживать request до конца встречи;
- polling даёт стабильный и тестируемый v1-контракт без преждевременного
  WebSocket transport;
- continuous whole-file rewrite на каждый partial создаёт лишний I/O и большой
  crash surface, тогда как final/status нужны для restart recovery;
- два API workers не могут безопасно владеть одним локальным PortAudio stream и
  in-memory event ring, поэтому второй owner должен завершать startup fail-closed;
- stop обязан пройти через штатный Vosk `FinalResult()`, а не убивать worker.

Следствия:

- browser start/stop требует RBAC и CSRF, machine bearer использует те же
  action permissions без cookie CSRF;
- незавершённые durable records после API restart детерминированно становятся
  `stale` и записывают path-free `api_restart` в meeting card;
- публичные ответы не содержат model path, host API, channel/rate diagnostics,
  raw device errors или абсолютные пути;
- event response явно сообщает `partial_events_durable=false` и потерю старого
  cursor через `truncated=true`;
- глобальный active-session budget равен двум по умолчанию: MIC+SYS разрешены,
  но число одновременно загруженных Vosk models ограничено;
- multi-worker API и WebSocket не поддерживаются этим контрактом; UI v1
  использует polling, а offline refinement остаётся отдельным этапом.

## 2026-07-13 - Live Offline Refinement Требует Source-Scoped WAV

Решение: реальный MIC/SYS capture одновременно с Vosk сохраняет полный
canonical PCM16 mono 16 kHz поток в `source/live_audio.<SOURCE>.wav`. Запись
идёт до Silero VAD, поэтому длительность WAV и wall-clock шкала live draft
совпадают, включая тишину и восстановленные gaps. Файл публикуется только через
temp + `fsync` + `os.replace`, регистрируется в `source.media_files` и остаётся
в `rag.no_index_artifacts`.

Почему:

- live segments являются текстовым черновиком и не могут быть входом для
  faster-whisper/GigaAM;
- live-only карточка без сохранённого аудио не допускает честный offline
  refinement;
- сохранение только speech frames после VAD сжимает исходное время и ломает
  сопоставление live/offline таймкодов;
- потоковая запись ограничивает память, а size/free-space guards не дают
  бесконтрольно заполнить локальный диск.

Следствия:

- MIC и SYS имеют отдельные WAV; автоматический MIX не создаётся;
- успешный backend обязан вернуть финализированный WAV, иначе live session
  завершается controlled failure и карточка не регистрирует media;
- `scripts/22_transcribe_meeting.py --media-path` принимает только относительный
  файл, уже зарегистрированный в `source.media_files`;
- live WAV не удаляется при offline ASR и остаётся provenance для #208.

## 2026-07-13 - Live Refinement Переиспользует Canonical ASR И Durable JobRunner

Решение: завершённый MIC/SYS live draft уточняется только явным запуском
canonical `scripts/22_transcribe_meeting.py` через существующий durable
JobRunner. Для каждой source сохраняется состояние `draft/refining/final/failed`
и отдельный no-index отчёт `transcript/live/refinement.<SOURCE>.json`.

Почему:

- второй ASR-оркестратор создал бы отдельные правила retry/cancel/recovery;
- live text является черновиком, а входом offline ASR должен быть сохранённый
  source-scoped WAV;
- сравнение качества по одному числу недостоверно без размеченного эталона;
- UI должен отличать незапущенный draft, активную job, финальный transcript и
  управляемую ошибку после restart/crash.

Следствия:

- live artifacts сохраняются без изменений и остаются в `rag.no_index_artifacts`;
- canonical exports и `transcription_report.json` создаёт штатный offline ASR;
- comparison report содержит только engine/model/timing/count metadata и дельты,
  без transcript text, backend diagnostics и абсолютных путей;
- `resume` переиспользует partial canonical segments только при совпадении
  SHA-256; stale GigaAM workdir для другого input не принимается;
- повторный final-run требует explicit `force`, а повторная live-запись
  инвалидирует прежний source-specific refinement report/state.

## 2026-07-13 - Live И Offline Work Используют Общий Межпроцессный Арбитр

Решение: live capture и offline stage/pipeline для одной встречи резервируются
через общий advisory lock. Под lock читается durable-state противоположного
контура и сразу выполняется reservation в собственном существующем store.
Отдельный persistent owner-registry не создаётся.

Почему:

- UI-блокировки не защищают bearer clients и параллельные HTTP requests;
- независимые check-then-start проверки оставляют race между двумя API;
- третий owner-state потребовал бы отдельного recovery и мог бы зависнуть после
  crash;
- существующие JobStore и LiveSessionStore уже атомарны и умеют очищать
  terminal/stale state.

Следствия:

- для одной meeting card ровно один из конкурирующих live/offline запусков
  получает reservation; другой получает bounded machine-readable `409`;
- коды конфликтов: `live_session_active` и `offline_job_active`;
- MIC+SYS разрешены одновременно в пределах `live.active_sessions_max`;
- работа разных meetings не блокируется этим арбитром;
- readiness и preflight отражают server-side blocked reason;
- advisory lock снимается ОС при завершении процесса, а owner-state остаётся
  только в существующих recoverable stores.

## 2026-07-13 - Live-Встреча Создаётся Отдельной Карточкой Без Fake Media

Решение: browser/API создаёт live-only карточку через `POST /meetings/live`.
Выделение collision-safe `meeting_id` и публикация готовой папки выполняются
под тем же межпроцессным ingest lock, что и upload. Карточка получает
`source.kind=live_session`, язык и MIC/SYS source tracks, но не получает
`media_files`, artifacts или index rows до появления реального результата.

Почему:

- live capture должен начинаться до существования записанного файла;
- пустой или выдуманный media entry ломает provenance и offline refinement;
- одновременные browser requests не должны перезаписывать встречу с тем же
  title/date;
- Workspace и readiness уже умеют работать с карточкой без offline media.

Следствия:

- editor создаёт карточку с `meetings.upload` и CSRF; viewer получает 403;
- карточка собирается в hidden staging directory и публикуется одним rename;
- list/detail показывают `source_kind=live_session` и язык без локальных путей;
- реальный WAV регистрируется только после успешной MIC/SYS live-сессии;
- offline extract/transcribe остаются blocked до появления настоящего source.
