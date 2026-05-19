# Завтрашний протокол проверки Project Knowledge Bot

Обновлено: 2026-05-18.

## 0. Назначение документа

Этот документ — пошаговый протокол на завтра.

Цель:

```text
подтянуть изменения из Git
проверить окружение
прогнать тесты
запустить API
проверить Web UI
проверить Telegram adapter
прогнать eval after_qh
понять, можно ли закрывать QH-5
```

Работать строго сверху вниз. Не перескакивать через шаги.

В каждый блок `Фактический результат` вставлять реальный вывод команды или краткое резюме.

## 0.1 Фактический прогон 2026-05-18

Статус:

```text
Частично выполнено.
QH-5 пока нельзя закрывать как PASSED.
```

Что выполнено:

```text
git branch: main
git pull: Already up to date
ollama list: bge-m3 и qwen2.5:7b-instruct есть
health_v2: status=ok, vector_ready=true, bm25_ready=true
regression tests: 97 passed, FAILED/ERROR нет
QH gate до smoke: pending_local_validation, pending QH-5A/QH-5B
API smoke: /health ok, /search project ok, /search weather refused
/chat project: answered, sources_count=5, llm_called=true, semantic warnings есть
/chat weather: refused, llm_called=false
/chat mixed: refused, llm_called=false
Web UI HTTP smoke: /ui status_code=200, основные элементы страницы есть
chat_runs.jsonl: пишется
after_qh eval: 7/13, 53.8%
baseline comparison: было 6/13, 46.2%, стало +1 passed
```

Что не выполнено:

```text
Telegram smoke не выполнен: нет ASU_JUNE_BOT_TELEGRAM_TOKEN и ASU_JUNE_BOT_ALLOWED_CHAT_IDS.
Финальный QH gate с --local-validation-done --baseline-compared не запускался намеренно.
```

Отчёт:

```text
docs/subprojects/asu-june-bot/smoke_report_qh_release.md
```

Итог:

```text
Бот близок к QH-5, но QH-5 остаётся PENDING_LOCAL_VALIDATION до Telegram smoke и финального gate.
```

## 1. Правила работы

### 1.1 Что не делать

```text
не запускать git reset --hard
не запускать git clean -fd
не удалять data/asu_june_bot
не запускать --reset без явной причины
не пересчитывать embeddings, если health показывает vector_ready=true
не менять модель embeddings bge-m3
не коммитить Telegram token
не начинать Docker до QH-5 passed
не чинить всё подряд перед сдачей
```

### 1.2 Что отправлять мне напрямую

Отправлять мне сразу, без самостоятельного исправления:

```text
git pull не проходит
git status показывает непонятные изменения
health status != ok
vector_ready = false
bm25_ready = false
ollama_available = false
embedding_model_installed = false
любой pytest падает
API не стартует
/health не отвечает
/chat возвращает 500 или llm_error
UI не открывается
Telegram adapter падает с traceback
QH gate показывает failed
после after_qh резко ухудшился eval
```

### 1.3 Как присылать ошибку

Копировать:

```text
1. Команду, которую запускал.
2. Полный вывод ошибки.
3. 20 строк выше ошибки, если ошибка длинная.
4. Вывод git status --short.
5. Если связано с API — скрин или текст из PowerShell, где запущен сервер.
```

## 2. Подготовка PowerShell

### 2.1 Открыть проект

Команда:

```powershell
cd C:\Users\Сотрудник\Desktop\AI\MeetingAgent
(Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned) ; (& .\.venv\Scripts\Activate.ps1)
```

Ожидаемо:

```text
в строке PowerShell появился префикс (.venv)
```

Фактический результат:

```text
[ВСТАВИТЬ РЕЗУЛЬТАТ]
```

Критично — отправить мне:

```text
папка не найдена
.venv не активируется
PowerShell пишет, что Activate.ps1 не найден
```

## 3. Git restore point

### 3.1 Проверить ветку

Команда:

```powershell
git branch --show-current
```

Ожидаемо:

```text
main
```

Если ветка другая:

