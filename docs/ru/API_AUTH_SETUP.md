# Настройка API и авторизации

[English](../en/API_AUTH_SETUP.md) | [Русский](API_AUTH_SETUP.md)

Этот документ описывает аутентификацию, авторизацию и использование HTTP API MeetingAgent.

---

## Текущее состояние

**Machine Bearer token (`MEETINGAGENT_API_TOKEN`) — основной способ доступа для скриптов и автоматизации. Локальный логин с cookie-сессиями работает для браузера; первичная регистрация администратора и управление пользователями реализованы.**

Это означает:

- Для скриптов, CI, автоматизации и межсервисных вызовов: используйте Bearer token.
- Для браузерных сессий: используйте `POST /admin/bootstrap`, чтобы создать первого администратора, затем `POST /auth/local/login`.
- Публичная регистрация отсутствует и не планируется в MVP.
- UI управления пользователями пока не реализован — управляйте пользователями через admin API.

### Замечание о встроенном Web UI

Встроенный web UI (`/` и `/ui`) поддерживает локальный login, показывает текущее auth-состояние, получает CSRF через `GET /auth/csrf` и отправляет `X-CSRF-Token` для cookie-аутентифицированных `POST /chat` и review-действий. Credentials и CSRF token не сохраняются в localStorage/sessionStorage.

---

## Модель аутентификации

API использует два типа принципалов:

| Тип принципала | Способ аутентификации | CSRF для write/action запросов |
|---|---|---|
| **machine** | `Authorization: Bearer <token>` | Нет |
| **user** (браузер) | Session cookie `ma_session` | Да (заголовок `X-CSRF-Token`) |

### Machine Bearer Token

Задайте `MEETINGAGENT_API_TOKEN` в окружении (`.env` или системное окружение). Значение должно быть достаточно длинной случайной строкой — не менее 32 символов. Все запросы должны включать:

```
Authorization: Bearer <token>
```

Если заголовок присутствует, но токен не совпадает — сервер вернёт `401`. Если заголовок `Authorization` отсутствует полностью — сервер проверяет наличие session cookie; если и его нет, запрос считается неаутентифицированным (большинство защищённых маршрутов вернут `401`).

**Важно**: любой присутствующий заголовок `Authorization`, который имеет неверный формат или содержит неправильный токен, сразу возвращает `401` — тихого fallback на cookie в этом случае нет.

Machine principal имеет фиксированный узкий набор прав: чтение встреч, загрузка, запуск/отмена/чтение jobs, поиск и чат. Управление пользователями, ролями, настройками и удаление встреч недоступны.

### Локальный логин (браузерная сессия)

```
POST /auth/local/login
Content-Type: application/json

{"email": "user@example.com", "password": "secret"}
```

Требует заранее созданного активного пользователя с local credential и назначенными ролями. При успехе ответ устанавливает два cookie:
- `ma_session` — HttpOnly, SameSite=Lax, Secure при HTTPS. JavaScript не может читать это cookie.
- `ma_session_csrf` — non-HttpOnly. JavaScript должен читать это значение и передавать его как `X-CSRF-Token` для всех write и action запросов.

Тело ответа также содержит:
- `csrf_token` — то же значение, что и CSRF cookie, для клиентов, которым удобнее читать из JSON.

При ошибке: `401 Unauthorized` с общим сообщением, независимо от того, существует email или нет.

После логина вызовите `GET /auth/me`, чтобы подтвердить сессию и получить identity и роли. Реальный уровень доступа зависит от назначенных пользователю ролей.

### CSRF

Cookie-аутентифицированные запросы к следующим write и action эндпоинтам требуют заголовок `X-CSRF-Token`:

