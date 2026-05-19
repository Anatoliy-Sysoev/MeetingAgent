# Roadmap Project Knowledge Bot

Обновлено: 2026-05-19.

## 1. Принцип roadmap

Развитие идёт от качества project-only контура, а не от выбора модели:

```text
источники -> extraction -> chunks -> index -> guarded search -> context -> chat -> observability/eval -> quality hardening -> release stabilization -> feedback dataset loop -> docker packaging -> UI hardening -> deployment
```

Любое изменение retrieval/context/LLM должно иметь проверку на baseline cases.

Docker-упаковка начинается после фактического прохождения QH-5. На 2026-05-19 QH-5 passed, поэтому Docker стал следующим инженерным этапом.

Feedback Dataset Loop начинается после QH-5 как QH-6. После закрытия QH-5 можно проектировать runtime `/feedback`, UI/Telegram feedback-команды и manual approval flow.

## 2. Сводный статус этапов

```text
Этап 0. Архитектурное отделение подпроекта          Закрыт
Этап 1. Corpus v2.1                                  Закрыт
Этап 2. Index/Search v2                              Закрыт
Этап 3. Search Quality v2.2                          Закрыт
Этап 4. ProjectGuard v2                              Закрыт
Этап 5. SearchService + API Search MVP               Закрыт
Этап 6. ChatService + CLI/API Chat MVP               Закрыт с ограничениями
Этап 7. Local Web UI + Telegram adapter              Закрыт local smoke
Этап 8. QH-1 Observability + Eval Baseline           Реализован
Этап 9. QH-2 Source Quality Filter                   Реализован и проверен
Этап 10. QH-3 Parent Expansion                       Реализован и проверен
Этап 11. QH-4 Semantic Warnings / Manual Labels      Реализован и проверен
Этап 12. QH-5 Release Stabilization                  PASSED
Этап 13. QH-6 Feedback Dataset Loop                  Следующий quality-трек
Этап 14. Docker Packaging                            Следующий delivery-трек
Этап 15. UI hardening / OpenWebUI adapter            Позже
Этап 16. GPU migration path                          Позже
Этап 17. Enterprise-hardening                        Позже
Этап 18. Выделение в отдельный репозиторий           После Docker и стабилизации документации
```

Главные документы статуса:

```text
docs/subprojects/asu-june-bot/QH_STATUS.md
docs/subprojects/asu-june-bot/QUERY_FEEDBACK_LOOP.md
```

## 3. Закрытые базовые этапы

### Этап 0. Архитектурное отделение подпроекта

Статус:

```text
Закрыт
```

Решение: `scripts/09_chat.py` считается legacy/prototype. Целевой runtime находится в `src/asu_june_bot/` и `scripts/asu_june_bot_*.py`.

### Этап 1. Corpus v2.1

Статус:

```text
Закрыт
```

Результаты:

```text
extract_text_v2
blocks.jsonl
DOCX/XLSX/PDF/PPTX/HTML/text parsing
exclude rules для system exports/temp files
source audit
```

### Этап 2. Index/Search v2

Статус:

```text
Закрыт
```

Результаты:

```text
chunks_v2 = 31302
indexed_chunks = 31285
embedding_model = bge-m3
numpy_index_v2
BM25
hybrid search
health_v2
```

### Этап 3. Search Quality v2.2

Статус:

```text
Закрыт
```

Результаты:

```text
QueryIntent
PostReranker
ContextBuilder
primary_sources
supporting_sources
excluded_sources
```

### Этап 4. ProjectGuard v2

Статус:

```text
Закрыт
```

Критерии:

```text
false_allow = 0
refused -> retrieval_called=false
clarify -> retrieval_called=false
mixed-scope -> refused
project + unknown tail -> refused
```

### Этап 5. SearchService + API Search MVP

Статус:

```text
Закрыт
```

Результаты:

```text
SearchService
GET /health
POST /search
API Search smoke report
```

### Этап 6. ChatService + CLI/API Chat MVP

Статус:

```text
Закрыт с ограничениями
```

Результаты:

```text
ChatService
PromptBuilder
LLMClient
OllamaOpenAIClient
AnswerValidator
ResponseFormatter
scripts/asu_june_bot_chat.py
POST /chat
API Chat smoke report
```

Ограничение:

```text
structural validation есть
semantic/factual validation не является hard-fail
```

Рабочая модель:

```text
qwen2.5:7b-instruct
```

## 4. Этап 7. Local Web UI + Telegram adapter

Статус:

```text
Закрыт local smoke
```

Результаты:

```text
GET /
GET /ui
src/asu_june_bot/api/routes_ui.py
src/asu_june_bot/telegram_bot.py
scripts/asu_june_bot_telegram.py
docs/subprojects/asu-june-bot/telegram.md
```

Ограничение ввода:

```text
MAX_QUERY_CHARS = 2000
```

## 5. Этап 8. QH-1 Observability + Eval Baseline

Статус:

```text
Реализован
```

Результаты:

```text
ChatRunsLogger
chat_runs.jsonl
eval/cases/base.jsonl
scripts/asu_june_bot_chat_eval.py
eval report JSON/Markdown
golden answer placeholders
```

