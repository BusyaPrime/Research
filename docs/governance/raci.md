# RACI по ролям

## Роли

### Research engineer / quant engineer

Отвечает за:

- временную семантику;
- PIT correctness;
- labels/features/splits;
- исследовательскую валидность backtest path.

### Platform engineer

Отвечает за:

- manifests и provenance;
- reproducibility;
- CLI/runtime/CI;
- хранение артефактов и data contracts.

### Reviewer

Отвечает за:

- anti-leakage review;
- проверку соответствия `MASTER_SPEC.md`;
- sanity-check по cost/capacity/reporting;
- то, чтобы “красиво” не подменяло “честно”.

### Product / hiring-facing owner

Отвечает за:

- выбор демонстрационного сценария;
- согласование deliverables;
- решение, что считается достаточным уровнем completeness для внешнего показа.

## Матрица ответственности

| Зона | Responsible | Accountable | Consulted | Informed |
| --- | --- | --- | --- | --- |
| Data contracts и schemas | Platform engineer | Platform engineer | Research engineer | Reviewer |
| PIT, labels, features | Research engineer | Research engineer | Reviewer | Product owner |
| Splits, OOF, backtest | Research engineer | Research engineer | Reviewer | Product owner |
| Artifacts, CI, manifests | Platform engineer | Platform engineer | Research engineer | Reviewer |
| Release readiness | Platform engineer + Research engineer | Reviewer | Product owner | Все участники |

## Подводный камень

Если role boundaries не назвать явно, очень быстро появляется режим “за это вроде кто-то отвечает”. Обычно это самая дорогая форма отсутствия ответственности.