- `POST /meetings/ingest`
- `POST /meetings/{id}/jobs/pipeline`
- `POST /meetings/{id}/jobs/{stage}`
- `POST /meetings/{id}/jobs/{job_id}/cancel`
- `POST /meetings/{id}/chat`
- `POST /chat`
- `POST /auth/logout`
- `POST /admin/users`
- `PATCH /admin/users/{user_id}`
- `POST /admin/users/{user_id}/disable`
- `POST /admin/users/{user_id}/enable`

```
X-CSRF-Token: <csrf_token>
```

Read-эндпоинты (все `GET`-маршруты, `POST /search`, `POST /auth/local/login`) CSRF **не требуют**.

Machine Bearer запросы освобождены от CSRF на всех маршрутах.

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

| Метод | Путь | Авторизация | CSRF | Примечания |
|---|---|---|---|---|
| POST | `/auth/local/login` | Нет | Нет | Возвращает session cookie + csrf_token |
| GET | `/auth/me` | Cookie-сессия | Нет | Identity, роли |
| POST | `/auth/logout` | Cookie + CSRF | **Да** | Отзывает сессию |

### Meetings (только чтение)

| Метод | Путь | Право | CSRF | Примечания |
|---|---|---|---|---|
| GET | `/meetings` | meetings.read | Нет | Постраничный список. Query params: `offset`, `limit` |
| GET | `/meetings/{id}` | meetings.read | Нет | Карточка встречи |
| GET | `/meetings/{id}/transcript` | transcripts.read | Нет | Транскрипт или `{"available": false}` |
| GET | `/meetings/{id}/artifacts` | artifacts.read | Нет | Список метаданных артефактов |
| GET | `/meetings/{id}/artifacts/{name}` | artifacts.read | Нет | Текстовый артефакт. 413 при превышении лимита. 415 для бинарных. |
| GET | `/meetings/{id}/transcript/segments` | transcripts.read | Нет | Нормализованные сегменты транскрипта |
| GET | `/meetings/{id}/media` | meetings.read | Нет | Безопасный список media-файлов |
| GET | `/meetings/{id}/media/{media_id}` | meetings.read | Нет | Стриминг media с поддержкой Range |
| GET | `/meetings/{id}/workspace` | meetings.read | Нет | Meeting Workspace UI |

Лимит текстового артефакта: **10 МиБ** (настраивается через `meetings.max_text_artifact_bytes`). Бинарные артефакты возвращают `415 Unsupported Media Type`.

### Ingest

| Метод | Путь | Право | CSRF | Примечания |
|---|---|---|---|---|
| POST | `/meetings/ingest` | meetings.upload | **Да** (cookie) | Multipart-загрузка. 201 или 409 при дубликате. |

### Job Pipeline

| Метод | Путь | Право | CSRF | Примечания |
|---|---|---|---|---|
| GET | `/meetings/{id}/jobs/stages` | jobs.read | Нет | Каталог запускаемых стадий |
| GET | `/meetings/{id}/pipeline/readiness` | jobs.read | Нет | Карта готовности стадий |
| POST | `/meetings/{id}/jobs/pipeline` | jobs.start | **Да** (cookie) | Запустить последовательный pipeline profile |
| POST | `/meetings/{id}/jobs/{stage}` | write access | **Да** (cookie) | Запустить стадию pipeline. Возвращает 202. |
| GET | `/meetings/{id}/jobs/{job_id}` | jobs.read | Нет | Статус задачи |
| POST | `/meetings/{id}/jobs/{job_id}/cancel` | write access | **Да** (cookie) | Отменить задачу |
| GET | `/jobs/active` | jobs.read | Нет | Текущая активная задача или `{}` |

### Поиск и чат

| Метод | Путь | Право | CSRF | Примечания |
|---|---|---|---|---|
| POST | `/search` | search.use | Нет | RAG-поиск. CSRF не требуется даже для cookie-клиентов. |
| POST | `/chat` | chat.use | **Да** (cookie) | Ответ с citations. Machine Bearer освобождён. |
| POST | `/meetings/{id}/search` | search.use | Нет | Поиск по чанкам конкретной встречи. |
| POST | `/meetings/{id}/chat` | chat.use | **Да** (cookie) | Q&A по конкретной встрече с citations. Machine Bearer освобождён. |

