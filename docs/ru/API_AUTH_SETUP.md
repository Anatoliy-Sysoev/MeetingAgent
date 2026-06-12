# Настройка API и авторизации

[English](../en/API_AUTH_SETUP.md) | [Русский](API_AUTH_SETUP.md)

Этот документ описывает аутентификацию, авторизацию и использование HTTP API MeetingAgent.

---

## Текущее состояние

**Единственный полностью рабочий способ доступа — machine Bearer token (`MEETINGAGENT_API_TOKEN`).**

Локальный логин (`POST /auth/local/login`) работает, но только если пользовательский аккаунт уже существует в базе данных. Первичная регистрация администратора **не реализована** — создать первого пользователя через API или UI пока невозможно. Admin API и admin UI не реализованы. Внешние провайдеры (Yandex ID, Google, OIDC) не реализованы.

Это означает:

- Для скриптов, CI, автоматизации и межсервисных вызовов: используйте Bearer token.
- Для браузерных сессий: локальный логин доступен только после того, как запись пользователя добавлена напрямую в SQLite базу данных авторизации. Это сценарий для разработчика/администратора.
- Публичная регистрация отсутствует и не планируется в MVP.

---

## Модель аутентификации

API использует два типа принципалов:

| Тип принципала | Способ аутентификации | CSRF для write-запросов |
|---|---|---|
| **machine** | `Authorization: Bearer <token>` | Нет |
| **user** (браузер) | Session cookie `ma_session` | Да (заголовок `X-CSRF-Token`) |

### Machine Bearer Token

Задайте `MEETINGAGENT_API_TOKEN` в окружении (`.env` или системное окружение). Значение должно быть достаточно длинной случайной строкой — не менее 32 символов. Все запросы должны включать:

```
Authorization: Bearer <token>
```

Если заголовок присутствует, но токен не совпадает — сервер вернёт `401`. Если заголовок отсутствует — запрос считается неаутентифицированным (большинство защищённых маршрутов вернут `401`).

Machine principal имеет фиксированный узкий набор прав: чтение встреч, загрузка, запуск/отмена/чтение jobs, поиск и чат. Управление пользователями, ролями, настройками и удаление встреч недоступны.

### Локальный логин (браузерная сессия)

```
POST /auth/local/login
Content-Type: application/json

{"email": "user@example.com", "password": "secret"}
```

При успехе ответ устанавливает два cookie:
- `ma_session` — HttpOnly, SameSite=Lax, Secure при HTTPS. JavaScript не может читать это cookie.
- `ma_session_csrf` — non-HttpOnly. JavaScript должен читать это значение и передавать его как `X-CSRF-Token` для всех write и action запросов.

Тело ответа также содержит:
- `csrf_token` — то же значение, что и CSRF cookie, для клиентов, которым удобнее читать из JSON.

При ошибке: `401 Unauthorized` с общим сообщением, независимо от того, существует email или нет.

После логина вызовите `GET /auth/me`, чтобы подтвердить сессию и получить identity и роли.

### CSRF

Все write и action запросы, аутентифицированные через cookie (POST/PUT/DELETE и `/chat`), должны включать:

```
X-CSRF-Token: <csrf_token>
```

Machine Bearer запросы освобождены от CSRF.

Отсутствующий или неверный CSRF token возвращает `403 Forbidden`.

### Выход

```
POST /auth/logout
X-CSRF-Token: <csrf_token>
```

Возвращает `204 No Content`. Очищает оба cookie и отзывает серверную сессию.

---

## RBAC

Три встроенные роли:

| Роль | Права |
|---|---|
| **viewer** | meetings.read, artifacts.read, transcripts.read, jobs.read, search.use, chat.use |
| **editor** | viewer + meetings.upload, meetings.edit, jobs.start, jobs.cancel, jobs.retry, artifacts.edit |
| **admin** | editor + users.manage, roles.manage, settings.manage, audit.read, meetings.delete, tokens.manage |

Machine principal имеет: `meetings.upload`, `meetings.read`, `artifacts.read`, `transcripts.read`, `search.use`, `chat.use`, `jobs.start`, `jobs.cancel`, `jobs.retry`, `jobs.read`. Не имеет: `users.manage`, `roles.manage`, `settings.manage`, `tokens.manage`, `meetings.delete`.

Неизвестные роли не дают никаких прав.

---

## Полный справочник API

Все пути относительны базового URL API (например, `http://127.0.0.1:8000`).

### Auth

| Метод | Путь | Авторизация | Примечания |
|---|---|---|---|
| POST | `/auth/local/login` | Нет | Возвращает session cookie + csrf_token |
| GET | `/auth/me` | Cookie-сессия | Identity, роли |
| POST | `/auth/logout` | Cookie + CSRF | Отзывает сессию |

