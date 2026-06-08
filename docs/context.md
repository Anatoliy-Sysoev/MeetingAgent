# Текущий Контекст

Обновлено: 2026-06-08.

MeetingAgent публикуется как local-first OSS проект для обработки встреч, транскрибации, проектной памяти, RAG-поиска и генерации рабочих артефактов.

## Текущее Состояние

- Основной публичный README оформлен как OSS landing page.
- Русская версия README сохранена в `README.ru.md`.
- Добавлены MIT license, security policy, contributing guide, code of conduct, changelog, issue templates и PR template.
- Добавлены безопасные синтетические examples в `examples/`.
- Runtime-папки `data/`, `logs/`, `vector_db/`, `watched_folder/`, `meetings/` закрыты через `.gitignore`.
- Приватные eval-отчеты, runtime-датасеты и локальные документы подпроектов сняты с индекса Git и остаются только локально.
- Публичные ссылки на удаленные private docs заменены на `docs/project_knowledge_bot.md`.
- Версия FastAPI Project Knowledge Bot берется из package `__version__`.
- `scripts/README.md` разделяет current runtime и legacy baseline.

## Важные Файлы

- `README.md` - публичное описание и quickstart.
- `README.ru.md` - русская версия описания.
- `docs/decisions.md` - публичные архитектурные решения.
- `docs/todo.md` - публичный backlog.
- `docs/quality/README.md` - политика публикации quality/eval артефактов.
- `.gitignore` - защита runtime outputs, приватных корпусов и локальных отчетов.
- `.env.example` - пример переменных без секретов.

## Что Не Публикуется

- реальные проектные документы;
- реальные транскрипты и аудио/видео;
- локальные meeting cards с содержимым встреч;
- embeddings cache, индексы и vector databases;
- eval runtime reports и private review datasets;
- локальные `.env`, `config.yaml`, токены и machine-specific paths.

Локальные подробные рабочие заметки сохранены в ignored-папке `docs/private/` и не должны попадать в Git.

## Последнее Изменение

Добавлены public-safe quality артефакты для следующего NTK integration eval:

- `docs/quality/heldout_integration_ftt_questions.jsonl` содержит синтетический held-out набор для проверки protocol / message_format / message_size / auth_type / object_identification без публикации runtime outputs;
- `scripts/diagnostics/grade_anchor_audit.py` преобразует `audit_answer_gate.py` JSONL в pivot-ready review JSONL с `review_verdict` и `review_issue`;
- `scripts/diagnostics/pivot_manual_review.py` теперь строит сводки не только по `review_verdict`, но и по `review_issue`, чтобы следующий bucket выбирать по типу дефекта;
- Q040 live закрыт: deterministic FTT integration answer возвращает `HTTPS` по найденному source anchor без вызова LLM (`llm_called=false`, `pre_llm_deterministic_answer=true`, `ftt_integration_deterministic_answer=true`);
- локальные audit/manual/pivot outputs остаются в ignored `data/diagnostics/`.

Добавлен первый public-safe слой live-транскрибации:

- `src/meeting_agent/live_transcription/` содержит контракт `LiveSegment`/`LiveSessionReport`, exporters и optional Vosk backend;
- `src/meeting_agent/live_transcription/vad.py` добавляет optional Silero VAD speech-window detection для `--input-wav`;
- `scripts/33_live_transcribe_meeting.py` запускает live draft transcription для meeting card, поддерживает `--engine vosk`, `--source MIC|SYS|MIX`, `--input-wav`, `--vad none|silero` для детерминированного smoke и `--dry-run`;
- live outputs пишутся отдельно в source-scoped файлы `transcript/live/live_segments.<SOURCE>.jsonl`, `live_partials.<SOURCE>.jsonl`, `live_transcript.<SOURCE>.txt`, `live_subtitles.<SOURCE>.srt`, `live_subtitles.<SOURCE>.vtt`, `live_report.<SOURCE>.json`;
- MIC/SYS/MIX теперь могут сосуществовать в одной карточке без перетирания результатов друг друга;
- Ctrl+C внутри live backend считается graceful stop: накопленные segments/partials финализируются и записываются;
- live draft completion оставляет `processing_status=processing`, чтобы финальный offline ASR через `scripts/22_transcribe_meeting.py` мог стартовать без `--force`;
- microphone capture loop использует `audio_queue.get(timeout=0.5)`, а `live_report.<SOURCE>.json` получает `input_status_events` и `queue_timeouts` для диагностики overflow/dropout;
- known limitation для `--vad silero`: таймкоды не компрессируются, но finalized segment может получить хвостовой fallback span блока завершения фразы; smoke должен проверять попадание в speech window, а не равенство span с `--vad none`;
- live draft artifacts автоматически добавляются в `rag.no_index_artifacts`, чтобы не попасть в RAG до offline/final handoff;
- `configs/schemas/meeting.schema.json` теперь разрешает `live_*` artifact paths;
- optional зависимости Vosk, sounddevice и Silero VAD вынесены в `requirements-live.txt` и `pyproject.toml [project.optional-dependencies].live`;
- `README.md`, `docs/decisions.md`, `docs/operations/MEETING_PIPELINE.md`, `docs/meeting_agent_architecture.md` и `docs/product/PROJECT_STAGES_AND_FTT.md` обновлены: Vosk выбран первым live backend, T-one оставлен как будущий сравнительный эксперимент на реальных встречах, final transcript остается offline-проходом через `scripts/22_transcribe_meeting.py`.