### Admin

#### Bootstrap

`POST /admin/bootstrap` создаёт первого администратора. Возвращает `409`, если пользователи уже существуют.

**Политика безопасности bootstrap** — эндпоинт применяет политику локальности, чтобы защитить пустые развёртывания:

| Источник запроса | Поведение по умолчанию | Как переопределить |
|---|---|---|
| **Localhost** (127.0.0.1, ::1) | Разрешён без секрета | Настройка не нужна |
| **Не-локальный** (LAN, контейнер, удалённо) | **Заблокирован** (возвращает 403) | Установите `allow_remote=true` + `secret` (см. ниже) |

Для не-локального bootstrap оператор должен явно включить его и предоставить одноразовый секрет:

1. Задайте переменные окружения (рекомендуется) или `auth.bootstrap` в `config.yaml`:
   ```
   MEETINGAGENT_BOOTSTRAP_ALLOW_REMOTE=true
   MEETINGAGENT_BOOTSTRAP_SECRET=<сильный-случайный-секрет>
   ```
   Секрет должен быть не короче 32 символов. Генерация:
   `python -c "import secrets; print(secrets.token_urlsafe(48))"`

2. Передайте секрет в заголовке `X-Bootstrap-Token`:
   ```
   POST /admin/bootstrap
   X-Bootstrap-Token: <секрет>
   Content-Type: application/json

   {"email": "admin@example.com", "password": "..."}
   ```

3. После создания первого администратора **удалите или сбросьте** `MEETINGAGENT_BOOTSTRAP_ALLOW_REMOTE` и `MEETINGAGENT_BOOTSTRAP_SECRET`. Секрет больше не нужен.

Секрет никогда не записывается в логи, аудит, не возвращается в ответах и не сохраняется. Определение IP использует адрес прямого пира — `X-Forwarded-For` не используется для идентификации клиента. Если в запросе присутствуют заголовки прокси (Forwarded, X-Forwarded-For), локальный bypass подавляется: запрос должен предоставить корректный `X-Bootstrap-Token`.

Bootstrap-эндпоинт:

| Метод | Путь | Auth | CSRF | Примечания |
|---|---|---|---|---|
| POST | `/admin/bootstrap` | Нет (+ проверка локальности) | Нет | Создать первого администратора. 409 если уже есть пользователи. 403 если заблокирован политикой. |

Управление пользователями (требует `users.manage` — cookie администратора):

| Метод | Путь | Auth | CSRF | Примечания |
|---|---|---|---|---|
| GET | `/admin/users` | users.manage | Нет | Список пользователей. Query: `offset`, `limit`. |
| GET | `/admin/users/{user_id}` | users.manage | Нет | Получить пользователя. |
| POST | `/admin/users` | users.manage | **Да** (cookie) | Создать пользователя. 409 при дублировании email. 422 при неизвестной роли. |
| PATCH | `/admin/users/{user_id}` | users.manage | **Да** (cookie) | Обновить имя и/или роли. 409 если последний admin понижен. |
| POST | `/admin/users/{user_id}/disable` | users.manage | **Да** (cookie) | Отключить пользователя. 409 если последний активный admin. |
| POST | `/admin/users/{user_id}/enable` | users.manage | **Да** (cookie) | Включить отключённого пользователя. |

Machine Bearer tokens не имеют `users.manage` и получают `403` на всех маршрутах управления пользователями.

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
| 401 | Unauthorized — нет учётных данных, неверный Bearer token или истёкшая сессия |
| 403 | Forbidden — аутентифицирован, но прав недостаточно; или CSRF отсутствует/неверен |
| 404 | Not Found |
| 409 | Conflict — дублирующийся файл при ingest (sha256); bootstrap отклонён (пользователи уже есть); защита последнего admin |
| 403 | Также: bootstrap заблокирован для не-локального запроса без `allow_remote`; bootstrap-токен отсутствует или неверен |
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

