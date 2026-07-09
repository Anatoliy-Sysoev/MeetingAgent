# Transcript anonymization

Локальная анонимизация нужна перед публикацией примеров, eval fixtures или фрагментов транскриптов. Это вспомогательный safety workflow, а не гарантия полной деидентификации.

## Входы

Поддерживаются:

```powershell
python scripts/43_anonymize_transcript.py --input path\segments.jsonl
python scripts/43_anonymize_transcript.py --input path\transcript.md
python scripts/43_anonymize_transcript.py --meeting-dir meetings\2026-01-15__demo
```

Для meeting card команда по умолчанию берёт `transcript/segments.jsonl` из `meeting.json.artifacts.segments` и пишет в:

```text
transcript/anonymized/
  anonymized_segments.jsonl
  anonymization_report.json
```

Markdown input пишет `anonymized_transcript.md`.

## Что заменяется

Эвристики заменяют найденные значения на явные маркеры:

```text
[PERSON_001]
[ORG_001]
[PATH_001]
[URL_001]
[EMAIL_001]
[PHONE_001]
[ID_001]
```

Автоматически обрабатываются:

- email;
- URL;
- Windows/Unix пути;
- телефоны;
- legal-form organization names типа `ООО ...`;
- русскоязычные ФИО эвристикой;
- внутренние идентификаторы вида `FTT-MA-08`.

Если указан `--meeting-dir`, имена из `meeting.json.speaker_mapping` также добавляются как person terms. Технические labels (`SPEAKER_01`, `segment_id`, `utterance_id`, `chunk_id`) сохраняются, чтобы таймкоды и ссылки не ломались. Если в `speaker`, `speakers` или `source` попали реальные имена или локальные пути, они анонимизируются; без обработки остаются только технические speaker labels и audio-source labels `MIX`/`MIC`/`SYS`.

## Custom terms

Добавить точные термины можно через repeatable CLI:

```powershell
python scripts/43_anonymize_transcript.py `
  --input transcript\segments.jsonl `
  --term person="Иван Петров" `
  --term org="НОВАТЭК" `
  --term identifier="Паспорт проекта"
```

Или через JSON file:

```json
{
  "person": ["Иван Петров"],
  "org": ["НОВАТЭК"],
  "identifier": ["Паспорт проекта"]
}
```

```powershell
python scripts/43_anonymize_transcript.py --input transcript\segments.jsonl --terms-file terms.json
```

Поддерживаемые ключи: `person`, `org`, `path`, `url`, `email`, `phone`, `identifier`.

## Reports

`anonymization_report.json` public-safe: он содержит только placeholder, kind и count. Исходные значения и их hashes в public report не пишутся, потому что unsalted hashes для email/телефонов/ФИО могут быть обратимы по словарю.

Если нужен локальный trace для ручной проверки, включите:

```powershell
python scripts/43_anonymize_transcript.py --input transcript\segments.jsonl --write-private-map
```

Это создаст `anonymization_mapping.private.json` с оригинальными значениями и `original_sha256`. Файл приватный, не публикуется и игнорируется Git через `*.private.json`.

## Safety limits

- Эвристики могут пропустить редкие имена, названия без legal form, внутренние термины и customer-specific сокращения.
- Эвристики могут дать false positive на обычные заголовки или проектные термины.
- Перед публикацией нужен ручной просмотр anonymized output и report.
- Не публикуйте private mapping.
- Реальные `meetings/`, `data/`, `logs/`, raw transcripts и ASR outputs остаются runtime data и не коммитятся.