Проверки live-слоя: `./.venv/Scripts/python.exe -m pytest tests/unit/test_live_transcription_contract.py tests/unit/test_transcription_contract.py -q` - 15 passed; `py_compile` для `scripts/22_transcribe_meeting.py`, `scripts/33_live_transcribe_meeting.py` и `compileall` для `src/meeting_agent/live_transcription` - ok.

Текущий внешний test gap после подтягивания `origin/main`: `./.venv/Scripts/python.exe -m pytest tests/asu_june_bot -q` падает 4 тестами в `tests/asu_june_bot/search/test_search_service.py`, потому что в ответе нет `diagnostics.search_service`. Это не связано с live-транскрибацией, но требует отдельного исправления search diagnostics contract.

Локальный meeting smoke проверил Docker-путь на реальной записи, но runtime-артефакты и идентификаторы встречи остаются только локально:

- исходное видео монтируется через `MEETINGAGENT_RECORDINGS_DIR`;
- `scripts/20_ingest_meeting.py` и `scripts/21_extract_audio.py` создают meeting card и `source/audio_16k_mono.wav`;
- `scripts/23_diarize_meeting.py` в контейнере прошел на `sherpa-onnx` и записывает `transcript/diarization.jsonl` + `transcript/diarization_report.json`;
- для качественного offline ASR используется `faster-whisper large-v3-turbo`, а `small` остается только для быстрых черновых smoke-проверок;
- внешний `large-v3-turbo` transcript импортирован через `scripts/22_transcribe_meeting.py --engine from-segments`;
- canonical transcript exports созданы: `segments.jsonl`, `transcript.json`, `transcript.txt`, `transcript.md`, `transcript.srt`, `transcript.vtt`, `transcription_report.json`;
- `scripts/24_merge_transcript_speakers.py` создал speaker transcript с `SPEAKER_XX`;
- `scripts/26_chunk_meeting.py` создал meeting chunks;
- `scripts/27_enrich_meeting_chunks.py` создал deterministic enrichment;
- `scripts/28_index_meeting_chunks.py` и `scripts/32_index_meeting_artifacts.py` экспортировали meeting chunks/artifacts в local runtime meeting index;
- `scripts/31_meeting_search.py` успешно нашел meeting chunks и structured action items по smoke-запросам.

Ограничение текущего прогона: `scripts/29_analyze_meeting.py --mode ollama-map-reduce --model qwen3.5:4b` ушел в fallback, потому что активный Ollama endpoint смотрел не в тот model store. Расследование подтвердило, что `qwen3.5:4b` не удалялась: модель лежит в `C:\ollama-models`, но запущенный `ollama serve` отдавал другой набор моделей. Для стабилизации добавлены `scripts/start_ollama_local.ps1` и `docs/operations/OLLAMA_LOCAL_RUNTIME.md`; canonical store для Windows - `C:\ollama-models`.

Контейнерный профиль для diarization добавлен как рабочий runtime-слой:

