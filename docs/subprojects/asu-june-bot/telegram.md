# Telegram adapter для Project Knowledge Bot

Обновлено: 2026-05-16.

## Назначение

Telegram adapter позволяет задавать вопросы Project Knowledge Bot через Telegram.

Архитектура:

```text
Telegram user
  -> Telegram Bot API long polling
  -> scripts/asu_june_bot_telegram.py
  -> local FastAPI POST /chat
  -> ChatService
  -> SearchService + LLM
  -> ответ в Telegram
```

Adapter не содержит собственной retrieval/chat логики. Он только отправляет вопрос в локальный `/chat`.

## Требования

Должны быть запущены:

```text
Ollama
Project Knowledge Bot API на http://127.0.0.1:8000
```

API запуск:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_api.py --host 127.0.0.1 --port 8000
```

Проверка:

```powershell
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8000/health"
```

## Переменные окружения

Обязательная:

```powershell
$env:ASU_JUNE_BOT_TELEGRAM_TOKEN='PASTE_TOKEN_HERE'
```

Опциональные:

```powershell
$env:ASU_JUNE_BOT_CHAT_API_URL='http://127.0.0.1:8000/chat'
$env:ASU_JUNE_BOT_ALLOWED_CHAT_IDS='123456789,987654321'
$env:ASU_JUNE_BOT_TELEGRAM_TOP_K='5'
$env:ASU_JUNE_BOT_TELEGRAM_MODEL='qwen2.5:7b-instruct'
$env:ASU_JUNE_BOT_TELEGRAM_MAX_TOKENS='700'
$env:ASU_JUNE_BOT_TELEGRAM_TIMEOUT_SEC='300'
```

## Запуск

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_telegram.py
```

Ожидаемо:

```text
Telegram bot polling started
```

## Команды в Telegram

```text
/start
/help
/health
```

Обычное текстовое сообщение считается вопросом к `/chat`.

## Ограничения

```text
максимальная длина запроса: 2000 символов
поддерживаются только текстовые сообщения
ответы длиннее лимита Telegram режутся на части
Telegram token нельзя коммитить в Git
```

## Безопасность

Перед демонстрацией рекомендуется ограничить доступ по chat id:

```powershell
$env:ASU_JUNE_BOT_ALLOWED_CHAT_IDS='123456789'
```

Если `ASU_JUNE_BOT_ALLOWED_CHAT_IDS` не задан, бот отвечает всем, кто знает Telegram bot username.

## Очистка token после работы

```powershell
Remove-Item Env:\ASU_JUNE_BOT_TELEGRAM_TOKEN -ErrorAction SilentlyContinue
Remove-Item Env:\ASU_JUNE_BOT_ALLOWED_CHAT_IDS -ErrorAction SilentlyContinue
```

## Troubleshooting

### Telegram пишет, что Chat API недоступен

Проверить:

```powershell
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8000/health"
```

Если не отвечает — запустить API.

### Telegram adapter стартует, но бот молчит

Проверить:

```powershell
Get-ChildItem Env:ASU_JUNE_BOT*
```

Проверить, что token правильный и у ПК есть интернет.

### Ответы слишком длинные

Уменьшить:

```powershell
$env:ASU_JUNE_BOT_TELEGRAM_MAX_TOKENS='500'
```

### Модель отвечает медленно

Проверить, что используется:

```text
qwen2.5:7b-instruct
```

Не использовать qwen3:8b как default на CPU.
