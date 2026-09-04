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

Если указан `--meeting-dir`, имена из `meeting.json.speaker_mapping` также
добавляются как person terms. Технические speaker labels (`SPEAKER_01`,
`SPEAKER_UNKNOWN`), source labels (`MIC`, `SYS`, `MIX`) и идентификаторы
`segment_id`/`utterance_id`/`chunk_id` сохраняются, чтобы таймкоды и ссылки не
ломались. Любые другие значения в `speaker`, `speakers[]` и `source` проходят
обычную анонимизацию и не считаются безопасными метаданными.

## Custom terms

Добавить точные термины можно через repeatable CLI:

```powershell
python scripts/43_anonymize_transcript.py `
  --input transcript\segments.jsonl `
  --term person="Иван Петров" `
  --term org="АльфаСофт" `
  --term identifier="Паспорт проекта"
```

Или через JSON file:

```json
{
  "person": ["Иван Петров"],
  "org": ["АльфаСофт"],
  "identifier": ["Паспорт проекта"]
}
```

```powershell
python scripts/43_anonymize_transcript.py --input transcript\segments.jsonl --terms-file terms.json
```

Поддерживаемые ключи: `person`, `org`, `path`, `url`, `email`, `phone`, `identifier`.

## Reports

`anonymization_report.json` public-safe: он содержит только placeholder, kind и
count. В нём нет исходных значений и воспроизводимых hashes исходных значений.

Если нужен локальный trace для ручной проверки, включите:

```powershell
python scripts/43_anonymize_transcript.py --input transcript\segments.jsonl --write-private-map
```

Это создаст `anonymization_mapping.private.json` с оригинальными значениями и
их SHA-256 для локальной сверки. Файл приватный, не публикуется и игнорируется
Git через `*.private.json`.

## Safety limits

- Эвристики могут пропустить редкие имена, названия без legal form, внутренние термины и customer-specific сокращения.
- Эвристики могут дать false positive на обычные заголовки или проектные термины.
- Перед публикацией нужен ручной просмотр anonymized output и report.
- Не публикуйте private mapping.
- Реальные `meetings/`, `data/`, `logs/`, raw transcripts и ASR outputs остаются runtime data и не коммитятся.