```powershell
git switch main
```

Фактический результат:

```text
[ВСТАВИТЬ РЕЗУЛЬТАТ]
```

Критично — отправить мне:

```text
git checkout не проходит
Git пишет про local changes или conflicts
```

### 3.2 Подтянуть изменения

Команда:

```powershell
git pull --ff-only origin main
```

Ожидаемо:

```text
Fast-forward
```

или:

```text
Already up to date.
```

Фактический результат:

```text
From https://github.com/Anatoliy-Sysoev/MeetingAgent
 * branch            main -> FETCH_HEAD
Already up to date.
```

Критично — отправить мне:

```text
fatal
conflict
not possible to fast-forward
merge required
```

### 3.3 Проверить чистоту рабочей папки

Команда:

```powershell
git status --short
```

Ожидаемо:

```text
пустой вывод
```

Фактический результат:

```text
?? eval/reports/
```

Критично — отправить мне:

```text
есть изменения в src/
есть изменения в docs/
есть untracked .env/token/config files
есть conflict markers
```

### 3.4 Зафиксировать последние коммиты

Команда:

```powershell
git log --oneline -10
```

Фактический результат:

```text
[ВСТАВИТЬ РЕЗУЛЬТАТ]
```

## 4. Проверка моделей и Ollama

### 4.1 Проверить список моделей

Команда:

```powershell
ollama list
```

Ожидаемо есть:

```text
bge-m3
qwen2.5:7b-instruct
```

Фактический результат:

```text
[ВСТАВИТЬ РЕЗУЛЬТАТ]
```

Критично — отправить мне:

```text
ollama не найден
нет bge-m3
нет qwen2.5:7b-instruct
команда зависает
```

### 4.2 Если Ollama не запущен

Команда в отдельном PowerShell:

```powershell
ollama serve
```

Потом повторить:

```powershell
ollama list
```

Фактический результат:

```text
[ВСТАВИТЬ РЕЗУЛЬТАТ]
```

## 5. Health v2

### 5.1 Запустить health

Команда:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_health_v2.py --json
```

Ожидаемо:

```text
status = ok
bm25_ready = true
vector_ready = true
ollama_available = true
embedding_model_installed = true
```

Фактический результат:

```text
[ВСТАВИТЬ ПОЛНЫЙ JSON ИЛИ КЛЮЧЕВЫЕ СТРОКИ]
```

Критично — отправить мне:

```text
status != ok
vector_ready = false
bm25_ready = false
ollama_available = false
embedding_model_installed = false
ошибка чтения chunks/index
ошибка импорта Python-модулей
```

Решение самому не делать, если `data/asu_june_bot` отсутствует или индекс битый. Сначала отправить мне вывод.

## 6. Быстрый unit/regression pack

Запускать по одному блоку. Если блок упал — остановиться и отправить мне ошибку.

### 6.1 ChatService

Команда:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\chat\test_chat_service.py -q
```

Ожидаемо:

```text
7 passed
```

Фактический результат:

```text
[ВСТАВИТЬ РЕЗУЛЬТАТ]
```

Критично — отправить мне:

```text
FAILED
ERROR
ImportError
ModuleNotFoundError
```

### 6.2 Semantic warnings

Команда:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\chat\test_semantic_warnings.py -q
```

Ожидаемо:

```text
3 passed
```

Фактический результат:

```text
[ВСТАВИТЬ РЕЗУЛЬТАТ]
```

### 6.3 API tests

Команды:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\api\test_health.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\api\test_search_smoke.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\api\test_chat_smoke.py -q
```

Ожидаемо:

```text
test_health.py: 1 passed
test_search_smoke.py: 4 passed
test_chat_smoke.py: 7 passed
```

Фактический результат:

```text
[ВСТАВИТЬ РЕЗУЛЬТАТ]
```

Критично — отправить мне:

```text
любой FAILED
FastAPI import error
pydantic validation error в тестах
```

### 6.4 Retrieval QH tests

