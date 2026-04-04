# Аудит соответствия `MASTER_SPEC.md`

## Короткий итог

Проект уже не в статусе “заготовка”. Основной исследовательский контур собран: PIT, universe, labels, features, walk-forward, OOF, portfolio, costs, capacity, reporting и manifests уже существуют и проходят тесты. Но до полного DoD из spec ещё остается вполне конкретный хвост.

Если совсем коротко: базовая честность системы уже есть, а хвост сейчас в основном про operational maturity и release completeness.

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

Baseline и linear path есть. Advanced rankers в config/spec уже видны, но в operational runtime они пока не едут.

### Portfolio optimizer

Портфельный слой рабочий, но beta-neutralization пока эвристическая. Это тот случай, когда “работает” ещё не равно “закрыто по spec”.

### Reporting figures

Report bundle уже знает, какие figures обязательны, и индексирует их. Но отдельного рендера всех mandatory figures пока нет.

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

Почти закрыто. Базовый контур есть, но model zoo в runtime ещё не полный.

### Portfolio/backtest

Почти закрыто. Основной путь честный, но optimizer ещё упрощён.

### Capacity/robustness/regimes/decay

Почти закрыто. Аналитика есть, но часть визуального слоя ещё не дорендерена.

### Reporting & hardening

Частично закрыто. Артефактов уже много и они осмысленные, но финальный release-grade polish ещё не закончен.

## Вывод

По текущей оценке проект находится примерно в зоне `85-87%` от полного целевого состояния по `MASTER_SPEC.md`.

Это уже рабочая исследовательская платформа с честным сквозным контуром, но еще не тот момент, когда можно без оговорок сказать “все требования spec добиты до конца”. До полного закрытия ТЗ осталось меньше, чем уже сделано, но оставшийся кусок как назло относится к самым капризным слоям: runtime adapters, optimizer и final release hardening.
