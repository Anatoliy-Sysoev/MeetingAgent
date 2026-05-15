# 08. Дорожная Карта и Этапы Релизов

Обновлено: 2026-05-15.

## Принцип Roadmap

Roadmap строится не вокруг "хочется еще одну AI-фичу", а вокруг последовательного усиления продукта:

1. сначала надежный corpus;
2. потом надежный retrieval;
3. потом API;
4. потом chat;
5. потом привычный пользовательский интерфейс;
6. потом более глубокая аналитика и память встреч.

## Этапы Продукта

## P0. Product Foundation

Цель:

- отделить `Asu June Bot` как самостоятельный продуктовый контур;
- описать vision, scope, roadmap, MVP и требования.

Артефакты:

- подпроектная документация;
- product package;
- decisions;
- tech architecture;
- runbook.

Статус: выполнено частично, продолжается синхронизация с реализацией.

## P1. Reliable Search Product Core

Цель:

- собрать очищенный project-only corpus;
- построить retrieval core;
- зафиксировать search quality;
- поставить guard перед retrieval.

Состав:

- extraction/chunking v2.1;
- embeddings/index v2;
- search quality v2.2;
- ProjectGuard v2.

Статус: по сути выполнено.

## P2. Search API MVP

Цель:

- сделать reusable API-слой поверх уже готового retrieval core.

Состав:

- `GET /health`;
- `POST /search`;
- единый SearchService;
- smoke-команды;
- API smoke report.

Критерий готовности:

- проектные запросы возвращают context и results;
- `refused` и `clarify` не вызывают retrieval;
- формат ответа стабилен для будущего UI и chat.

## P3. Chat API MVP

Цель:

- добавить project-only chat поверх уже подготовленного context.

Состав:

- `POST /chat`;
- prompt builder;
- answer generator;
- answer validator;
- response formatter.

Правило:

- не отправлять raw top-k напрямую в LLM;
- чат опирается только на curated context.

## P4. Team Adoption Surface

Цель:

- дать удобную точку входа для повседневного использования.

Состав:

- web panel / Open WebUI поверх локального API;
- понятный search/chat UX;
- стандартизированный ответ с источниками;
- ready-to-use сценарии для команды.

## P5. Cross-Document Analyst Mode

Цель:

- перейти от "найди ответ" к "сопоставь артефакты и объясни расхождения".

Состав:

- traceability между ФТТ, ПМИ, ЦТА, ПР, СоИ;
- document comparison;
- analyst flows;
- richer diagnostics.

## P6. Meeting Memory Integration

Цель:

- связать продуктовую память документов с памятью встреч.

Состав:

- подключение meeting artifacts;
- влияние встреч на проектный контекст;
- поиск по решениям, задачам, рискам;
- later linkage between discussion and formal docs.

## P7. Enterprise Readiness

Цель:

- подготовить продукт к более широкой эксплуатации, если это потребуется.

Состав:

- более сильный storage layer;
- richer auth/policy;
- deployment profiles;
- optional multi-user mode;
- performance hardening.

## Релизы

### Release 0.1

Надежный локальный search core.

### Release 0.2

API Search MVP.

### Release 0.3

Project-only Chat MVP.

### Release 0.4

Удобная рабочая оболочка для ежедневного использования.

## Что Не Должно Сломать Roadmap

- ранний уход в UI раньше стабильного API;
- ранняя замена ядра на тяжелую внешнюю платформу;
- попытка добавить "все и сразу";
- смешивание MeetingAgent и Asu June Bot в один неразделенный runtime;
- подмена продуктовой пользы красивой демонстрацией модели.

## Как Понимать Приоритеты

Приоритет выше у того, что:

1. повышает надежность;
2. повышает проверяемость;
3. сокращает рабочее время пользователя;
4. делает следующий слой продукта возможным.

Поэтому порядок:

```text
Search -> API -> Chat -> UI -> Traceability -> Meeting Integration
```

является не случайным, а архитектурно и продуктово обоснованным.