# Артефакт
Invoke-RestMethod `
  http://127.0.0.1:8000/meetings/2026-01-15__kickoff/artifacts/memo `
  -Headers $headers

# Загрузка файла встречи
$form = @{
  file  = Get-Item "C:\recordings\meeting.mp4"
  title = "Стартовая встреча"
  date  = "2026-01-15"
}
Invoke-RestMethod http://127.0.0.1:8000/meetings/ingest `
  -Method Post -Headers $headers -Form $form

# Запуск транскрибации
Invoke-RestMethod `
  http://127.0.0.1:8000/meetings/2026-01-15__kickoff/jobs/transcribe `
  -Method Post -Headers $headers

# Статус задачи
Invoke-RestMethod `
  http://127.0.0.1:8000/meetings/2026-01-15__kickoff/jobs/<job_id> `
  -Headers $headers

# Отмена задачи
Invoke-RestMethod `
  http://127.0.0.1:8000/meetings/2026-01-15__kickoff/jobs/<job_id>/cancel `
  -Method Post -Headers $headers

# Активная задача
Invoke-RestMethod http://127.0.0.1:8000/jobs/active -Headers $headers

# Поиск
$body = @{ query = "риски проекта" } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/search `
  -Method Post -Headers $headers `
  -ContentType "application/json" -Body $body

# Чат
$body = @{ query = "итоги встречи" } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/chat `
  -Method Post -Headers $headers `
  -ContentType "application/json" -Body $body
```

### PowerShell — Браузерная сессия (Cookie + CSRF)

```powershell
$base = "http://127.0.0.1:8000"
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession

# Логин
$loginBody = @{ email = "user@example.com"; password = "secret" } | ConvertTo-Json
$loginResp = Invoke-RestMethod "$base/auth/local/login" `
  -Method Post -WebSession $session `
  -ContentType "application/json" -Body $loginBody
$csrf = $loginResp.csrf_token

# Чтение (CSRF не нужен для GET)
Invoke-RestMethod "$base/meetings" -WebSession $session

# Запись (нужен CSRF)
$form = @{
  file  = Get-Item "C:\recordings\meeting.mp4"
  title = "Стартовая встреча"
  date  = "2026-01-15"
}
Invoke-RestMethod "$base/meetings/ingest" `
  -Method Post -WebSession $session `
  -Headers @{ "X-CSRF-Token" = $csrf } -Form $form

# Чат (нужен CSRF для cookie-клиентов)
$body = @{ query = "итоги встречи" } | ConvertTo-Json
Invoke-RestMethod "$base/chat" `
  -Method Post -WebSession $session `
  -Headers @{ "X-CSRF-Token" = $csrf } `
  -ContentType "application/json" -Body $body

# Выход
Invoke-RestMethod "$base/auth/logout" `
  -Method Post -WebSession $session `
  -Headers @{ "X-CSRF-Token" = $csrf }
```

### curl — Machine Bearer

```bash
TOKEN="your-api-token"

# Список встреч
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/meetings

# Транскрипт
curl -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/meetings/2026-01-15__kickoff/transcript

# Артефакт
curl -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/meetings/2026-01-15__kickoff/artifacts/memo

# Загрузка
curl -X POST http://127.0.0.1:8000/meetings/ingest \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/path/to/meeting.mp4" \
  -F "title=Стартовая встреча" \
  -F "date=2026-01-15"

# Запуск задачи
curl -X POST http://127.0.0.1:8000/meetings/2026-01-15__kickoff/jobs/transcribe \
  -H "Authorization: Bearer $TOKEN"

# Статус задачи
curl -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/meetings/2026-01-15__kickoff/jobs/<job_id>

# Отмена задачи
curl -X POST \
  http://127.0.0.1:8000/meetings/2026-01-15__kickoff/jobs/<job_id>/cancel \
  -H "Authorization: Bearer $TOKEN"

# Поиск
curl -X POST http://127.0.0.1:8000/search \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "риски проекта"}'

# Чат
curl -X POST http://127.0.0.1:8000/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "итоги встречи"}'
```

