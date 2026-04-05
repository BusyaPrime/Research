# Инженерные заметки

Здесь лежат решения, которые пришлось принимать по дороге, когда machine-readable слой, prose-spec и реальная реализация смотрели друг на друга не совсем одинаково. Идея простая: спорные места должны быть видны сразу, а не всплывать потом в формате «почему тут вообще так».

## Иерархия источников истины

1. `docs/specs/MASTER_SPEC.md`
2. `docs/specs/machine_spec.yaml`
3. `schemas/table_schemas.yaml`
4. `schemas/feature_registry.yaml`
5. `configs/*.yaml`
6. `tests/acceptance/acceptance_tests.yaml`
7. `pseudocode/pipeline_pseudocode.md`
8. `backlog/backlog.yaml` и `backlog/backlog.csv`

Если между слоями есть конфликт, решение принимается сверху вниз по этому списку.

## Принятые решения

## Реестр фич богаче в prose-spec, чем в YAML

`schemas/feature_registry.yaml` хорошо описывает формулы, входы и группы фич, но не хранит в явном виде все операционные поля из master-spec: lag policy, missing policy, normalization policy и PIT semantics.

Что сделали:

- оставили исходный registry каноническим и не ломали его структуру;
- недостающие операционные политики вынесли в кодовый слой feature metadata;
- место для расширения registry оставили совместимым назад, чтобы потом не устраивать миграцию ради миграции.

Почему так:

`MASTER_SPEC.md` требует строгой семантики, а supplied YAML в этой части неполный. Ломать canonical файл на первом проходе было бы плохим обменом: шума много, пользы мало.

## CLI-контур появился раньше, чем были готовы все стадии

Machine-readable spec сразу задает поверхность команд, но сами стадии доезжали поэтапно. Если ждать, пока все будет идеально, вокруг проекта быстро образуется классическая зона «здесь пока ничего не подключено, но вы верьте».

Что сделали:

- подняли полный CLI surface заранее;
- для неготовых стадий сначала возвращали явные structured stubs;
- по мере готовности модулей переключали команды на operational handlers.

Почему так:

Это сохраняет контракт и не прячет незавершенность. Пользователь видит, что команда существует, что она должна делать и какой слой еще не доведен.

## Временная семантика закреплена отдельным слоем, а не размазана по пайплайну

Наивный путь тут очень соблазнительный: местами посчитать `t+1` прямо в label engine, местами прямо в backtest, а потом удивляться, почему один и тот же горизонт живет тремя разными жизнями.

Что сделали:

- decision/execution semantics вынесли в `src/alpha_research/time`;
- PIT guards и as-of joins оставили отдельным слоем;
- leakage tests привязали к этим инвариантам напрямую.

Почему так:

Если время не централизовано, дальше начинается каша. Причем каша очень убедительная на графиках.

## Data contracts держим через схемы, а не через «ну вроде и так совпадает»

Табличные схемы из spec обязательны, и это тот случай, где мягкость обычно дорого обходится.

Что сделали:

- добавили YAML-driven schema validation;
- нормализацию типов и required/optional полей оставили рядом со storage/ingest;
- метаданные версии и происхождения данных не выбрасываем по дороге.

Почему так:

Без этого provenance начинает растворяться сразу после первого нормального рефакторинга ingest-слоя.

## Временные упрощения

### Портфельный optimizer сначала был упрощен, потом дожали его до constrained path

Стартовая версия действительно держалась на эвристической коррекции. Это был осознанный промежуточный шаг: нужно было сперва замкнуть честный путь `OOF -> portfolio -> execution -> backtest`, а уже потом тащить отдельную постановку ограничений.

Что изменилось:

- в `src/alpha_research/portfolio/targets.py` теперь стоит constrained projection с affine-ограничениями и box bounds;
- beta-neutralization и sector-neutralization проверяются отдельными integration-тестами;
- старый хвост в этом месте закрыт и больше не считается временным упрощением.

Почему так лучше:

Наивная коррекция веса хороша только до первого серьезного разговора про exposure control. Дальше она начинает жить на честном слове и одном `if`, а это для такого слоя уже плохая примета.

## Что изменилось после первого hardening-прохода

### Advanced boosting path теперь едет в operational runtime

Раньше canonical config с `gradient_boosting_ranker` был формально валиден, но operational path его обходил стороной и сваливался на ridge. Это был некрасивый разрыв между config contract и реальным исполнением.

Что сделали:

- подключили boosting-модели в `training/oof`;
- добавили deterministic tuning path без доступа к test fold;
- завели простой params registry для повторного использования best params;
- включили advanced model selection в runtime по приоритету, а не по остаточному принципу.

Почему это важно:

Если config обещает одну модель, а runtime тихо едет на другой, это уже не research platform, а источник недоразумений с красивым CLI.

### Reporting figures и ablation теперь живут как настоящие артефакты

Раньше report bundle был уже приличный, но mandatory figures оставались только в индексе, а ablation вообще не доезжал до runtime. Сейчас этот кусок закрыт до нормального рабочего состояния.

Что сделали:

- добавили figure renderer и сохраняем все mandatory figures как отдельные SVG-артефакты;
- включили `ablation_analysis` в reporting config и section bundle;
- считаем feature-family и preprocessing ablation отдельным слоем и сохраняем его в diagnostics;
- release bundle теперь знает не только секции отчета, но и реальные figure paths.