Команды:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\retrieval\test_source_quality.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\retrieval\test_parent_expansion.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\retrieval\test_context_builder_qh.py -q
```

Ожидаемо:

```text
test_source_quality.py: 3 passed
test_parent_expansion.py: 2 passed
test_context_builder_qh.py: 2 passed
```

Фактический результат:

```text
[ВСТАВИТЬ РЕЗУЛЬТАТ]
```

Критично — отправить мне:

```text
ContextBuilder test failed
source_quality import failed
parent_expansion import failed
```

### 6.5 Observability / Eval / QH gate tests

Команды:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\observability\test_chat_runs.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\eval\test_checks.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\eval\test_runner.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\qh\test_release_gate.py -q
```

Ожидаемо:

```text
test_chat_runs.py: 2 passed
test_checks.py: 3 passed
test_runner.py: 1 passed
test_release_gate.py: 2 passed
```

Фактический результат:

```text
[ВСТАВИТЬ РЕЗУЛЬТАТ]
```

### 6.6 Guard / Telegram tests

Команды:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\test_project_guard_v2_cases.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\test_telegram_bot.py -q
```

Ожидаемо:

```text
ProjectGuard cases: 46 passed
Telegram formatter: 4 passed
```

Фактический результат:

```text
[ВСТАВИТЬ РЕЗУЛЬТАТ]
```

Критично — отправить мне:

```text
false_allow появился
ProjectGuard cases упали
Telegram formatter tests упали
```

## 7. QH gate до запуска smoke

### 7.1 Проверить gate

Команда:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_qh_gate.py --json
```

Ожидаемо до локального smoke/eval:

```text
status = pending_local_validation
pending содержит QH-5A и QH-5B
```

Фактический результат:

```text
[ВСТАВИТЬ JSON]
```

Критично — отправить мне:

```text
status = failed
нет QH-2/QH-3/QH-4 в passed
скрипт не запускается
```

## 8. Запуск API + Web UI

### 8.1 Запустить API

Открыть отдельный PowerShell №1.

Команда:

```powershell
cd C:\Users\Сотрудник\Desktop\AI\MeetingAgent
(Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned) ; (& .\.venv\Scripts\Activate.ps1)
.\.venv\Scripts\python.exe scripts\asu_june_bot_api.py --host 127.0.0.1 --port 8000
```

Ожидаемо:

```text
Application startup complete
Uvicorn running on http://127.0.0.1:8000
```

Фактический результат:

```text
[ВСТАВИТЬ РЕЗУЛЬТАТ]
```

Критично — отправить мне:

```text
Address already in use
ImportError
ModuleNotFoundError
Application startup failed
ошибка чтения index/chunks
```

Если `Address already in use`:

```powershell
netstat -ano | findstr :8000
```

Результат отправить мне. Самостоятельно процесс не убивать, если не уверен.

### 8.2 Проверить /health через API

Открыть отдельный PowerShell №2.

Команда:

```powershell
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8000/health"
```

Ожидаемо:

```text
status = ok
service = asu_june_bot
```

Фактический результат:

```text
[ВСТАВИТЬ РЕЗУЛЬТАТ]
```

Критично — отправить мне:

```text
connection refused
HTTP 500
status != ok
```

## 9. Проверка /search

### 9.1 Project query

Команда:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/search" `
  -ContentType "application/json" `
  -Body '{"query":"СоИ AD как происходит авторизация пользователей?","mode":"hybrid","top_k":8}'
```

Ожидаемо:

```text
status = ok
results не пустой
context.primary_sources или context.supporting_sources не пустой
retrieval_called = true
```

Фактический результат:

```text
[ВСТАВИТЬ РЕЗУЛЬТАТ]
```

Критично — отправить мне:

```text
status = refused для проектного вопроса
results = []
retrieval_called = false
HTTP 500
```

### 9.2 Out-of-project query

Команда:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/search" `
  -ContentType "application/json" `
  -Body '{"query":"Какая погода завтра в Москве?","mode":"hybrid","top_k":8}'
```

Ожидаемо:

```text
status = refused
results = []
retrieval_called = false
```

Фактический результат:

