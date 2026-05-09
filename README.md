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
- research governance: strict runtime policy, явный split protocol, evaluation manifest и data-usage trace по fold/model;
- statistical skepticism: bootstrap uncertainty, probabilistic/deflated Sharpe, FDR-контроль, stability gates и machine-readable approval summary;
- portfolio/backtest: target weights, turnover, execution simulation, costs, holdings state, gross/net accounting;
- robustness/evaluation: capacity ladder, predictive metrics, regime breakdown, decay, ablation-матрицы, markdown/html report generation, persisted section bundle, figure artifacts и review bundle;
- content-addressed lineage: dataset manifests фиксируют content/schema/profile/file hash и дают immutable dataset id вместо “просто latest parquet где-то на диске”;
- pipeline orchestration: тонкий dispatcher и отдельные runtime-модули для ingest, research, reporting, release и verification;
- hardening: leakage guards, operational stage wiring, `ruff`, `mypy`, configured-local smoke, release verifier, acceptance/spec coverage audit и nightly live-public smoke.
- live verification: configured local smoke без сети и отдельный live-public smoke через публичные источники.

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
- `src/alpha_research/pipeline` — orchestration stage-by-stage, stage graph и разнесенные runtime handlers.
- `tests` — unit, integration, leakage и acceptance-покрытие.
- `docs/status/spec_coverage_map.yaml` — machine-readable карта, которая связывает ключевые инварианты spec с кодом, тестами и артефактами.

Разделение намеренно жесткое. Здесь лучше чуть дольше пожить с лишним модулем, чем потом выковыривать из одной функции одновременно и feature engineering, и торговую симуляцию, и поломанную временную ось.

## Что принципиально важно

- Решение на дате `t` принимается только после `close_t`.
- Базовое исполнение идет на `open_{t+1}`.
- Fundamentals джойнятся только по `available_from`.
- Любой preprocessing fit'ится только на train fold.
- Backtest строится только на OOF predictions.
- Gross и net результаты считаются отдельно.
- Каждый run должен быть привязан к `dataset version`, `config hash`, `git commit`, `run id`, `timestamp`.
- Unsupported experiment, missing requested report format и release-grade run с временными упрощениями не маскируются под `completed`.
- Сильная метрика без uncertainty/FDR/stability diagnostics не считается “доказанной”, а идет в отчет как недопроверенная гипотеза.

Если что-то из этого сломано, результат красивый, но исследовательски недействительный.

## Как запускать

Быстрый старт:

```bash
python -m alpha_research config-validate
python -m alpha_research bootstrap
python -m alpha_research run-full-pipeline --dry-run
python -m pytest
python .\scripts\verify_release_bundle.py --root .
python .\scripts\run_release_smoke.py --root . --mode configured-local
python .\scripts\run_release_smoke.py --root . --mode live-public
```

Отдельные стадии тоже доступны через CLI. Полный список команд и ожидаемых артефактов описан в `docs/specs/machine_spec.yaml`.

## Как проверять

- `python -m pytest` — базовый прогон тестов;
- `python -m ruff check src tests` — lint gate;
- `python -m mypy src/alpha_research` — type gate;
- `tests/leakage` — проверки на протечки;
- `tests/integration` — сквозные куски пайплайна;
- `tests/acceptance/acceptance_tests.yaml` — quality gates из спецификации.
- `docs/status/acceptance_coverage_map.yaml` — machine-readable связка acceptance suite с реальными тестами.
- `docs/status/spec_coverage_map.yaml` — быстрый способ проверить, где clause реально enforce'ится кодом, а не просто красиво описан.
- `python .\scripts\verify_release_bundle.py --root .` — машинная проверка release bundle и связанных артефактов.
- `python .\scripts\run_release_smoke.py --root .` — компактный operational smoke path с ingest, report и verifier.

Если падает leakage-тест, это не «мелкая нестабильность», а красная лампа. Значит, где-то пайплайн знает о будущем больше, чем ему положено.

## Что важно понимать про режимы запуска

- `synthetic_vendor_stub` остается как детерминированный offline/fallback path для быстрых локальных и регрессионных прогонов;
- `synthetic_vendor_stub` теперь живет строго как `fixture_only` режим: он детерминированный, полезный для regression/clean-room сценариев, но не считается release-grade результатом;
- `configured_adapters` — основной operational режим с публичными и локальными адаптерами;
- `configured-local` smoke нужен для clean-room воспроизводимости без сети;
- `live-public` smoke нужен для проверки real external path на публичных источниках.

Это не набор взаимозаменяемых костылей. У каждого режима свой capability contract: можно ли строить release bundle, требуется ли external proof и допустим ли synthetic ingest.

Для локального воспроизводимого прогона есть отдельный runbook: `docs/runbooks/reproducible_local_runbook.md`.
Для отдельного тяжелого smoke-прогона есть workflow `.github/workflows/release_smoke.yml`.
Для честной сверки реализации со спецификацией есть `docs/status/spec_coverage_map.yaml` и `docs/status/spec_gap_audit.md`.

## Developer docs

- `docs/development/onboarding.md` — быстрый путь от clone до reviewable local run.
- `docs/development/local_setup.md` — установка и editable/dev режим.
- `docs/development/commands.md` — Makefile, CLI и quality gate команды.
- `docs/development/environment.md` — безопасная работа с env и adapter variables.
- `docs/development/troubleshooting.md` — типовые локальные сбои и диагностика.
- `docs/development/project_structure.md` — ответственность ключевых папок.
- `docs/development/contribution_workflow.md` — branch, commit и PR workflow.