### curl — Браузерная сессия (Cookie + CSRF)

```bash
BASE=http://127.0.0.1:8000

# Логин — сохраняем cookies; получаем csrf_token из ответа
RESP=$(curl -s -c cookies.txt -X POST "$BASE/auth/local/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"secret"}')
CSRF=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['csrf_token'])")

# Чтение (CSRF не нужен для GET)
curl -b cookies.txt "$BASE/meetings"

# Запись (нужен CSRF)
curl -b cookies.txt -X POST "$BASE/meetings/ingest" \
  -H "X-CSRF-Token: $CSRF" \
  -F "file=@meeting.mp4" -F "title=Тест" -F "date=2026-01-15"

# Чат (нужен CSRF для cookie-клиентов)
curl -b cookies.txt -X POST "$BASE/chat" \
  -H "X-CSRF-Token: $CSRF" \
  -H "Content-Type: application/json" \
  -d '{"query": "итоги встречи"}'

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
paths:
  auth_db: "data/meetingagent/auth.db"   # по умолчанию; можно переопределить

auth:
  session_ttl_seconds: 86400             # 24 ч по умолчанию
  cookie_name: "ma_session"              # по умолчанию
  cookie_secure: "auto"                  # auto|true|false; auto=Secure при HTTPS

  # Безопасность bootstrap (опционально — нужно только для не-локального первого запуска).
  # bootstrap:
  #   allow_remote: false                # по умолчанию; true только для не-локального bootstrap
  #   secret: ""                         # обязательно при allow_remote: true

  login_throttle:
    enabled: true
    max_failures: 5
    window_seconds: 300
    block_seconds: 900
    max_entries: 10000
    trusted_proxy_cidrs: []

meetings:
  max_text_artifact_bytes: 10485760      # 10 МиБ
```

Переменные окружения для bootstrap (переопределяют config.yaml):

| Переменная | Значения | Примечания |
|---|---|---|
| `MEETINGAGENT_BOOTSTRAP_ALLOW_REMOTE` | `true` / `false` | По умолчанию: `false`. Установите `true`, чтобы разрешить не-локальный bootstrap. |
| `MEETINGAGENT_BOOTSTRAP_SECRET` | строка, мин. 32 символа | Обязательно при `allow_remote: true`. Не коммитить. |

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

Cookies устанавливаются с атрибутом `Secure` только если запрос пришёл по HTTPS (`cookie_secure: auto`). Задайте `cookie_secure: true`, чтобы принудительно включить `Secure`, или `false` для отключения (только разработка). В продакшене используйте HTTPS.

### Доверенные прокси-серверы для cookie_secure=auto

При `cookie_secure: auto` API определяет, пришёл ли запрос по HTTPS, проверяя заголовок `X-Forwarded-Proto` — но **только если запрос пришёл с доверенного IP прокси**. Заголовок от недоверенных клиентов игнорируется.

Настройте доверенные прокси-подсети через переменную окружения или конфиг:

```text
MEETINGAGENT_TRUSTED_PROXY_CIDRS=127.0.0.1/32,10.0.0.0/8
```

Или в `config.yaml`:

```yaml
security:
  trusted_proxy_cidrs:
    - "127.0.0.1/32"
    - "10.0.0.0/8"
```

Без `trusted_proxy_cidrs` (пустой список по умолчанию) `X-Forwarded-Proto` игнорируется от всех клиентов, а флаг Secure устанавливается только по прямому соединению. Это безопасный дефолт для хоста напрямую открытого в интернет. Deployment safety validator предупреждает, если `cookie_secure: auto` включён без trusted_proxy_cidrs в режиме `self_hosted`.