Что это значит для результата:

- review bundle стал гораздо полезнее для ревью и release-check;
- reporting слой теперь не делает вид, что figures “когда-нибудь будут”;
- хвост сместился из отчетности туда, где ему и место: ingest adapters, optimizer и final reproducibility polish.

### Для release-hardening появился отдельный smoke profile

Полный `run-report` на базовом профиле честный, но для регулярной smoke-проверки слишком тяжелый. Если такой прогон бездумно воткнуть в default CI, он быстро превращает “быстрый сигнал о проблеме” в длинный сериал с неизвестным концом.

Что сделали:

- добавили `release_smoke` профиль в `configs/runtime.yaml`;
- подняли `scripts/run_release_smoke.py`, который гонит ingest, compact runtime report path и release verifier подряд;
- вынесли тяжелый smoke в отдельный GitHub workflow, а не в основной тестовый контур;
- добавили summary artifact, чтобы результат smoke не исчезал в логах.

Почему так:

Smoke должен быть достаточно настоящим, чтобы ловить broken stitching между слоями, но не настолько тяжелым, чтобы его начинали обходить стороной. Тут важно не перепутать честность с желанием уронить себе CI на ровном месте.

### Runtime теперь умеет собирать bundle через configured adapters, а не только из синтетики

Раньше самый неприятный разрыв был в том, что ingest surface уже выглядел operational, а downstream `run-report` и `run-full-pipeline` продолжали жить на synthetic research bundle. То есть архитектурно слои были правильные, но operational truth заканчивалась слишком рано.

Что сделали:

- добавили configured adapter layer для security master, market, fundamentals и corporate actions;
- научили runtime собирать research bundle через реальные adapter contracts и уже сохраненные bronze artifacts;
- оставили synthetic mode как честный fallback для offline/smoke path, а не как единственную опору всей системы;
- для configured adapters режима завели benchmark proxy по market panel, потому что labels config допускает `proxy_or_index_return`.

Почему так:

Если ingest ходит во внешний мир, а downstream pipeline тихо переключается назад на синтетику, это уже не operational path, а декорация с хорошими манерами. Этот хвост нужно было закрыть не ради красоты в README, а потому что иначе release-аудит был бы неполным по сути.

### Для benchmark появился отдельный adapter path, а proxy остался только запасным аэродромом

Пока benchmark был только в виде proxy по market panel, это было терпимо для раннего research-контура, но не очень похоже на взрослый data contract. Если benchmark нужен как отдельный источник, у него должна быть собственная точка входа, а не жизнь “между делом” где-то в runtime.

Что сделали:

- добавили `benchmark_provider` в canonical configs;
- поддержали dedicated benchmark adapters в configured path;
- оставили market-panel proxy как fallback, если benchmark adapter явно не настроен;
- протащили выбранный benchmark mode в runtime notes и data lineage section отчета.

Почему так:

Proxy хорош как страховка, но плох как молчаливое default-поведение там, где человеку потом надо объяснять, откуда взялись benchmark returns и почему именно такие.

### Clean-room smoke теперь идет через configured local fixtures без monkeypatch'ей

Раньше release smoke уже был полезным, но все еще слишком сильно полагался либо на synthetic mode, либо на подмены в тестах. Для hardening это не катастрофа, но и не тот уровень самодостаточности, который хочется видеть перед финальным handoff.

Что сделали:

- добавили подготовку local configured fixtures из synthetic bundle;
- release smoke теперь умеет сам собрать security master, market, fundamentals, corporate actions и benchmark files;
- после этого smoke идет уже через `configured_adapters`, а не через прямой synthetic shortcut;
- отдельный integration-тест проверяет этот путь без monkeypatch'ей.

Что это дает:

- clean-room path перестал быть бумажным;
- release hardening теперь проверяет реальный configured runtime stitching;
- оставшийся хвост сузился до живого внешнего контура, а не до внутренней сборки проекта.

### Live-public verification теперь идет по-настоящему, а не “теоретически можем”

Самая неприятная финальная ловушка была не в коде как таковом, а в ощущении “ну live path у нас уже почти есть”. Пока нет реального прогона против внешних источников, это не verification, а надежда на хорошую погоду.

Что сделали:

- заменили заведомо хрупкий `stooq`-путь на рабочий публичный market/events adapter через Yahoo chart API;
- добавили security master adapter через SEC exchange mapping;
- оставили SEC companyfacts для fundamentals;
- подняли отдельный `live-public` smoke-режим поверх того же release path;
- добили selection logic, чтобы smoke не пытался тащить весь reference universe целиком и не умирал на первом странном тикере.

Почему это важно:

На этом шаге проект перестал быть “release-ready на внутреннем стенде” и стал платформой, у которой есть и clean-room path, и live external verification. Это уже не косметика, а та самая граница между “архитектура вроде правильная” и “да, контур действительно работает”.

## Что остается уже после закрытия ТЗ

- расширять model zoo и tuning policies;
- добавлять новые adapters под более богатые commercial feeds;
- при желании усиливать ops-monitoring вокруг внешних интеграций.

Это уже не недоделки проекта, а нормальная следующая жизнь платформы.