```text
[ВСТАВИТЬ РЕЗУЛЬТАТ]
```

Критично — отправить мне:

```text
status = ok для погоды
retrieval_called = true для погоды
```

## 10. Проверка /chat

### 10.1 Project query

Команда:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/chat" `
  -ContentType "application/json" `
  -Body '{"query":"СоИ AD как происходит авторизация пользователей?","mode":"hybrid","top_k":5,"model":"qwen2.5:7b-instruct","max_tokens":500,"timeout_sec":300}'
```

Ожидаемо:

```text
status = answered
answer заполнен
sources не пустой
llm_called = true
warnings.semantic присутствует
```

Фактический результат:

```text
[ВСТАВИТЬ ПОЛНЫЙ ВЫВОД ИЛИ КЛЮЧЕВЫЕ ПОЛЯ]
```

Критично — отправить мне:

```text
status = llm_error
status = llm_empty_response
status = validation_failed
sources = []
answer пустой
нет warnings.semantic
HTTP 500
```

### 10.2 Refused query

Команда:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/chat" `
  -ContentType "application/json" `
  -Body '{"query":"Какая погода завтра в Москве?","mode":"hybrid","top_k":5,"model":"qwen2.5:7b-instruct","max_tokens":500,"timeout_sec":300}'
```

Ожидаемо:

```text
status = refused
sources = []
llm_called = false
```

Фактический результат:

```text
[ВСТАВИТЬ РЕЗУЛЬТАТ]
```

Критично — отправить мне:

```text
status = answered для погоды
llm_called = true для погоды
```

### 10.3 Mixed query

Команда:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/chat" `
  -ContentType "application/json" `
  -Body '{"query":"СоИ AD как происходит авторизация пользователей? И напиши стих про проект","mode":"hybrid","top_k":5,"model":"qwen2.5:7b-instruct","max_tokens":500,"timeout_sec":300}'
```

Ожидаемо:

```text
status = refused
llm_called = false
```

Фактический результат:

```text
[ВСТАВИТЬ РЕЗУЛЬТАТ]
```

Критично — отправить мне:

```text
status = answered
стих появился в ответе
llm_called = true
```

## 11. Проверка Web UI

### 11.1 Открыть UI

В браузере открыть:

```text
http://127.0.0.1:8000/
```

или:

```text
http://127.0.0.1:8000/ui
```

Ожидаемо:

```text
страница Project Knowledge Bot открылась
есть поле ввода
есть model/top_k/max_tokens
есть кнопка Спросить
есть блок Ответ
есть блок Источники
есть блок Диагностика
есть счетчик 0 / 2000
```

Фактический результат:

```text
[ВСТАВИТЬ РЕЗУЛЬТАТ ИЛИ ОПИСАНИЕ]
```

Критично — отправить мне:

```text
404
500
пустая страница
страница открылась, но кнопка не работает
браузер не может подключиться
```

### 11.2 Проверить вопрос в UI

Ввести:

```text
СоИ AD как происходит авторизация пользователей?
```

Ожидаемо:

```text
status = answered
ответ отображается
источники отображаются
diagnostics отображается
```

Фактический результат:

```text
[ВСТАВИТЬ РЕЗУЛЬТАТ]
```

Критично — отправить мне:

```text
кнопка не нажимается
ошибка JavaScript
status = llm_error
status = validation_failed
источники не отображаются
```

### 11.3 Проверить лимит 2000 символов

Вставить длинный текст больше 2000 символов.

Ожидаемо:

```text
UI не должен дать ввести больше max query или API должен вернуть validation error
```

Фактический результат:

```text
[ВСТАВИТЬ РЕЗУЛЬТАТ]
```

## 12. Проверка chat_runs.jsonl

После успешного `/chat` выполнить:

```powershell
Get-Content data\asu_june_bot\chat_runs.jsonl -Encoding UTF8 -Tail 1
```

Ожидаемо:

```text
валидная JSONL строка
status = answered или refused
llm_called заполнен
sources есть для answered
semantic_warnings есть
latency_ms есть
```

