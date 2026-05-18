# Query Feedback Loop — Project Knowledge Bot

Обновлено: 2026-05-18.

## 1. Назначение

Query Feedback Loop — контур накопления обратной связи по реальным запросам пользователей и превращения этой обратной связи в управляемый eval dataset.

Цель: улучшать Project Knowledge Bot доказательно, через regression/eval, а не через ручные догадки.

Важно: на текущем этапе это не fine-tuning LLM и не обучение весов модели. Это управляемое накопление датасета, улучшение guard/retrieval/context/prompt и проверка качества через eval.

## 2. Что считается обучением в текущем MVP

В рамках текущего MVP под обучением понимается:

```text
реальный вопрос пользователя
  -> ответ бота
  -> sources/warnings/diagnostics
  -> ручная оценка качества
  -> классификация ошибки
  -> утвержденный eval case
  -> исправление guard/retrieval/context/prompt/corpus
  -> regression/eval повторная проверка
```

Не считается обучением:

```text
fine-tuning qwen/mistral
DSPy optimization
LLM-as-judge
NLI validator
автоматическое исправление корпуса без review
автоматическое добавление всех плохих ответов в base eval
```

## 3. Текущая база, на которую опирается loop

Уже реализовано:

```text
ChatRunsLogger
chat_runs.jsonl
warnings.semantic
manual_label/manual_issue в observability-контуре
EvalRunner
eval/cases/base.jsonl
eval/golden_answers/*.md
scripts/asu_june_bot_chat_eval.py
ProjectGuard regression cases
QH gate
```

Feedback loop должен быть надстройкой над существующими QH-1..QH-5, а не заменой текущей архитектуры.

## 4. Целевая схема

```text
User question
  -> /chat
  -> ChatResponse
      -> answer
      -> sources
      -> diagnostics
      -> warnings.semantic
      -> request_id
  -> chat_runs.jsonl
  -> UI/Telegram feedback
  -> feedback_events.jsonl
  -> feedback export
  -> eval/cases/feedback_candidates.jsonl
  -> analyst review
  -> eval/cases/feedback.jsonl или base.jsonl
  -> fix
  -> regression/eval
```

## 5. Минимальная модель feedback event

```json
{
  "feedback_id": "uuid",
  "request_id": "uuid from ChatResponse",
  "timestamp": "2026-05-18T00:00:00Z",
  "channel": "ui|telegram|cli|api",
  "query": "статус ПМИ",
  "status": "answered",
  "rating": "good|bad|unclear",
  "issue_type": "wrong_sources|bad_answer|false_refuse|false_allow|should_clarify|should_no_answer|hallucination|format_error|too_slow|ui_error|telegram_error",
  "comment": "Ответ ушел в статус замечания, а не в статус документа ПМИ.",
  "expected_behavior": "Уточнить, какой статус имеется в виду.",
  "expected_sources": [],
  "reviewer": "manual"
}
```

## 6. Типы ошибок

```text
false_refuse        бот отказался, хотя вопрос проектный
false_allow         бот ответил на внепроектный вопрос
wrong_sources       источники нерелевантны
weak_sources        источники слабые, но ответ уверенный
bad_answer          ответ формально есть, но смысл неверный
should_no_answer    должен был сказать, что данных недостаточно
should_clarify      должен был уточнить вопрос
hallucination       утверждение не подтверждено источниками
format_error        нарушен формат ответа
too_slow            неприемлемая задержка ответа
ui_error            проблема Web UI
telegram_error      проблема Telegram adapter
```

## 7. Пример feedback case

Фактический пример:

```text
query = статус ПМИ
status = answered
issue = wrong_intent / should_clarify
```

Проблема: короткий запрос неоднозначен. Система может интерпретировать его как статус замечаний, статус сценариев ПМИ, статус документа ПМИ или статус прохождения испытаний.

Ожидаемое поведение:

```text
status = clarify
answer содержит уточнение:
- статус документа ПМИ;
- статус сценариев ПМИ;
- статус прохождения испытаний;
- статус замечаний из ПМИ.
```

Кандидат eval case:

```json
{
  "id": "FB-STATUS-PMI-001",
  "query": "статус ПМИ",
  "expected_status": "clarify",
  "expected_answer_contains": ["статус документа", "статус сценариев", "статус испытаний", "статус замечаний"],
  "source": "feedback",
  "linked_issue_type": "should_clarify"
}
```

## 8. Правила превращения feedback в eval

Нельзя автоматически переносить весь feedback в `base.jsonl`.

Порядок:

```text
1. Собрать feedback_events.jsonl.
2. Отобрать rating=bad и rating=unclear.
3. Сгруппировать по issue_type.
4. Сформировать feedback_candidates.jsonl.
5. Аналитик вручную проверяет кандидаты.
6. Утвержденные кейсы переносятся в feedback.jsonl или base.jsonl.
7. После исправления запускается eval.
```

Критерии включения в base:

```text
часто повторяется
бизнес-критично
ловит regression
не зависит от случайного wording LLM
имеет понятный expected_status/expected_behavior
```

## 9. Минимальная реализация после QH-5

Commit 1:

```text
src/asu_june_bot/feedback/models.py
src/asu_june_bot/feedback/store.py
```

Commit 2:

```text
POST /feedback
```

Commit 3:

```text
Web UI buttons: good / bad / wrong_sources / should_clarify
```

Commit 4:

```text
Telegram commands: /good, /bad
```

Commit 5:

```text
scripts/asu_june_bot_feedback_export.py
```

Commit 6:

```text
eval/cases/feedback_candidates.jsonl
eval/cases/feedback.jsonl
```

## 10. Где хранить данные

Runtime feedback:

```text
data/asu_june_bot/feedback_events.jsonl
```

Кандидаты:

```text
eval/cases/feedback_candidates.jsonl
```

Утвержденные regression cases:

```text
eval/cases/feedback.jsonl
eval/cases/base.jsonl
```

Не коммитить runtime feedback без очистки, если в нем есть чувствительные данные.

## 11. Что исправляет feedback loop

Feedback loop помогает находить:

```text
короткие неоднозначные запросы
false_refuse guard
false_allow guard
нерелевантные источники
слабые primary sources
ошибки parent expansion
галлюцинации при формально корректных citations
медленные запросы
ошибки UI/Telegram
```

## 12. Что feedback loop не решает сам по себе

```text
не доказывает фактическую истинность ответа
не заменяет ручную проверку источников
не обучает LLM веса
не исправляет corpus автоматически
не должен менять guard без regression cases
```

## 13. Запреты

```text
не делать fine-tuning до накопления стабильного датасета
не подключать LLM-as-judge/NLI до QH-6 dataset review
не делать автоматическое самообучение
не добавлять user feedback напрямую в prompt
не сохранять Telegram token или персональные данные в eval
не менять retrieval/guard без regression/eval
```

## 14. Статус

```text
STATUS = PLANNED_AFTER_QH5
```

Причина: QH-5 должен быть закрыт перед расширением runtime. До QH-5 можно обновлять документацию и готовить план, но не добавлять новые endpoints в демо-контур.
