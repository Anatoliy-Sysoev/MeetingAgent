# NTK realistic 500 v3 guard-only baseline

Дата: 2026-06-04

Назначение: дешёвый baseline только через ProjectGuard.evaluate_v2(), без retrieval, embeddings и LLM.

Dataset: `docs\quality\ntk_realistic_500_v3_queries_2026-06-03.jsonl`
Report: `docs\quality\ntk_realistic_500_v3_guard_only_report_2026-06-04_p0_harmful.jsonl`

## Summary

- total: 500
- ok: 419
- false_clarify_project: 65
- false_clarify_boundary: 16

## Actual Status Counts

- ok: 385
- clarify: 81
- refused: 34

## Action By Scope

- harmful_security: {'refused': 20}
- out_of_scope: {'clarify': 16, 'refused': 14}
- project: {'ok': 385, 'clarify': 65}

## Verdict By Scope

- harmful_security: {'ok': 20}
- out_of_scope: {'false_clarify_boundary': 16, 'ok': 14}
- project: {'ok': 385, 'false_clarify_project': 65}

## Top Guard Reasons

- all_relevant_segments_in_project_scope: 385
- ambiguous_scope: 81
- out_of_project_query: 30
- mixed_scope_query_contains_out_of_project_segment: 4

## Verdict By Category

- admin_security: {'ok': 27, 'false_clarify_project': 8}
- cta: {'ok': 42, 'false_clarify_project': 3}
- executive_docs: {'ok': 24, 'false_clarify_project': 11}
- ftt: {'ok': 32, 'false_clarify_project': 13}
- harmful_security: {'ok': 20}
- mto: {'ok': 31, 'false_clarify_project': 4}
- nsi_regulation_reference: {'ok': 38, 'false_clarify_project': 2}
- operations_audit: {'ok': 19, 'false_clarify_project': 6}
- out_of_scope_generic: {'false_clarify_boundary': 16, 'ok': 14}
- passport: {'ok': 21, 'false_clarify_project': 4}
- pr_sk: {'ok': 42, 'false_clarify_project': 8}
- soi_ad: {'ok': 33, 'false_clarify_project': 2}
- soi_nsi: {'ok': 39, 'false_clarify_project': 1}
- testing: {'ok': 37, 'false_clarify_project': 3}

## Failed Examples

- `NTK500-V3-004` false_clarify_project | scope=project | category=ftt | actual=clarify | reason=ambiguous_scope
  Query: Как функционально-технических требованиях описывает журнал замечаний?
- `NTK500-V3-005` false_clarify_project | scope=project | category=ftt | actual=clarify | reason=ambiguous_scope
  Query: Как функционально-технических требованиях описывает обязательные поля?
- `NTK500-V3-007` false_clarify_project | scope=project | category=ftt | actual=clarify | reason=ambiguous_scope
  Query: Какие источники подтверждают вложения и подтверждающие материалы?
- `NTK500-V3-009` false_clarify_project | scope=project | category=ftt | actual=clarify | reason=ambiguous_scope
  Query: Какие источники подтверждают история изменений?
- `NTK500-V3-010` false_clarify_project | scope=project | category=ftt | actual=clarify | reason=ambiguous_scope
  Query: Какие источники подтверждают разграничение доступа?
- `NTK500-V3-011` false_clarify_project | scope=project | category=ftt | actual=clarify | reason=ambiguous_scope
  Query: Какие источники подтверждают уведомления пользователей?
- `NTK500-V3-013` false_clarify_project | scope=project | category=ftt | actual=clarify | reason=ambiguous_scope
  Query: Какие разделы документации нужно использовать для ответа про история изменений?
- `NTK500-V3-020` false_clarify_project | scope=project | category=ftt | actual=clarify | reason=ambiguous_scope
  Query: Какие сведения о журнал замечаний нужно брать из функционально-технических требованиях?
- `NTK500-V3-025` false_clarify_project | scope=project | category=ftt | actual=clarify | reason=ambiguous_scope
  Query: Какие требования или правила описывают вложения и подтверждающие материалы в функционально-технических требованиях?
- `NTK500-V3-031` false_clarify_project | scope=project | category=ftt | actual=clarify | reason=ambiguous_scope
  Query: Какие требования или правила описывают обязательные поля в функционально-технических требованиях?
- `NTK500-V3-039` false_clarify_project | scope=project | category=ftt | actual=clarify | reason=ambiguous_scope
  Query: Что в функционально-технических требованиях указано про печатные формы?
- `NTK500-V3-040` false_clarify_project | scope=project | category=ftt | actual=clarify | reason=ambiguous_scope
  Query: Что в функционально-технических требованиях указано про поиск и фильтрация?
- `NTK500-V3-044` false_clarify_project | scope=project | category=ftt | actual=clarify | reason=ambiguous_scope
  Query: Что нужно проверить в функционально-технических требованиях, если вопрос касается поиск и фильтрация?
- `NTK500-V3-051` false_clarify_project | scope=project | category=pr_sk | actual=clarify | reason=ambiguous_scope
  Query: Какие источники подтверждают журнал замечаний?