### Meetings (только чтение)

| Метод | Путь | Право | Примечания |
|---|---|---|---|
| GET | `/meetings` | meetings.read | Постраничный список. Query params: `offset`, `limit` |
| GET | `/meetings/{id}` | meetings.read | Карточка встречи |
| GET | `/meetings/{id}/transcript` | transcripts.read | Транскрипт или `{"available": false}` |
| GET | `/meetings/{id}/artifacts` | artifacts.read | Список метаданных артефактов |
| GET | `/meetings/{id}/artifacts/{name}` | artifacts.read | Содержимое текстового артефакта. 413 при превышении лимита. 415 для бинарных артефактов. |

Лимит текстового артефакта: **10 МиБ** (настраивается через `meetings.max_text_artifact_bytes`). Бинарные артефакты возвращают `415 Unsupported Media Type`.

### Ingest

| Метод | Путь | Право | Примечания |
|---|---|---|---|
| POST | `/meetings/ingest` | meetings.upload (write access) | Multipart-загрузка. 201 при успехе, 409 при дубликате по sha256. |

### Job Pipeline

| Метод | Путь | Право | Примечания |
|---|---|---|---|
| POST | `/meetings/{id}/jobs/{stage}` | write access | Запустить стадию pipeline. Возвращает 202. |
| GET | `/meetings/{id}/jobs/{job_id}` | jobs.read | Статус задачи |
| POST | `/meetings/{id}/jobs/{job_id}/cancel` | write access | Отменить задачу |
| GET | `/jobs/active` | jobs.read | Текущая активная задача или `{}` |

### Поиск и чат

| Метод | Путь | Право | Примечания |
|---|---|---|---|
| POST | `/search` | search.use | RAG-поиск |
| POST | `/chat` | chat.use | Ответ с citations. Для cookie-клиентов требуется CSRF. |

### Здоровье сервиса

| Метод | Путь | Auth | Примечания |
|---|---|---|---|
| GET | `/health` | Нет | Проверка работоспособности |

---

## HTTP-коды ответов

| Код | Значение |
|---|---|
| 200 | OK |
| 201 | Created (ingest) |
| 202 | Accepted (задача запущена) |
| 204 | No Content (logout) |
| 400 | Bad Request (ошибка валидации) |
| 401 | Unauthorized — нет учётных данных или неверный Bearer token |
| 403 | Forbidden — аутентифицирован, но прав недостаточно; или CSRF отсутствует/неверен |
| 404 | Not Found |
| 409 | Conflict — дублирующийся файл при ingest (совпадение sha256) |
| 413 | Payload Too Large — транскрипт или артефакт превышает лимит байт |
| 415 | Unsupported Media Type — бинарный артефакт запрошен как текст |
| 422 | Unprocessable Entity — ошибка схемы тела запроса |
| 429 | Too Many Requests — сработал throttle логина; заголовок `Retry-After` включён |
| 500 | Internal Server Error |

---

## Throttling логина

Неудачные попытки входа считаются по паре (sha256(email), IP клиента). После `max_failures` неудач за `window_seconds` секунд эндпоинт возвращает `429 Too Many Requests` с заголовком `Retry-After`. Попытка, которая достигает порога, сама получает 429.

Блокировка снимается при успешном входе.

Настройка в `config.yaml`:

```yaml
auth:
  login_throttle:
    enabled: true
    max_failures: 5
    window_seconds: 300
    block_seconds: 900      # 15 минут
    max_entries: 10000
    trusted_proxy_cidrs: [] # см. раздел Reverse Proxy
```

Для отключения throttling (только разработка):

```yaml
auth:
  login_throttle:
    enabled: false
```

---

## Примеры запросов

### PowerShell — Machine Bearer

```powershell
$token = $env:MEETINGAGENT_API_TOKEN
$headers = @{ Authorization = "Bearer $token" }

# Список встреч
Invoke-RestMethod http://127.0.0.1:8000/meetings -Headers $headers

# Карточка встречи
Invoke-RestMethod http://127.0.0.1:8000/meetings/2026-01-15__kickoff -Headers $headers

# Транскрипт
Invoke-RestMethod http://127.0.0.1:8000/meetings/2026-01-15__kickoff/transcript -Headers $headers

# Загрузка файла встречи
$form = @{
  file  = Get-Item "C:\recordings\meeting.mp4"
  title = "Стартовая встреча"
  date  = "2026-01-15"
}
Invoke-RestMethod http://127.0.0.1:8000/meetings/ingest `
  -Method Post -Headers $headers -Form $form

# Запуск транскрибации
Invoke-RestMethod http://127.0.0.1:8000/meetings/2026-01-15__kickoff/jobs/transcribe `
  -Method Post -Headers $headers

