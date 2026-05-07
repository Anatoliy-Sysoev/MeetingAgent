# Контекст Проекта

Обновлено: 2026-05-07.

## Текущее Состояние

MeetingAgent - приватный GitHub-backed пет-проект и локальный продуктовый репозиторий.

Репозиторий:

- Локальный путь: `%USERPROFILE%\Desktop\AI\MeetingAgent`
- Remote: `https://github.com/Anatoliy-Sysoev/MeetingAgent`
- Видимость: private
- Ветка: `main`

Продуктовое направление: local-first агент памяти проекта.

Основные сценарии:

- RAG по проектной документации;
- транскрибация встреч;
- генерация memo и протоколов;
- классификация по этапу проекта, ФТТ, задаче и документу;
- генерация документов на основе цитируемых проектных источников.

## Рабочий Статус

Основной RAG-corpus локально собран: текущие `data/chunks.jsonl` дают 5207 chunks после исключения архивов, черновиков и служебных JSON-копий. `data/embeddings_cache.jsonl` содержит валидные `bge-m3` embeddings для всех текущих chunks и сохраняет stale-записи для ранее удаленных/исключенных chunks.

ChromaDB больше не считается стабильным поисковым слоем: локально наблюдалась ошибка загрузки HNSW-индекса. Для критического пути поиска используется отдельный numpy-индекс в `data/numpy_index`.

Важные runtime-факты:

- `run_full_rag.ps1` запускает полную сборку.
- `scripts/03_build_index.py` - долгий шаг создания chunks и пополнения embeddings cache.
- `data/embeddings_cache.jsonl` - resumable cache embeddings.
- `scripts/05_build_numpy_index.py` - сборка стабильного numpy-поиска из готовых chunks и embeddings cache.
- `data/numpy_index` - локальный numpy-индекс, игнорируется Git.
- `monitor_rag.ps1` - один тик мониторинга.
- Локальные рабочие папки игнорируются Git.

## Важные Файлы

- `README.md`: обзор продукта и запуск.
- `AGENTS.md`: инструкции для Codex/AI.
- `docs/context.md`: текущее состояние проекта.
- `docs/decisions.md`: почему приняты ключевые решения.
- `docs/todo.md`: следующие шаги.
- `.env.example`: безопасный пример переменных окружения.
- `config.example.yaml`: безопасный пример локальной конфигурации.
- `scripts/03_build_index.py`: worker для embeddings/indexing.
- `scripts/05_build_numpy_index.py`: сборщик локального numpy-индекса.
- `scripts/04_query.py`: запросы к RAG через numpy-индекс.
- `monitor_rag.ps1`: мониторинг долгой RAG-сборки.
- `docs/product/PROJECT_STAGES_AND_FTT.md`: рабочая карта этапов продукта, ФТТ и критериев приемки.
- `docs/product/PROJECT_TAXONOMY.md`: единый реестр этапов проекта и типов документов.
- `docs/glossary.md`: словарь терминов и заготовка `initial_prompt` для транскрибации.
- `docs/operations/BACKUP_AND_RETENTION.md`: правила backup, восстановления и хранения медиа.
- `docs/quality/rag_eval_questions.md`: стартовый набор вопросов для baseline качества RAG.
- `docs/references/WHISPERDESK_EXPERIMENT.md`: что берем из эксперимента WhisperDesk для live-транскрибации.

## Что Изменилось Недавно