- `Dockerfile` поддерживает build arg `INSTALL_DIARIZATION=true`;
- `docker-compose.yml` содержит profile/service `diarization`;
- `requirements-diarization.txt` ставится только в optional image;
- `models/` игнорируется Git и используется для локальных ONNX/HuggingFace model caches;
- GigaAM по-прежнему не включается в основной Docker image.

Добавлен optional speaker diarization слой для MeetingAgent:

- `src/meeting_agent/diarization/` содержит контракт интервалов, нормализацию, maximum-overlap speaker assignment и `sherpa-onnx` backend;
- `scripts/23_diarize_meeting.py` пишет `transcript/diarization.jsonl` и `transcript/diarization_report.json`;
- `scripts/24_merge_transcript_speakers.py` теперь использует `diarization.jsonl`, если он есть, иначе сохраняет старый fallback `SPEAKER_UNKNOWN`;
- `configs/schemas/meeting.schema.json` поддерживает `artifacts.diarization` и `artifacts.diarization_report`;
- optional зависимости вынесены в `requirements-diarization.txt`, а ONNX-модели хранятся локально в ignored `models/`.

В `AGENTS.md` закреплены правила после cleanup публичного Git:

- что ведется в репозитории: код, public-safe docs, synthetic examples, safe config examples и тесты без приватных данных;
- что остается только локально: `.env`, `config.yaml`, runtime outputs, реальные документы/транскрипты, индексы, cache, private eval/manual-review и `docs/private/`;
- перед commit нужно проверять подозрительные пути через `git check-ignore -v` и не использовать `git add -f` для ignored файлов без отдельного решения.

Добавлен локальный диагностический runner для последовательного сравнения Ollama-моделей на пользовательском наборе вопросов:

- runner сохраняет исходный вопрос, фактический `run_query`, ответ, источники, статус и время ответа;
- результаты пишутся в ignored runtime-папки `data/diagnostics/` и `logs/`;
- JSONL/summary/manual-review outputs не публикуются в Git.

Добавлены публично безопасные диагностические утилиты для локальных quality runs:

- `scripts/diagnostics/check_index_coverage.py` проверяет, покрывает ли JSONL индекс ожидаемые gold anchors;
- `scripts/diagnostics/pivot_manual_review.py` строит status/verdict/issue pivots по локальному manual-review JSONL;
- приватные `gold.jsonl`, coverage reports и pivots остаются в ignored `data/diagnostics/`.

Добавлена runtime-семантика заголовков ФТТ Table 8 в `ContextBuilder`:

- карта заголовков хранится в public-safe `configs/asu_june_bot/table_header_maps.yaml`;
- строки таблицы с `Входит в объём проекта_3: Х` получают нормализованный факт `Этап 3 (ФТ3)` только в built context;
- persisted chunks, `chunk_id`, embeddings cache и numpy index не меняются;
- targeted retrieval/context check для вопросов по требованиям `1.1` и `1.3` подтверждает `Этап 3 (ФТ3)` без `Этап 1 (ФТ1)`.

Добавлен diagnostic-only аудит answer gate:

- `scripts/diagnostics/audit_answer_gate.py` проверяет наличие required anchors в corpus, built context и prompt после обрезки;
- локальная проверка `integration_ftt` показала: нужный anchor есть в corpus, но для проблемного вопроса не попадает в context/prompt;
- значит текущий дефект относится к required-anchor source selection, а не к validator и не к отсутствию документа в корпусе;
- JSONL/summary outputs остаются в ignored `data/diagnostics/`.

Добавлен required-anchor source selection для ФТТ-интеграций:

- `SearchService` определяет intent для вопросов `integration_ftt`: протокол, формат сообщения, размер сообщения, тип аутентификации, идентификация объектов;
- до rerank в raw candidates подмешивается или продвигается ФТТ chunk с нужным anchor (`https`, `JSON/XML`, `100Мб`, `Basic-аутентификация`, `тэг в заголовке вызова`);
- diagnostics stage: `integration_ftt_required_anchor_selection`;
- targeted проверка Q040-Q044 на локальном qwen3.5:4b: все 5 ответили, required anchors есть в corpus/context/prompt, `no_answer=0`, `validation_failed=0`;
- Q043 подтверждает `Basic-аутентификация` как ФТТ-источник без подмены Blitz/OIDC как общего типа аутентификации.