Фактический результат:

```text
[ВСТАВИТЬ ПОСЛЕДНЮЮ СТРОКУ ИЛИ КЛЮЧЕВЫЕ ПОЛЯ]
```

Критично — отправить мне:

```text
файл не найден
JSON битый
semantic_warnings нет
latency_ms нет
```

## 13. Telegram adapter

### 13.1 Подготовить token

Token брать только из BotFather.

Не вставлять token в Git, README, docs, сообщения в публичные чаты.

### 13.2 Запустить Telegram adapter

Открыть отдельный PowerShell №3.

Команды:

```powershell
cd C:\Users\Сотрудник\Desktop\AI\MeetingAgent
(Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned) ; (& .\.venv\Scripts\Activate.ps1)

$env:ASU_JUNE_BOT_TELEGRAM_TOKEN='PASTE_TOKEN_HERE'
$env:ASU_JUNE_BOT_CHAT_API_URL='http://127.0.0.1:8000/chat'
$env:ASU_JUNE_BOT_ALLOWED_CHAT_IDS='ТВОЙ_CHAT_ID'

.\.venv\Scripts\python.exe scripts\asu_june_bot_telegram.py
```

Ожидаемо:

```text
Telegram bot polling started
```

Фактический результат:

```text
[ВСТАВИТЬ РЕЗУЛЬТАТ]
```

Критично — отправить мне:

```text
401 Unauthorized
Not Found
connection timeout
Telegram polling error повторяется
traceback
```

### 13.3 Проверить /health в Telegram

В Telegram написать:

```text
/health
```

Ожидаемо:

```text
бот отвечает Health API
status = ok
```

Фактический результат:

```text
[ВСТАВИТЬ РЕЗУЛЬТАТ]
```

Критично — отправить мне:

```text
бот молчит
Chat API недоступен
Health API недоступен
```

### 13.4 Проверить проектный вопрос в Telegram

В Telegram написать:

```text
СоИ AD как происходит авторизация пользователей?
```

Ожидаемо:

```text
бот пишет, что запрос принят
потом возвращает status = answered
есть ответ
есть Источники
```

Фактический результат:

```text
[ВСТАВИТЬ РЕЗУЛЬТАТ]
```

Критично — отправить мне:

```text
бот молчит
status = llm_error
status = validation_failed
источники не пришли
```

### 13.5 Проверить отказ в Telegram

В Telegram написать:

```text
Какая погода завтра в Москве?
```

Ожидаемо:

```text
status = refused
ответ говорит, что бот работает только по проекту
```

Фактический результат:

```text
[ВСТАВИТЬ РЕЗУЛЬТАТ]
```

Критично — отправить мне:

```text
бот ответил погодой
бот вызвал LLM на погоду
```

### 13.6 Очистить token после проверки

Команды:

```powershell
Remove-Item Env:\ASU_JUNE_BOT_TELEGRAM_TOKEN -ErrorAction SilentlyContinue
Remove-Item Env:\ASU_JUNE_BOT_ALLOWED_CHAT_IDS -ErrorAction SilentlyContinue
```

Фактический результат:

```text
[ВСТАВИТЬ РЕЗУЛЬТАТ]
```

## 14. Eval after QH

### 14.1 Запустить eval