# Поиск
$body = @{ query = "риски проекта" } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/search `
  -Method Post -Headers $headers `
  -ContentType "application/json" -Body $body
```

### curl — Machine Bearer

```bash
TOKEN="your-api-token"

# Список встреч
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/meetings

# Транскрипт
curl -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/meetings/2026-01-15__kickoff/transcript

# Загрузка
curl -X POST http://127.0.0.1:8000/meetings/ingest \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/path/to/meeting.mp4" \
  -F "title=Стартовая встреча" \
  -F "date=2026-01-15"

# Запуск задачи
curl -X POST http://127.0.0.1:8000/meetings/2026-01-15__kickoff/jobs/transcribe \
  -H "Authorization: Bearer $TOKEN"

# Поиск
curl -X POST http://127.0.0.1:8000/search \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "риски проекта"}'
```

### curl — Браузерная сессия (Cookie + CSRF)

```bash
BASE=http://127.0.0.1:8000

# Логин — сохраняем cookies
curl -c cookies.txt -X POST "$BASE/auth/local/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"secret"}'
# В ответе есть csrf_token; сохраните его.

CSRF="<csrf_token из ответа>"

# Чтение (CSRF не нужен для GET)
curl -b cookies.txt "$BASE/meetings"

# Запись (нужен CSRF)
curl -b cookies.txt -X POST "$BASE/meetings/ingest" \
  -H "X-CSRF-Token: $CSRF" \
  -F "file=@meeting.mp4" -F "title=Тест" -F "date=2026-01-15"

# Выход
curl -b cookies.txt -X POST "$BASE/auth/logout" \
  -H "X-CSRF-Token: $CSRF"
```

---

## Справочник конфигурации

`.env.example` / `.env`:

```ini
# Обязательно для Bearer-аутентификации
MEETINGAGENT_API_TOKEN=замените-на-длинный-случайный-секрет

# Порт API сервера (Docker / docker compose)
MEETINGAGENT_API_PORT=8000
```

`config.yaml` (скопируйте из `config.example.yaml`):

```yaml
auth:
  login_throttle:
    enabled: true
    max_failures: 5
    window_seconds: 300
    block_seconds: 900
    max_entries: 10000
    trusted_proxy_cidrs: []

meetings:
  max_text_artifact_bytes: 10485760   # 10 МиБ
```

---

## HTTPS и Reverse Proxy

API не терминирует TLS. Для продакшена запускайте за reverse proxy (nginx, Caddy, Traefik).

При работе за прокси, который добавляет `X-Forwarded-For`, настройте `trusted_proxy_cidrs`, чтобы API корректно определял реальный IP клиента для throttling:

```yaml
auth:
  login_throttle:
    trusted_proxy_cidrs:
      - "127.0.0.1/32"
      - "10.0.0.0/8"
```

API определяет реальный IP, обходя `X-Forwarded-For` справа налево и пропуская IP из доверенных подсетей. Используется первый недоверенный hop. Без `trusted_proxy_cidrs` (пустой список по умолчанию) всегда используется IP прямого пира, а `X-Forwarded-For` игнорируется — это безопасный дефолт для хоста, напрямую открытого в интернет.

Cookies устанавливаются с атрибутом `Secure` только если запрос пришёл по HTTPS. В продакшене используйте HTTPS.

---

## Безопасное хранение

| Данные | Где хранить | Никогда не делать |
|---|---|---|
| `MEETINGAGENT_API_TOKEN` | `.env` (не коммитить) или системное окружение | Коммитить в Git |
| `config.yaml` | Только локально, в gitignore | Коммитить в Git |
| `data/auth.db` (SQLite авторизация) | Только локально, в gitignore | Коммитить в Git |
| `meetings/` | Только локально, в gitignore | Коммитить в Git |
| `logs/` | Только локально, в gitignore | Коммитить в Git |
| `data/` (индексы, чанки) | Только локально, в gitignore | Коммитить в Git |

Генерация сильного токена:

```powershell
# PowerShell
[System.Web.Security.Membership]::GeneratePassword(48, 8)
# или
-join ((48..122) | Get-Random -Count 48 | % {[char]$_})
```

```bash
# bash / Linux
openssl rand -hex 32
```

---

## Ограничения и дорожная карта

| Функция | Статус |
|---|---|
| Machine Bearer token | **Работает** |
| Локальный логин (cookie-сессия) | **Работает** — требует существующей записи пользователя |
| Первичная регистрация администратора | **Не реализована** |
| Admin user API | **Не реализован** |
| Admin UI | **Не реализован** |
| Yandex ID / Google / OIDC | **Не реализованы** |
| Публичная регистрация | **Не планируется в MVP** |

Следующий запланированный шаг: **MA-AUTH-BOOTSTRAP-ADMIN** — первичная регистрация администратора и admin user API.
