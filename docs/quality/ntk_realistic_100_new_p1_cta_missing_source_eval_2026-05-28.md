# NTK realistic-100 new P1 targeted eval: CTA missing_source

Дата: 2026-05-28.

Bucket:

```text
CTA missing_source
```

Кейсы:

```text
NTK100-NEW-025
NTK100-NEW-026
NTK100-NEW-027
NTK100-NEW-028
```

## До исправления

Все 4 кейса были размечены как `missing_source`.

Симптом:

```text
025: PostgreSQL/MinIO как целевые storage-компоненты не поднимались стабильно.
026: запрос про PostgreSQL уходил в строки SIEM/Grafana Loki/логирования.
027: запрос про MinIO S3 поднимал логирование в S3 вместо storage/file-source chunks.
028: запрос про Kubernetes поднимал сетевые взаимодействия/logging вместо K8s master/worker и описания развертывания.
```

## Что изменено

В `configs/asu_june_bot/query_expansion.yaml` общий `cta_infrastructure` больше не расширяет точечный PostgreSQL/MinIO/Kubernetes-запрос всеми инфраструктурными терминами сразу. Добавлены отдельные expansion-группы:

```text
cta_postgresql
cta_minio_storage
cta_kubernetes
```

В retrieval layer добавлен точечный CTA infrastructure rerank:

```text
src/asu_june_bot/retrieval/bm25.py
src/asu_june_bot/retrieval/post_rerank.py
src/asu_june_bot/retrieval/hybrid.py
src/asu_june_bot/retrieval/query_intent.py
```

Логика:

```text
PostgreSQL route -> boost PostgreSQL/СУБД/хранение данных chunks.
MinIO/S3 route -> boost object storage/file storage chunks.
Kubernetes route -> boost K8s master/worker/service deployment chunks.
Non-logging CTA infra route -> penalize SIEM/Grafana Loki/logging-noise chunks.
Explicit CTA infra query -> penalize non-CTA documents as primary candidates.
Hybrid exact infra terms -> prefer stronger lexical signal.
```

Добавлены regression tests:

```text
tests/asu_june_bot/retrieval/test_bm25_ntk_routes.py
```

## Targeted eval

Search-level `hybrid`, NTK corpus, top-k=5:

```text
NTK100-NEW-025: status=ok, top5 ЦТА=5, anchors PostgreSQL+MinIO+object storage present
NTK100-NEW-026: status=ok, top5 ЦТА=5, primary PostgreSQL role/storage chunk
NTK100-NEW-027: status=ok, top5 ЦТА=5, primary MinIO S3 file/object storage chunk
NTK100-NEW-028: status=ok, top5 ЦТА=5, primary Kubernetes master/control-plane chunks

summary: passed=4/4
```

Chat-level `hybrid`, model `qwen2.5:7b-instruct`, top-k=5:

```text
NTK100-NEW-025: answered, sources=5, PostgreSQL+MinIO present
NTK100-NEW-026: answered, sources=5, PostgreSQL storage role present
NTK100-NEW-027: answered, sources=5, MinIO+S3 file storage present
NTK100-NEW-028: answered, sources=5, Kubernetes present

summary: passed=4/4
```

Regression:

```text
python -m pytest tests/asu_june_bot/retrieval/test_query_intent_project_markers.py tests/asu_june_bot/retrieval/test_bm25_ntk_routes.py -q

9 passed
```

## Вывод

P1 `CTA missing_source` закрыт на уровне targeted retrieval/chat eval. CTA infrastructure queries больше не доминируются строками SIEM/Grafana Loki/логирования и получают источники по PostgreSQL, MinIO S3 и Kubernetes.

Остаток P1: `PR missing_source`, `NSI regulation/reference`, `Passport`, `AD/app_ccpm`.
