# Чеклист перед релизом

Этот список нужен не для галочки. Он нужен, чтобы в релиз не уехал пайплайн, который красиво выглядит на локальной машине, а на следующем окружении разваливается или, что хуже, тихо подмешивает себе будущее.

## Обязательные manifests

- `dataset_manifest.json`
- `oof_manifest.json`
- `backtest_manifest.json`
- `capacity_manifest.json`
- `pipeline_run_manifest.json`

У каждого артефакта должны быть видны как минимум `run_id`, `dataset_version`, `config_hash`, `git_commit` и timestamp. Если provenance потерялся, дальше спорить о метриках уже поздновато.

## Обязательные отчеты

- финальный research report;
- артефакт с fold metadata и validation protocol;
- predictive diagnostics;
- portfolio diagnostics;
- regime analysis;
- decay analysis;
- cost/capacity diagnostics.

Если какой-то раздел пока не готов, он не замалчивается, а уезжает в отчет как явный stub с пометкой о статусе.

## Review bundle

`review_bundle.json` должен ссылаться на:

- manifests;
- отчеты;
- `run_id`;
- `dataset_version`;
- `config_hash`;
- ключевые метрики;
- список всех `TEMPORARY SIMPLIFICATION`.

Иначе ревью превращается в археологию, а на это обычно ни у кого нет лишней недели.

## Release gates

- unit tests зеленые;
- integration tests зеленые;
- leakage tests зеленые;
- CI падает при любом test failure;
- артефакты воспроизводятся из config snapshot и `git commit`;
- backtest собран только из OOF predictions;
- time semantics подтверждены тестами и не нарушены в runtime path.

## Что проверить руками перед пушем релизной ветки

- нет ли в конфиге параметров, которые случайно переопределяются хардкодом;
- не потерялись ли `available_from` и dataset metadata по дороге между слоями;
- не попала ли в портфельный контур логика, которая знала цену исполнения раньше времени;
- нет ли временных упрощений без явной пометки и TODO;
- совпадают ли manifests, отчеты и фактические артефакты на диске.