Первый baseline:

```text
total = 13
passed = 6
failed = 7
pass_rate = 46.2%
```

Интерпретация: baseline выявил смесь ложных eval failures, guard gap и реальных retrieval/context gaps. Часть ложных падений и guard gap уже исправлены.

## 6. Этап 9. QH-2 Source Quality Filter

Статус:

```text
Реализован и проверен
```

Цель: снизить риск, что короткие UML/heading/caption chunks становятся primary evidence.

Реализация:

```text
src/asu_june_bot/retrieval/source_quality.py
src/asu_june_bot/retrieval/context_builder.py
```

Принцип:

```text
не удалять chunks из индекса
не менять raw retrieval
оценивать качество источника в ContextBuilder
слабые источники демотировать из primary в supporting/excluded
фиксировать reasons в diagnostics
```

Тесты:

```text
tests/asu_june_bot/retrieval/test_source_quality.py
tests/asu_june_bot/retrieval/test_context_builder_qh.py
```

## 7. Этап 10. QH-3 Parent Expansion

Статус:

```text
Реализован и проверен
```

Цель: расширять слабый, но потенциально полезный источник соседним/родительским контекстом.

Реализация:

```text
src/asu_june_bot/retrieval/parent_expansion.py
src/asu_june_bot/retrieval/context_builder.py
```

Ограничения:

```text
только для weak source
только если соседний/родительский фрагмент уже есть среди кандидатов
строгий max_parent_chars
без обращения к индексу и без пересборки corpus
```

Тесты:

```text
tests/asu_june_bot/retrieval/test_parent_expansion.py
tests/asu_june_bot/retrieval/test_context_builder_qh.py
```

## 8. Этап 11. QH-4 Semantic Warnings / Manual Labels

Статус:

```text
Реализован и проверен
```

Цель: добавить warning-only слой качества без hard-fail semantic validation.

Реализация:

```text
src/asu_june_bot/chat/semantic_warnings.py
src/asu_june_bot/chat/service.py
src/asu_june_bot/observability/chat_runs.py
```

Warning codes:

```text
weak_sources_present
weak_primary_fallback
parent_expansion_applied
low_source_count
low_citation_coverage
structural_validation_errors
```

Важно: QH-4 не является factual validator. Он только помечает риск.

## 9. Этап 12. QH-5 Release Stabilization

Статус:

```text
PASSED
```

Реализация gate:

```text
src/asu_june_bot/qh/release_gate.py
scripts/asu_june_bot_qh_gate.py
```

Почему `passed`:

```text
локальные тесты, API/UI/Telegram smoke и eval after_qh выполнены на рабочем ПК с data/asu_june_bot и Ollama
final gate выполнен с --local-validation-done --baseline-compared
```

Проверка:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_qh_gate.py --json
```

Финальный результат:

```text
status = passed
pending = []
```

## 10. Этап 13. QH-6 Feedback Dataset Loop

Статус:

```text
Запланирован после QH-5
```

Назначение:

```text
накапливать реальные запросы и ручную обратную связь
превращать плохие ответы в feedback candidates
переносить только проверенные cases в eval/regression
улучшать guard/retrieval/context/prompt через baseline comparison
```

Документ:

```text
docs/subprojects/asu-june-bot/QUERY_FEEDBACK_LOOP.md
```

Минимальный состав будущей реализации:

```text
src/asu_june_bot/feedback/models.py
src/asu_june_bot/feedback/store.py
POST /feedback
data/asu_june_bot/feedback_events.jsonl
scripts/asu_june_bot_feedback_export.py
eval/cases/feedback_candidates.jsonl
eval/cases/feedback.jsonl
UI feedback buttons
Telegram /good и /bad
```

Ограничение:

```text
не делать fine-tuning
не делать автоматическое самообучение
не добавлять candidates в base без ручного review
```

## 11. Этап 14. Docker Packaging

Статус:

```text
Запланирован после фактического QH-5 passed
```

Минимальный состав:

```text
Dockerfile
.dockerignore
docker-compose.yml
.env.example
config.docker.example.yaml
docs/deployment/docker.md
bot-api service
host volumes для data/eval/config
```

Первый docker-compose:

```text
Ollama на Windows host
bot-api в Docker
LLM endpoint через host.docker.internal
```

## 12. Поздние этапы

```text
UI hardening / OpenWebUI adapter
GPU migration path
Enterprise-hardening
Выделение в отдельный репозиторий
```

## 13. Не делать сейчас

```text
не считать QH-5 passed без локального smoke/eval
не начинать Docker до фактического QH-5 passed
не расширять runtime feedback endpoints до QH-5 passed
не удалять weak chunks из индекса
не делать parent expansion без лимита
не превращать semantic warnings в hard-fail
не подключать DSPy в runtime
не делать LLM-as-judge/NLI до накопления dataset
не делать fine-tuning
не развивать scripts/09_chat.py как основной runtime
не смешивать старый MeetingAgent RAG v1 и bot v2.1
```
