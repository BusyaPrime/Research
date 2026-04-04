# Definition of Done по фазам

## Фаза 1. Analyze and map

Считается закрытой, если:

- прочитаны `MASTER_SPEC`, machine-readable spec, schemas, configs, backlog, pseudocode;
- построена dependency map;
- зафиксированы обязательные сущности и инварианты;
- есть implementation plan без скрытого изменения scope.

## Фаза 2. Foundation

Считается закрытой, если:

- структура репозитория и package layout зафиксированы;
- конфиги валидируются;
- hash/snapshot/manifests работают;
- CLI поднимается;
- smoke-тесты и bootstrap path проходят.

## Фаза 3. Data layer

Считается закрытой, если:

- raw сохраняется без мутаций;
- bronze слой нормализован;
- provider contracts разнесены отдельно;
- QA-валидаторы и manifests сохраняются;
- schemas соблюдаются.

## Фаза 4. PIT & universe

Считается закрытой, если:

- as-of join не течет будущим;
- fundamentals используют `available_from`;
- universe строится point-in-time;
- exclusion reasons и diagnostics сохраняются.

## Фаза 5. Labels & features

Считается закрытой, если:

- labels выровнены относительно execution semantics;
- features строятся registry-driven способом;
- preprocessing fold-safe;
- gold panel собирается с dataset manifest.

## Фаза 6. Splits & models

Считается закрытой, если:

- walk-forward purged/embargoed;
- tuning не трогает test;
- OOF predictions сохраняются как отдельный слой;
- baseline models и metadata доступны для ревью.

## Фаза 7. Portfolio/backtest

Считается закрытой, если:

- portfolio строится только из OOF;
- execution идет на корректной временной оси;
- costs и turnover считаются отдельно;
- gross и net результаты разведены.

## Фаза 8. Capacity/robustness/regimes/decay

Считается закрытой, если:

- есть AUM ladder;
- regime analysis и decay analysis сохраняются в артефактах;
- robustness не сводится к одному числу в summary.

## Фаза 9. Reporting & hardening

Считается закрытой, если:

- все обязательные manifests и отчеты на месте;
- acceptance и leakage tests зеленые;
- release checklist можно пройти без ручных догадок;
- временные упрощения перечислены явно.
