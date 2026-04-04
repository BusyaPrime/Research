# Naming conventions и versioning policy

## Зачем это вообще нужно

Если имена артефактов, датасетов и версий гуляют свободно, дальше ломается не только эстетика. Ломается provenance, сравнение запусков и здравый смысл в ревью.

## Базовые правила

- в data layer всегда используем `security_id`, а не `symbol` как основной ключ;
- таблицы и артефакты называем по слою и сути: `silver_market_pit`, `gold_panel`, `oof_predictions`, `capacity_results`;
- версии должны быть видны в dataset manifest и review bundle;
- `run_id` не заменяет `dataset_version`, а дополняет его.

## Что должно быть versioned

- dataset;
- config snapshot;
- feature registry version;
- label family version;
- git commit;
- generated report bundle.

## Чего делать не надо

- не изобретать ad-hoc имена под один конкретный запуск;
- не смешивать в одном имени и бизнес-смысл, и полпути до файловой системы;
- не подменять версию датасета датой прогона.
