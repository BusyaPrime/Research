# Аудит соответствия `MASTER_SPEC.md`

## Короткий итог

Проект закрыт по `MASTER_SPEC.md` как production-grade research platform. Основной контур, release path и live public verification теперь сходятся друг с другом, а не живут тремя параллельными жизнями.

Если совсем коротко: исследовательская честность, operational stitching и reproducible handoff здесь уже собраны в один рабочий контур.

## Что уже закрыто по сути

### Time semantics и PIT

- решение живет после `close_t`;
- baseline execution идет на `open_{t+1}`;
- fundamentals джойнятся по `available_from`;
- guards на future-data есть;
- label alignment и same-bar leakage проверяются тестами.

### Research loop

- features строятся registry-driven способом;
- preprocessing fold-safe;
- splits purged/embargoed;
- split protocol сохраняется отдельным артефактом и проверяет overlap/purge/embargo инварианты;
- backtest идет только на OOF predictions;
- evaluation protocol и data-usage trace сохраняются отдельным manifest-слоем;
- есть gross/net/cost/capacity/regime/decay артефакты;
- uncertainty/FDR/stability diagnostics теперь тоже лежат в machine-readable виде.

### Reproducibility

- config hash и snapshot сохраняются;
- git metadata и runtime fingerprint пишутся;
- manifests и review bundle уже есть;
- report bundle тоже появился и сохраняет секции отдельно.

## Что было последним хвостом и чем его закрыли

### Operational ingest path

Этот хвост уже не в том месте, где раньше. Теперь есть два честных operational режима:

- deterministic synthetic mode для offline/smoke-прогонов;
- configured adapters path для reference, ingest и downstream runtime.

То есть `run-report` и `run-full-pipeline` теперь умеют собирать research bundle не только из синтетики, но и через configured adapters с реальными внешними вызовами и локальными источниками. Плюс появился clean-room smoke path на local-file adapters без monkeypatch'ей и без сети, а live-public smoke отдельно прошел на реальных публичных источниках.

### Strict runtime policy

Этот слой тоже закрыт. Runtime больше не занимается “умной деградацией”, которая выглядит прилично в логах и плохо пахнет на ревью.

Что теперь зафиксировано конструктивно:

- operational experiment выбирается явно через `runtime.operational_experiment_key`;
- неподдерживаемая модель в operational path приводит к hard failure, а не к fallback на baseline;
- requested report formats обязаны реально существовать, иначе release-capable run не считается завершенным;
- synthetic path маркируется как `fixture_only` и не проходит release verifier;
- review bundle с `pending_outputs`, `temporary_simplifications` или `release_eligible = false` verifier отклоняет.

### Statistical skepticism

Этот слой теперь тоже закрыт до рабочего состояния и больше не висит как благородное намерение.

Что есть сейчас:

- bootstrap confidence intervals для predictive и portfolio метрик;
- `probabilistic_sharpe_ratio` и `deflated_sharpe_ratio`;
- model hypothesis registry и FDR-контроль;
- prediction correlation matrix;
- stability gates и machine-readable `approval_summary`;
- metamorphic regression-тесты на split и OOF инварианты.

Это не заменяет будущий research science-максимум в духе полноценного PBO или больших experiment ledgers, но уже переводит слой статистической проверки из “можно было бы сделать” в реально работающий audit artifact.

### Model zoo

Baseline, linear path и boosting-модели уже едут в operational runtime. Для критериев success из spec этого достаточно; дальнейшее расширение zoo уже относится к эволюции платформы, а не к незакрытому DoD.

### Portfolio optimizer

Этот хвост закрыт. В портфельном слое теперь стоит constrained projection с affine-ограничениями и box bounds, а не старая эвристическая коррекция. Отдельные тесты на beta- и sector-neutralization тоже уже добавлены.

### Reporting figures

Этот хвост закрыт. Mandatory figures теперь рендерятся как отдельные SVG-артефакты и входят в report bundle.

## Проверка по фазам

### Analyze and map

Закрыто. Source-of-truth прочитан, dependency map и implementation path собраны.

### Foundation

Закрыто. Конфиги, hash/snapshot, CLI, manifests и базовый test harness на месте.

### Data layer

Закрыто по архитектуре и тестам. Есть ingest contracts, raw/bronze, QA и schemas.

### PIT & universe

Закрыто. Это один из самых сильных кусков текущей реализации.

### Labels & features

Закрыто по основному research path.

### Splits & models

Закрыто по основному operational path. Незаполненный хвост тут уже не в базовой работоспособности, а в дальнейшей эволюции model zoo.

### Portfolio/backtest

Закрыто. Основной путь честный, optimizer уже constrained, costs/turnover/gross-net/accounting на месте.

### Capacity/robustness/regimes/decay

Закрыто по текущему DoD-контуру: capacity, regimes, decay и ablation считаются, сохраняются и попадают в отчетный слой.

### Reporting & hardening

Закрыто. Артефакты, section bundle, review bundle, figures, configured clean-room smoke и live-public smoke уже на месте.

## Вывод

По текущей оценке проект находится в зоне `100%` от целевого состояния по `MASTER_SPEC.md`.

Это рабочая исследовательская платформа с честным сквозным контуром, configured operational data path, dedicated benchmark adapter path, release verifier, config-driven release smoke profile и нормальным report/review bundle. На текущем этапе требования spec закрыты без оговорок; дальше уже начинается не добивка ТЗ, а обычная эксплуатационная жизнь системы.

## Что это значит относительно более жесткого критерия 10/10

Если мерить не только `MASTER_SPEC.md`, а более злой критерий из отдельного инженерного ревью, картина чуть менее глянцевая и от этого полезнее.

Что уже дожали сверх базового DoD:

- strict runtime policy теперь валит на неподдерживаемых operational режимах и не выдает degraded run за нормальный;
- split protocol формализован и дополнительно прикрыт randomized invariant tests;
- evaluation protocol, data-usage trace и approval gating уже живут как отдельный audit-ready контракт;
- model layer получил tiered registry, advanced linear ranking path и отдельный model stability слой;
- появился machine-readable spec coverage map, который уже связывает clause -> code -> tests -> artifacts.

Что еще остается до совсем бесспорного “здесь не к чему подкопаться”:

- orchestration все еще слишком тяготеет к тяжелому `runtime.py`, и его правильно было бы дальше резать на более явные stage runtimes;
- randomized invariants уже есть, но полноценный mutation testing и более широкий property-based слой еще не закрыты;
- execution/capacity реализм можно сделать еще злее через halted/no-open/liquidity cliff сценарии;
- current model stack уже не ограничивается baseline'ами, но до максимально взрослого external ranking zoo еще есть пространство;
- provenance хороший, но не полностью content-addressed на уровне immutable replay guarantee.

Итог простой:

- по `MASTER_SPEC.md` проект закрыт;
- по расширенному критерию “бесспорный 10/10 без права на красивую ложь” проект уже очень близко, но еще не в финальной точке.