- `NTK500-V3-052` false_clarify_project | scope=project | category=pr_sk | actual=clarify | reason=ambiguous_scope
  Query: Какие источники подтверждают журнал предписаний?
- `NTK500-V3-053` false_clarify_project | scope=project | category=pr_sk | actual=clarify | reason=ambiguous_scope
  Query: Какие источники подтверждают печать форм?
- `NTK500-V3-054` false_clarify_project | scope=project | category=pr_sk | actual=clarify | reason=ambiguous_scope
  Query: Какие разделы документации нужно использовать для ответа про акт устранения замечаний?
- `NTK500-V3-055` false_clarify_project | scope=project | category=pr_sk | actual=clarify | reason=ambiguous_scope
  Query: Какие разделы документации нужно использовать для ответа про журнал предписаний?
- `NTK500-V3-056` false_clarify_project | scope=project | category=pr_sk | actual=clarify | reason=ambiguous_scope
  Query: Какие разделы документации нужно использовать для ответа про ответственный за устранение?
- `NTK500-V3-057` false_clarify_project | scope=project | category=pr_sk | actual=clarify | reason=ambiguous_scope
  Query: Какие разделы документации нужно использовать для ответа про печать форм?
- `NTK500-V3-058` false_clarify_project | scope=project | category=pr_sk | actual=clarify | reason=ambiguous_scope
  Query: Какие разделы документации нужно использовать для ответа про создание предписания?
- `NTK500-V3-105` false_clarify_project | scope=project | category=cta | actual=clarify | reason=ambiguous_scope
  Query: Какие источники подтверждают внешние интеграции?
- `NTK500-V3-108` false_clarify_project | scope=project | category=cta | actual=clarify | reason=ambiguous_scope
  Query: Какие источники подтверждают сетевые порты?
- `NTK500-V3-133` false_clarify_project | scope=project | category=cta | actual=clarify | reason=ambiguous_scope
  Query: Что в архитектурной документации указано про сетевые порты?
- `NTK500-V3-150` false_clarify_project | scope=project | category=soi_ad | actual=clarify | reason=ambiguous_scope
  Query: Какие источники подтверждают получение данных пользователя?
- `NTK500-V3-156` false_clarify_project | scope=project | category=soi_ad | actual=clarify | reason=ambiguous_scope
  Query: Какие разделы документации нужно использовать для ответа про получение данных пользователя?
- `NTK500-V3-181` false_clarify_project | scope=project | category=soi_nsi | actual=clarify | reason=ambiguous_scope
  Query: Какие источники подтверждают маппинг атрибутов?
- `NTK500-V3-222` false_clarify_project | scope=project | category=nsi_regulation_reference | actual=clarify | reason=ambiguous_scope
  Query: Какие источники подтверждают ответственный за ведение?
- `NTK500-V3-224` false_clarify_project | scope=project | category=nsi_regulation_reference | actual=clarify | reason=ambiguous_scope
  Query: Какие источники подтверждают правила актуализации?
- `NTK500-V3-260` false_clarify_project | scope=project | category=testing | actual=clarify | reason=ambiguous_scope
  Query: Как сценариях функциональных испытаний описывает разграничение доступа?
- `NTK500-V3-267` false_clarify_project | scope=project | category=testing | actual=clarify | reason=ambiguous_scope
  Query: Какие разделы документации нужно использовать для ответа про создание замечания?
- `NTK500-V3-294` false_clarify_project | scope=project | category=testing | actual=clarify | reason=ambiguous_scope
  Query: Что нужно проверить в сценариях функциональных испытаний, если вопрос касается подписание предписания?
- `NTK500-V3-298` false_clarify_project | scope=project | category=passport | actual=clarify | reason=ambiguous_scope
  Query: Какие источники подтверждают источники?
- `NTK500-V3-300` false_clarify_project | scope=project | category=passport | actual=clarify | reason=ambiguous_scope
  Query: Какие разделы документации нужно использовать для ответа про информационная безопасность?
- `NTK500-V3-313` false_clarify_project | scope=project | category=passport | actual=clarify | reason=ambiguous_scope
  Query: Что в паспорте информационной системы указано про техническая поддержка?
- `NTK500-V3-320` false_clarify_project | scope=project | category=passport | actual=clarify | reason=ambiguous_scope
  Query: Что нужно проверить в паспорте информационной системы, если вопрос касается техническая поддержка?
- `NTK500-V3-322` false_clarify_project | scope=project | category=admin_security | actual=clarify | reason=ambiguous_scope
  Query: Как руководстве администратора описывает Consul?
- `NTK500-V3-324` false_clarify_project | scope=project | category=admin_security | actual=clarify | reason=ambiguous_scope
  Query: Как эксплуатационной документации описывает Consul?
- `NTK500-V3-327` false_clarify_project | scope=project | category=admin_security | actual=clarify | reason=ambiguous_scope
  Query: Какие источники подтверждают Consul?
- `NTK500-V3-328` false_clarify_project | scope=project | category=admin_security | actual=clarify | reason=ambiguous_scope
  Query: Какие источники подтверждают Patroni?
