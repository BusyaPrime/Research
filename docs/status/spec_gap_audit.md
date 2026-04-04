# Аудит соответствия `MASTER_SPEC.md`

## Короткий итог

Проект уже не в статусе “заготовка”. Основной исследовательский контур собран: PIT, universe, labels, features, walk-forward, OOF, portfolio, costs, capacity, ablation, reporting и manifests уже существуют и проходят тесты. Хвост по spec остался, но он уже заметно уже и неприятно сконцентрирован в тех местах, где обычно и живет последний продовый геморрой.

Если совсем коротко: исследовательская честность системы уже есть, а оставшиеся долги сейчас в основном про operational maturity и финальный reproducible handoff.

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
- backtest идет только на OOF predictions;
- есть gross/net/cost/capacity/regime/decay артефакты.

### Reproducibility

- config hash и snapshot сохраняются;
- git metadata и runtime fingerprint пишутся;
- manifests и review bundle уже есть;
- report bundle тоже появился и сохраняет секции отдельно.

## Что еще не дожато

### Operational ingest path

В runtime пока живет deterministic synthetic bundle. Архитектурно это нормальный adapter/stub, но до полного соответствия production-grade operational data path это не дотягивает.

### Model zoo

Baseline, linear path и boosting-модели уже едут в operational runtime. До полного закрытия этого блока не хватает скорее расширения zoo и более богатого tuning/persistence слоя, а не самого факта поддержки advanced path.

### Portfolio optimizer

Портфельный слой рабочий, но beta-neutralization пока эвристическая. Это тот случай, когда “работает” ещё не равно “закрыто по spec”.

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

Почти закрыто. Основной путь честный, но optimizer ещё упрощён.

### Capacity/robustness/regimes/decay

Закрыто по текущему DoD-контуру: capacity, regimes, decay и ablation считаются, сохраняются и попадают в отчетный слой.

### Reporting & hardening

Почти закрыто. Артефакты, section bundle, review bundle и figures уже на месте. Не закончена именно последняя миля reproducibility и vendor-operational readiness.

## Вывод

По текущей оценке проект находится примерно в зоне `91-93%` от полного целевого состояния по `MASTER_SPEC.md`.

Это уже рабочая исследовательская платформа с честным сквозным контуром и нормальным report/review bundle, но еще не тот момент, когда можно без оговорок сказать “все требования spec добиты до конца”. До полного закрытия ТЗ осталось меньше, чем уже сделано, но оставшийся кусок по-прежнему сидит в самых капризных слоях: runtime adapters, portfolio optimizer и final release hardening.