### Требования к секретам

`MEETINGAGENT_API_TOKEN` и `MEETINGAGENT_BOOTSTRAP_SECRET` должны быть высокоэнтропийными секретами. Deployment safety validator отклоняет:

- Пустые значения или слишком короткие (минимум 32 символа).
- Однотипный повтор символа (например, `aaaa...`).
- Повтор коротких блоков (например, `abcabc...`, `token-token-token...`).
- Известные placeholder-слова (например, `changeme`, `example`, `placeholder`).

Сгенерируйте надёжный токен:

```powershell
# PowerShell
[Convert]::ToBase64String((1..48 | ForEach-Object { Get-Random -Maximum 256 }))
```

```bash
# bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

---

## Безопасное хранение

| Данные | Где хранить | Никогда не делать |
|---|---|---|
| `MEETINGAGENT_API_TOKEN` | `.env` (не коммитить) или системное окружение | Коммитить в Git |
| `config.yaml` | Только локально, в gitignore | Коммитить в Git |
| `data/meetingagent/auth.db` (SQLite авторизация) | Только локально, в gitignore | Коммитить в Git |
| `meetings/` | Только локально, в gitignore | Коммитить в Git |
| `logs/` | Только локально, в gitignore | Коммитить в Git |
| `data/` (индексы, чанки) | Только локально, в gitignore | Коммитить в Git |

Генерация сильного токена:

```powershell
# PowerShell (кроссплатформенный вариант через Python — без проблем со спецсимволами)
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

```bash
# bash / Linux / macOS
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
# или
openssl rand -hex 32
```

---

## Ограничения и дорожная карта

| Функция | Статус |
|---|---|
| Machine Bearer token | **Работает** |
| Локальный логин (cookie-сессия) | **Работает** |
| Первичная регистрация администратора (`POST /admin/bootstrap`) | **Работает** |
| Admin user API (`/admin/users`) | **Работает** |
| Валидация безопасности деплоя | **Работает** — `MEETINGAGENT_DEPLOYMENT_MODE`, startup-валидатор, `GET /admin/security/status` |
| Admin UI | **Не реализован** — используйте admin API напрямую |
| Чат в Web UI (браузер) | **Работает** — local login + CSRF token flow |
| Yandex ID / Google / OIDC | **Не реализованы** |
| Публичная регистрация | **Не планируется в MVP** |
| Per-user API tokens | **Не реализованы** |
| Сброс пароля | **Не реализован** |

---

## Безопасность деплоя

### Режим деплоя

Установите `MEETINGAGENT_DEPLOYMENT_MODE` для управления валидацией при старте:

| Режим | Описание |
|---|---|
| `local` (по умолчанию) | Локальная разработка. Слабая конфигурация даёт **warnings**, но не блокирует старт. |
| `self_hosted` | LAN или интернет. Отсутствие/слабость обязательных настроек даёт **error** и **прерывает старт**. |

```bash
# .env — self-hosted деплой
MEETINGAGENT_DEPLOYMENT_MODE=self_hosted
MEETINGAGENT_API_TOKEN=<сгенерируйте: python -c "import secrets; print(secrets.token_urlsafe(48))">
```

### Что проверяется при старте

