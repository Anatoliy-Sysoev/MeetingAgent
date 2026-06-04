# NTK retrieval gate floor analyzer

- rows: 500
- project: 450
- out_of_scope: 30
- harmful_security: 20

## Max Vector Distribution

- project: n=450 p10=0.5425 p50=0.6342 p90=0.6959 max=0.7915 missing_vector=2
- out_of_scope: n=30 p10=0.403 p50=0.449 p90=0.5081 max=0.5292 missing_vector=0
- harmful_security: n=20 p10=0.4965 p50=0.5503 p90=0.6474 max=0.6969 missing_vector=0

## Max Term Overlap Distribution

- project: p10=1.0 p50=2.0 p90=4.0 max=6.0
- out_of_scope: p10=0.0 p50=0.0 p90=1.0 max=1.0
- harmful_security: p10=0.9 p50=1.5 p90=3.0 max=4.0

## Frontier

Gate: `(max_vector >= floor) OR (term_overlap >= k AND project_doc_hits > 0)`

| floor | k | project_pass | out_of_scope_leak | harmful_pass |
|---:|---:|---:|---:|---:|
| 0.40 | 1 | 450/450 | 27 | 20 |
| 0.40 | 2 | 448/450 | 27 | 20 |
| 0.40 | 3 | 448/450 | 27 | 20 |
| 0.42 | 1 | 450/450 | 22 | 20 |
| 0.42 | 2 | 447/450 | 20 | 20 |
| 0.42 | 3 | 447/450 | 20 | 20 |
| 0.44 | 1 | 450/450 | 20 | 20 |
| 0.44 | 2 | 447/450 | 18 | 20 |
| 0.44 | 3 | 446/450 | 18 | 20 |
| 0.46 | 1 | 449/450 | 15 | 20 |
| 0.46 | 2 | 445/450 | 13 | 20 |
| 0.46 | 3 | 443/450 | 13 | 20 |
| 0.48 | 1 | 449/450 | 12 | 20 |
| 0.48 | 2 | 443/450 | 10 | 20 |
| 0.48 | 3 | 440/450 | 10 | 20 |
| 0.50 | 1 | 448/450 | 9 | 18 |
| 0.50 | 2 | 438/450 | 5 | 17 |
| 0.50 | 3 | 434/450 | 5 | 17 |
| 0.52 | 1 | 447/450 | 9 | 18 |
| 0.52 | 2 | 430/450 | 2 | 16 |
| 0.52 | 3 | 424/450 | 2 | 16 |
| 0.55 | 1 | 447/450 | 7 | 18 |
| 0.55 | 2 | 422/450 | 0 | 13 |
| 0.55 | 3 | 408/450 | 0 | 13 |

## Recommendation

Лучшая точка с `out_of_scope_leak=0`: `floor=0.55`, `k=2`, `project_pass=422/450`.

`harmful_pass` здесь диагностический: harmful держится pre-retrieval guard, а не evidence gate.