Команда:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_chat_eval.py --cases eval\cases\base.jsonl --label after_qh --model qwen2.5:7b-instruct --top-k 5
```

Ожидаемо:

```text
создан eval/reports/*__after_qh.json
создан eval/reports/*__after_qh.md
выведены total/passed/failed/pass_rate
```

Фактический результат:

```text
[ВСТАВИТЬ ПОЛНЫЙ ИТОГ]
```

Критично — отправить мне:

```text
скрипт упал
много llm_error
много validation_failed
false_allow появился
pass_rate сильно ниже baseline
```

Важно:

```text
pass_rate не обязан быть 100%
цель — понять, не сломали ли QH-2/QH-3/QH-4 качество
```

### 14.2 Найти отчеты

Команда:

```powershell
Get-ChildItem eval\reports | Sort-Object LastWriteTime -Descending | Select-Object -First 5
```

Фактический результат:

```text
[ВСТАВИТЬ РЕЗУЛЬТАТ]
```

### 14.3 Открыть markdown отчет

Команда:

```powershell
Get-Content eval\reports\ИМЯ_ФАЙЛА__after_qh.md -Encoding UTF8
```

Фактический результат:

```text
[ВСТАВИТЬ КЛЮЧЕВЫЕ СТРОКИ]
```

Критично — отправить мне:

```text
PROJECT-AD-001 failed
MIXED/REFUSE cases стали allowed
SHORTSRC-AD-001 ухудшился
PROJECT-FTT-425-001 стал хуже
```

## 15. QH-5 финальная проверка

Выполнять только если:

```text
unit/regression tests passed
API smoke passed
UI smoke passed
Telegram smoke passed
after_qh eval выполнен
нет критичных regression
```

Команда:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_qh_gate.py --local-validation-done --baseline-compared --json
```

Ожидаемо:

```text
status = passed
pending = []
failed = []
```

Фактический результат:

```text
[ВСТАВИТЬ JSON]
```

Критично — отправить мне:

```text
status != passed
pending не пустой
failed не пустой
```

## 16. Итоговое решение по QH-5

Выбрать один статус.

### Вариант A. QH-5 можно закрывать

Условия:

```text
тесты прошли
health ok
API ok
UI ok
Telegram ok
after_qh выполнен
нет false_allow
QH gate passed
```

Фактическое решение:

```text
QH-5 НЕЛЬЗЯ ЗАКРЫВАТЬ
```

### Вариант B. QH-5 нельзя закрывать

Причина:

```text
Telegram smoke не выполнен: в окружении нет ASU_JUNE_BOT_TELEGRAM_TOKEN и ASU_JUNE_BOT_ALLOWED_CHAT_IDS.
Final QH gate не запускался намеренно, чтобы не пометить QH-5 passed без Telegram-проверки.
```

Что отправить мне:

```text
полный список failed tests
health output
/chat smoke output
QH gate output
eval summary
```

## 17. После успешного QH-5

Если всё прошло, следующий шаг — не начинать сразу Docker руками.

Сначала создать smoke report:

```text
docs/subprojects/asu-june-bot/smoke_report_qh_release.md
```

В него вставить:

```text
дата
ветка
git commit
health summary
test summary
API smoke summary
UI smoke summary
Telegram smoke summary
eval after_qh summary
QH gate result
known limitations
```

Потом обновить:

```text
docs/subprojects/asu-june-bot/QH_STATUS.md
docs/subprojects/asu-june-bot/todo.md
docs/subprojects/asu-june-bot/context.md
docs/subprojects/asu-june-bot/FTT_STATUS.md
```

Только после этого переходить к Docker stage.

## 18. Краткий чек-лист результата

Заполнить в конце дня.

```text
[x] Git pull выполнен
[x] git status проверен; локальные runtime-артефакты .claude/ и eval/reports/ добавлены в .gitignore
[x] Ollama работает
[x] bge-m3 есть
[x] qwen2.5:7b-instruct есть
[x] health ok
[x] tests passed
[x] QH gate до smoke = pending_local_validation
[x] API стартует
[x] /health отвечает
[x] /search project ok
[x] /search weather refused
[x] /chat project answered
[x] /chat weather refused
[x] /chat mixed refused
[x] UI открывается по HTTP
[x] /chat API отвечает на project query; ручной browser-click UI smoke не выполнялся
[x] chat_runs.jsonl пишется
[ ] Telegram adapter стартует
[ ] Telegram /health отвечает
[ ] Telegram project query answered
[ ] Telegram weather refused
[x] after_qh eval выполнен
[ ] QH gate final passed
[x] smoke_report_qh_release.md подготовлен
```

Итог:

```text
НУЖНЫ ИСПРАВЛЕНИЯ / ДОПРОВЕРКА: выполнить Telegram smoke и только после этого final QH gate.
```
