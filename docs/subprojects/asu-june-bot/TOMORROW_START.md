# Завтрашний старт Project Knowledge Bot

Обновлено: 2026-05-16.

## Цель

После случайного выключения рабочего ПК через AnyDesk завтра нужно быстро восстановить рабочее состояние и проверить:

```text
Git актуален
тесты проходят
Ollama доступен
API работает
Web UI открывается
Telegram adapter отвечает
```

## 0. Открыть проект

```powershell
cd C:\Users\Сотрудник\Desktop\AI\MeetingAgent
(Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned) ; (& .\.venv\Scripts\Activate.ps1)
```

## 1. Забрать изменения из Git

```powershell
git checkout docs/asu-june-bot-subproject
git pull --ff-only origin docs/asu-june-bot-subproject
git status --short
```

Ожидаемо:

```text
пустой вывод git status --short
```

Если есть локальные изменения — не делай reset сразу. Сначала пришли вывод.

## 2. Проверить Ollama и модели

```powershell
ollama list
```

Должны быть:

```text
bge-m3
qwen2.5:7b-instruct
```

Если Ollama не запущен:

```powershell
ollama serve
```

Если модели нет:

```powershell
ollama pull bge-m3
ollama pull qwen2.5:7b-instruct
```

## 3. Проверить health v2

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

Если `vector_ready = false`, Web UI и Telegram могут отвечать хуже или не отвечать через hybrid/vector.

## 4. Быстрый regression набор

```powershell
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\api\test_health.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\api\test_search_smoke.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\api\test_chat_smoke.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\chat\test_chat_service.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\eval\test_checks.py -q
```

Ожидаемо после последних изменений:

```text
test_health.py: 1 passed
test_search_smoke.py: 4 passed
test_chat_smoke.py: 7 passed
test_chat_service.py: 7 passed
test_checks.py: 3 passed
```

## 5. Запустить API + Web UI

PowerShell №1:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_api.py --host 127.0.0.1 --port 8000
```

Ожидаемо:

```text
Application startup complete
Uvicorn running on http://127.0.0.1:8000
```

Открыть в браузере:

```text
http://127.0.0.1:8000/
```

или:

```text
http://127.0.0.1:8000/ui
```

## 6. Проверить API вручную

PowerShell №2:

```powershell
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8000/health"
```

Проверка `/chat`:

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
sources != []
diagnostics.llm_called = true
```

## 7. Проверить лимит запроса

В API и UI установлен лимит:

```text
MAX_QUERY_CHARS = 2000
```

Слишком длинный запрос должен возвращать HTTP 422.

## 8. Запустить Telegram adapter

Сначала создай Telegram-бота через BotFather и получи token.

PowerShell №3:

```powershell
$env:ASU_JUNE_BOT_TELEGRAM_TOKEN='PASTE_TOKEN_HERE'
$env:ASU_JUNE_BOT_CHAT_API_URL='http://127.0.0.1:8000/chat'

.\.venv\Scripts\python.exe scripts\asu_june_bot_telegram.py
```

Если хочешь ограничить доступ только своим chat id:

```powershell
$env:ASU_JUNE_BOT_ALLOWED_CHAT_IDS='123456789'
```

Команды в Telegram:

```text
/start
/help
/health
```

Обычное сообщение считается вопросом к `/chat`.

## 9. Если Telegram не отвечает

Проверить по порядку:

```text
1. API запущен на 127.0.0.1:8000
2. /health отвечает
3. токен ASU_JUNE_BOT_TELEGRAM_TOKEN задан
4. у ПК есть интернет
5. Telegram не заблокирован сетью
6. в PowerShell с Telegram adapter нет traceback
```

Проверить env:

```powershell
Get-ChildItem Env:ASU_JUNE_BOT*
```

Сбросить token после работы:

```powershell
Remove-Item Env:\ASU_JUNE_BOT_TELEGRAM_TOKEN -ErrorAction SilentlyContinue
```

## 10. Что не делать перед сдачей

```text
не запускать --reset без причины
не удалять data/asu_june_bot
не пересчитывать embeddings, если индекс уже готов
не менять модель embeddings bge-m3
не начинать Docker до QH-5
не чинить все baseline failures перед демонстрацией
```

Для сдачи сейчас важнее:

```text
API работает
UI работает
Telegram работает
project-only guard отказывает на мусор
ответы содержат sources/citations
```
