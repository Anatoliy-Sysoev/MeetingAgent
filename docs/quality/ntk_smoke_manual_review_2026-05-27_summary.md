# Manual source-supported review - smoke_eval_hybrid_after_markers_v3

## Summary

- total: 20
- strict source-supported pass: 18/20
- pass: 18
- partial: 2
- fail: 0

## Decision

Strict pass is 18/20. The threshold >=18/20 is met. NTK corpus can be enabled behind a feature flag, not as unconditional global default.

## Partial / follow-up cases

### NTK-SMOKE-012
Query: Какие группы AD app_ccpm используются для ролей строительного контроля?

Verdict: partial

Note: top-1/top-2 СоИ AD и source_url есть; источники подтверждают наличие справочника групп AD и атрибута groups. Но для полного ответа по конкретным app_ccpm-группам/ролям нужен контроль, что в top-N попадает таблица соответствия групп AD и ролей, а не только общая строка справочника.

### NTK-SMOKE-017
Query: Какие регламенты ведения объектов НСИ есть в корпусе?

Verdict: partial

Note: top-1..top-4 Реестр НСИ; источник подтверждает наличие реестров НСИ. Но формулировка про регламенты ведения объектов НСИ может требовать маршрутизации также в МВД/регламентные документы, поэтому это source-supported частично.

## Full review table

- NTK-SMOKE-001: pass - top-1/top-2 ФТТ.docx, section 4.1; источники напрямую соответствуют требованию 4.1 по инспекционным документам.
- NTK-SMOKE-002: pass - top-1 ФТТ.docx, section 4.2; далее ПР как supporting. Источник достаточен для перечисления функций СК.
- NTK-SMOKE-003: pass - top-1/top-2 ФТТ.docx, section 4.2.5; supporting ПМИ. Источник напрямую соответствует вопросу про связку актов/предписаний/НОВАДОК.
- NTK-SMOKE-004: pass - top-1/top-2 ФТТ.docx, section 10.8; несколько ФТТ-источников в top-5. Достаточно для performance 2520/600.
- NTK-SMOKE-005: pass - top-5 полностью ЦТА, section 1.4; вопрос про PostgreSQL/MinIO/Kubernetes корректно маршрутизирован в архитектуру.
- NTK-SMOKE-006: pass - top-5 полностью ЦТА; источники по логированию/Grafana Loki/SIEM находятся в архитектурном документе.
- NTK-SMOKE-007: pass - top-5 ЦТА, section 1.4; запрос RTO/RPO больше не уходит в clarify, источники архитектурного типа.
- NTK-SMOKE-008: pass - top-5 ПР; источники по статусам замечаний СК и процессным строкам ПР.
- NTK-SMOKE-009: pass - top-5 ПР, section 4.1; источники по автоматически формируемым документам после инспекционной проверки.
- NTK-SMOKE-010: pass - top-5 ПР; источники по ролям модуля строительного контроля.
- NTK-SMOKE-011: pass - top-5 СоИ AD; источники по синхронизации учетных записей, групп и LDAPS.
- NTK-SMOKE-012: partial - top-1/top-2 СоИ AD и source_url есть; источники подтверждают наличие справочника групп AD и атрибута groups. Но для полного ответа по конкретным app_ccpm-группам/ролям нужен контроль, что в top-N попадает таблица соответствия групп AD и ролей, а не только общая строка справочника.
- NTK-SMOKE-013: pass - top-1 СоИ Справочники; query про Bearer Token/MDR/НСИ попадает в нужный документ, несмотря на supporting СоИ AD ниже.
- NTK-SMOKE-014: pass - top-5 СоИ Справочники; источники по полям справочников MDR, полному срезу и дельте.
- NTK-SMOKE-015: pass - top-1 ПМИ section 4.3; supporting ЦТА/ФТТ/ПР допустимы, но основной источник правильный.
- NTK-SMOKE-016: pass - top-5 Паспорт ИС; guard больше не отказывает, источники по связанным документам/составу паспорта.
- NTK-SMOKE-017: partial - top-1..top-4 Реестр НСИ; источник подтверждает наличие реестров НСИ. Но формулировка про регламенты ведения объектов НСИ может требовать маршрутизации также в МВД/регламентные документы, поэтому это source-supported частично.
- NTK-SMOKE-018: pass - top-5 ФТТ, включая section 10.8; источники достаточны для ограничений экспорта PDF/Excel/CSV.
- NTK-SMOKE-019: pass - top-5 ЦТА; источники архитектурного типа по SIEM/событиям безопасности.
- NTK-SMOKE-020: pass - out-of-scope запрос корректно refused; source support не требуется, guard behavior корректен.