| Код нарушения | Что проверяется | Severity в self_hosted |
|---|---|---|
| `deployment_mode_unknown` | Неизвестное значение `MEETINGAGENT_DEPLOYMENT_MODE` | error |
| `machine_token_missing` | `MEETINGAGENT_API_TOKEN` не задан | error |
| `machine_token_weak` | `MEETINGAGENT_API_TOKEN` недостаточно надёжен: слишком короткий, похож на placeholder, повтор одного символа или повтор короткого блока | error |
| `session_cookie_insecure` | `auth.cookie_secure = false` в конфиге | error |
| `cors_wildcard_self_hosted` | Не настроены `security.allowed_hosts` или `security.allowed_origins` | warning |
| `bootstrap_policy_unsafe` | `allow_remote=true` без надёжного bootstrap-секрета | error |
| `trusted_proxy_no_cidrs` | `cookie_secure: auto` задан без `trusted_proxy_cidrs` | warning |
| `invalid_trusted_proxy_cidrs` | Одно или несколько значений `trusted_proxy_cidrs` не является валидным CIDR | error |

В режиме `local` те же проверки дают `warning` или `info` и не прерывают старт.

### Чеклист для self-hosted деплоя

1. Установите `MEETINGAGENT_DEPLOYMENT_MODE=self_hosted` в `.env`.
2. Установите надёжный токен: `MEETINGAGENT_API_TOKEN=<случайная строка ≥ 32 символов>`.
3. Установите `auth.cookie_secure: auto` или `true` в `config.yaml` (не `false`).
4. Настройте `security.allowed_hosts` / `security.allowed_origins` в `config.yaml` или убедитесь, что reverse proxy ограничивает допустимые хосты/источники.
5. Используйте HTTPS или доверенный reverse proxy для всего браузерного доступа.
6. Запустите bootstrap первого администратора через локальный путь или используйте `MEETINGAGENT_BOOTSTRAP_SECRET`.
7. Убедитесь, что `.env` не зафиксирован в VCS (он в `.gitignore`).
8. Запустите `pytest tests/asu_june_bot/auth -q` — убедитесь, что тесты безопасности проходят.

### Endpoint статуса безопасности

```
GET /admin/security/status
```

Требует браузерную сессию администратора (`users.manage`). Machine Bearer токены запрещены для этого endpoint-а.

Возвращает режим деплоя и очищенные от секретов нарушения. **Никогда** не включает значения токенов, хэши токенов, идентификаторы сессий или пути файловой системы.

### Типы principals и что они могут

- **Machine Bearer token** (`MEETINGAGENT_API_TOKEN`) — для скриптов, CI, межсервисных вызовов. Не является паролем администратора в браузере. Machine-токены не могут управлять пользователями браузера (`/admin/users`, `/admin/security/status`).
- **Браузерная сессия** (`ma_session` cookie) — для операторов в web UI. Запросы, изменяющие состояние, требуют CSRF-токен (заголовок `X-CSRF-Token`).

Это разные principals. Корректная cookie-сессия **не компенсирует** неверный Bearer-токен — неверные credentials всегда возвращают 401.

### Безопасность cookie и сессий

| Свойство | Значение |
|---|---|
| Имя cookie | `ma_session` (настраивается) |
| HttpOnly | Да — JavaScript не может прочитать cookie сессии |
| SameSite | `Lax` |
| Флаг Secure | Управляется `auth.cookie_secure` (`auto` / `true` / `false`; по умолчанию `auto`) |
| TTL сессии | 24 часа (настраивается через `auth.session_ttl_seconds`) |
| Хранилище | Серверное (SQLite); хранится только хэш токена — plaintext не сохраняется |
| CSRF | non-HttpOnly cookie `ma_session_csrf`; значение передаётся в заголовке `X-CSRF-Token` |

### Контроль хостов и источников

MeetingAgent не включает встроенный CORS или TrustedHost middleware. Для self-hosted деплоев ограничения хостов/источников должны обеспечиваться reverse proxy (nginx, Caddy и т.п.) перед приложением.

Чтобы убрать warning `cors_wildcard_self_hosted`, задайте явные списки в `config.yaml`:

```yaml
security:
  allowed_hosts:
    - meetingagent.internal
  allowed_origins:
    - https://meetingagent.internal
```

Эти значения в текущей реализации используются только в валидаторе нарушений. Применение middleware — элемент roadmap.
