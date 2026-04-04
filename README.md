# Alpha Research Platform

Это исследовательская платформа для daily cross-sectional alpha research по акциям США. Здесь собран не ноутбук на один вечер, а нормальный пайплайн с разнесенными слоями данных, point-in-time логикой, OOF-дисциплиной и отдельным контуром для портфеля, исполнения, костов и отчетности.

Главная мысль простая: если не держать временную семантику и provenance в узде с самого начала, дальше начинается красивая статистика на данных из будущего. Снаружи это выглядит как «модель молодец», внутри это обычно просто leakage в хорошем костюме.

## Что считать источником истины

Порядок такой:

1. `docs/specs/MASTER_SPEC.md`
2. `docs/specs/machine_spec.yaml`
3. `schemas/table_schemas.yaml`
4. `schemas/feature_registry.yaml`
5. `configs/*.yaml`
6. `tests/acceptance/acceptance_tests.yaml`
7. `pseudocode/pipeline_pseudocode.md`
8. `backlog/backlog.yaml`

Если где-то есть двусмысленность, решение принимается в пользу `MASTER_SPEC.md`, а отклонение фиксируется в инженерных заметках.

## Что уже есть

Система сейчас покрывает основной сквозной путь:

- foundation-слой: структура репозитория, `pyproject`, lockfiles, конфиг-контракты, structured logging, runtime fingerprint, manifests, базовый CLI;
- time semantics: торговый календарь, decision/execution timestamps, guard против same-bar execution;
- data layer: provider contracts, raw/bronze ingest для market data, fundamentals и corporate actions, schema validation, QA-валидаторы;
- PIT и universe: intervalized fundamentals, as-of join, future-data guards, point-in-time snapshots universe;
- labels/features/gold: label engine, registry-driven features, fold-safe preprocessing, gold panel assembly;
- research loop: purged walk-forward splits, baseline models, tuning для линейных моделей, OOF predictions;
- portfolio/backtest: target weights, turnover, execution simulation, costs, holdings state, gross/net accounting;
- robustness/evaluation: capacity ladder, predictive metrics, regime breakdown, decay, markdown report generation;
- hardening: leakage guards, operational stage wiring, CI smoke-проверки, release checklist.

## Как устроен проект

- `src/alpha_research/config` — загрузка и валидация конфигов, hash/snapshot.
- `src/alpha_research/time` — торговый календарь и все, что связано с временной семантикой.
- `src/alpha_research/data` — contracts, ingest, schemas, storage, QA.
- `src/alpha_research/reference` — security master и symbol mapping.
- `src/alpha_research/pit` — interval logic, as-of joins, guards против будущих данных.
- `src/alpha_research/universe` — point-in-time построение universe.
- `src/alpha_research/features` и `src/alpha_research/labels` — формирование признаков и таргетов.
- `src/alpha_research/preprocessing` — fold-safe трансформации.
- `src/alpha_research/dataset` — сборка gold-панели.
- `src/alpha_research/splits`, `models`, `training` — walk-forward, baseline models, OOF.
- `src/alpha_research/portfolio`, `execution`, `backtest`, `capacity` — портфельная и торговая часть.
- `src/alpha_research/evaluation` — метрики и финальные отчеты.
- `src/alpha_research/pipeline` — orchestration stage-by-stage.
- `tests` — unit, integration, leakage и acceptance-покрытие.

Разделение намеренно жесткое. Здесь лучше чуть дольше пожить с лишним модулем, чем потом выковыривать из одной функции одновременно и feature engineering, и торговую симуляцию, и поломанную временную ось.

## Что принципиально важно

- Решение на дате `t` принимается только после `close_t`.
- Базовое исполнение идет на `open_{t+1}`.
- Fundamentals джойнятся только по `available_from`.
- Любой preprocessing fit'ится только на train fold.
- Backtest строится только на OOF predictions.
- Gross и net результаты считаются отдельно.
- Каждый run должен быть привязан к `dataset version`, `config hash`, `git commit`, `run id`, `timestamp`.

Если что-то из этого сломано, результат красивый, но исследовательски недействительный.

## Как запускать

Быстрый старт:

```bash
python -m alpha_research config-validate
python -m alpha_research bootstrap
python -m alpha_research run-full-pipeline --dry-run
python -m pytest
```

Отдельные стадии тоже доступны через CLI. Полный список команд и ожидаемых артефактов описан в `docs/specs/machine_spec.yaml`.

## Как проверять

- `python -m pytest` — базовый прогон тестов;
- `tests/leakage` — проверки на протечки;
- `tests/integration` — сквозные куски пайплайна;
- `tests/acceptance/acceptance_tests.yaml` — quality gates из спецификации.

Если падает leakage-тест, это не «мелкая нестабильность», а красная лампа. Значит, где-то пайплайн знает о будущем больше, чем ему положено.

## Что еще не доведено до релизного блеска

- Часть CLI-стадий уже заведена в operational path, но вокруг них еще есть слой доводки по артефактам и финальной упаковке отчетов.
- В пайплайне остается несколько честно помеченных временных упрощений, например упрощенная beta-neutralization в портфельном слое.
- Полный release-hardening еще допиливается: тут уже не про идею, а про то, чтобы все воспроизводилось без сюрпризов на чистом окружении.

Это не ломает архитектуру, но и делать вид, что работа полностью закончена, было бы странно.