Добавлен deterministic answer layer для стабильных ФТТ-интеграционных параметров:

- `src/asu_june_bot/chat/ftt_integration_answer.py` формирует ответы по protocol, message format, message size, auth type и object identification только при наличии соответствующего source anchor в выбранных источниках;
- `ChatService` вызывает этот слой до LLM и как fallback при no-answer marker / validation failure;
- `PromptBuilder` сохраняет поле `document` в `ChatSource.path`, чтобы source-grounded builder корректно распознавал ФТТ-источник;
- targeted tests: `tests/asu_june_bot/chat/test_ftt_integration_answer.py` и связанные chat/guard tests прошли локально (`31 passed`);
- live Q040 после корректного restart API на `corpus_key=ntk` отвечает `HTTPS` без вызова LLM.

Штатная chat-модель переведена на `qwen3.5:4b`:

- обновлены runtime fallbacks для CLI/API/Telegram и локальный ignored `config.yaml`;
- обновлены public config examples, `.env.example`, quickstarts и UI model selector;
- для `qwen3.5:*` `OllamaOpenAIClient` использует native Ollama `/api/chat` с `think=false`, потому что OpenAI-compatible endpoint игнорирует `think=false`, а `/no_think` не отключает reasoning у текущей локальной модели;
- embeddings model не менялась: `bge-m3`.

Добавлена защита от обрезанных LLM-ответов:

- default `max_tokens` для Project Knowledge Bot API/UI поднят до `1400`;
- UI теперь отправляет `max_tokens=1400` вместо старого `900`;
- если LLM возвращает `finish_reason=length`, chat API возвращает статус `truncated`, сохраняет ответ и источники, но не считает результат `answered`;
- semantic warnings добавляют high-warning `truncated_answer` с сообщением, что ответ обрезан лимитом генерации;
- UI показывает отдельную warning-плашку: `Ответ обрезан лимитом генерации, нужно повторить с большим лимитом.`;
- eval checks теперь валят такие ответы через проверку `not_truncated`, чтобы `finish_reason=length` не проходил как `ok`.

Проверен live baseline Project Knowledge Bot на локальном NTK corpus:

- `/health` подтверждает `corpus_key=ntk` и пути `data/asu_june_bot_ntk/*`;
- локальный Ollama runtime был переведен на ASCII model store, потому что `bge-m3` не загружался из Unicode-пути профиля Windows;
- Q030/Q031 live отвечают `Этап 3 (ФТ3)` с `finish_reason=stop`;
- Q040 live отвечает `HTTPS` по source anchor без вызова LLM;
- Q041-Q044 live отвечают требуемыми ФТТ anchors с `finish_reason=stop`;
- локальный JSONL baseline сохранен в ignored `data/diagnostics/`.

Закрыт targeted guard bucket для project testing/documentation queries:

- добавлены project markers для `список сервисов` / `ролевая модель`;
- добавлены out-of-project markers для рисования и простых арифметических запросов;
- mixed project + drawing теперь отказывается до retrieval;
- targeted guard eval по project/out-of-scope/mixed кейсам: 19/19;
- `tests/asu_june_bot/test_project_guard_v2.py`: 13 passed.

Исправлен corpus alias для NTK:

- в `configs/asu_june_bot/corpus.yaml` добавлен явный key `ntk`;
- `ASU_JUNE_BOT_ACTIVE_CORPUS=ntk` теперь должен вести на `data/asu_june_bot_ntk/*`, а не fallback-иться на `default`;
- это критично для сопоставимости UI и eval: Q030/Q040-Q044 нужно проверять на том же corpus key, на котором работает живой бот;
- добавлен regression test на live config alias.

Ранее выполнен cleanup публичного дерева:

- ужесточены `.gitignore` правила для private/eval/runtime данных;
- приватные quality reports и docs подпроекта сняты с индекса через `git rm --cached`;
- публичные `docs/context.md`, `docs/todo.md`, `docs/decisions.md` заменены на безопасные версии;
- публичный README больше не ведет на локальные private setup документы.
- `src/meeting_agent/` явно описан как planned scaffold, кроме реализованного `transcription` слоя.

История Git пока не переписывалась. Если нужно убрать уже опубликованные приватные файлы из истории GitHub, нужен отдельный проход через `git filter-repo` или BFG с force-push.