- Создана продуктовая структура репозитория.
- Создан и запушен приватный GitHub-репозиторий.
- Локальные рабочие данные исключены из Git.
- Мониторинг усилен для работы с Ollama и живым Python build-процессом.
- В `scripts/03_build_index.py` сохранены reusable `chunk_id` и совместимый `db_id`, но запись в ChromaDB убрана из основного build-пути.
- Добавлены стандартные файлы пет-проекта: `AGENTS.md`, `docs/context.md`, `docs/decisions.md`, `docs/todo.md` и `.env.example`.
- Основная документация переведена на русский язык как основной язык проекта.
- Добавлен подробный продуктовый документ `docs/product/PRODUCT_VISION_AND_PLAN.md`: видение, модули, сценарии, roadmap и адаптация идей Speakr.
- Добавлен план параллельных работ `docs/product/PARALLEL_WORK_WHILE_RAG_BUILDS.md`, чтобы развивать продукт, пока текущая RAG-сборка продолжается.
- Добавлен отдельный стабильный локальный RAG-поиск на numpy: `scripts/rag_numpy_backend.py` и `scripts/05_build_numpy_index.py`.
- `scripts/04_query.py` переведен на numpy-поиск по умолчанию и больше не зависит от ChromaDB для обычного поиска.
- `run_full_rag.ps1` теперь после build/indexing запускает сборку `05_build_numpy_index`.
- Ранний smoke-поиск numpy прошел на корпусе 9575 chunks; после чистки корпуса актуальный индекс пересобран на 5207 chunks.
- `vector_db/` полностью исключен из Git как устаревшая локальная папка ChromaDB, чтобы rebuild не удалял tracked-заглушки.
- `monitor_rag.ps1` получил более устойчивое определение процессов через CIM fallback и lock PID fallback.
- Добавлен документ `docs/product/PROJECT_STAGES_AND_FTT.md`: этапы разработки MeetingAgent, ФТТ продукта, предметные этапы проекта АСУ и ближайший маршрут выполнения.
- Добавлен документ `docs/references/WHISPERDESK_EXPERIMENT.md`: WhisperDesk зафиксирован как экспериментальный референс для live-транскрибации, но не как продуктовый код.
- Добавлены `docs/glossary.md`, `docs/product/PROJECT_TAXONOMY.md`, `docs/operations/BACKUP_AND_RETENTION.md` и `docs/quality/rag_eval_questions.md`.
- `scripts/04_query.py` получил компактный вывод источников, `score` и JSON-обертку для evaluation.
- `scripts/03_build_index.py` больше не пересоздает `vector_db/`; после него `run_full_rag.ps1` собирает numpy-индекс через `scripts/05_build_numpy_index.py`.
- `RAG_AUTOMATION_INSTRUCTION.md` переписан под актуальный numpy-поток и больше не описывает ChromaDB как рабочий путь.
- `config.example.yaml` дополнен настройками генерации и live-транскрибации.
- Добавлен `docs/quality/rag_eval_report_template.md` для исторических срезов качества RAG.
- Выполнен первый baseline-прогон `FTT-MA-07` по 10 вопросам и сохранен в `docs/quality/rag_eval_baseline_2026-05-07.md`.
- В `docs/decisions.md` добавлены решения про контракт вывода `04_query.py` и политику ротации медиа.
- Добавлена гигиена корпуса RAG: `exclude_path_patterns` исключают `Архив`, `Черновики и шаблоны`, backup-папки и служебные `_analysis/docx_json*`, но оставляют curated `_analysis/*.md`.
- `scripts/04_query.py` и numpy backend теперь по умолчанию фильтруют исключенные пути и дедуплицируют одинаковые chunks по тексту; для диагностики есть `--include-excluded` и `--no-dedupe`.
- `run_full_rag.ps1` и `monitor_rag.ps1` настроены на UTF-8 вывод; `monitor_rag.ps1` больше не считает старый done-маркер завершением, если жив текущий wrapper/build.
- После чистки корпуса RAG пересобран: `data/numpy_index` содержит 5207 chunks, свежий done-маркер `full_rag_2026-05-07_17-16-38.done.txt`, failed-маркеров нет.

## Что Осталось

- Допрогнать вопросы 11-15 из `docs/quality/rag_eval_questions.md`.
- Принять отдельное решение по порогу приемки качества поиска после полного baseline.
- Перезапустить полный baseline `FTT-MA-07` на очищенном корпусе, потому что старый baseline отражает грязную выдачу с архивами и JSON-дублями.
- Оценить, нужно ли добавлять BM25-гибрид или метаданные-фильтры для системных экспортов, если HTML/TXT-страницы админки продолжают вытеснять проектные документы.
- Использовать `docs/product/PROJECT_STAGES_AND_FTT.md` как основной рабочий чек-лист.
- Спроектировать карточку встречи и live-сессию вокруг `FTT-MA-09`, `FTT-MA-10` и `FTT-MA-11`.
- Добавить инкрементальное обновление RAG.
- Собрать первый pipeline обработки встреч.
- Опционально подключить FAISS как ускорение поверх того же контракта поиска, если понадобится скорость на большем корпусе.

## Восстановление Контекста В Новом Треде

Используй prompt:

```text
Прочитай README.md, AGENTS.md, docs/context.md, docs/todo.md и git log --oneline -10. Восстанови контекст проекта и предложи следующий шаг.
```
