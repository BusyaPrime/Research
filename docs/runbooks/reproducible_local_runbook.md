# Reproducible Local Runbook

Этот runbook нужен для очень приземленной вещи: чтобы следующий инженер мог поднять проект, прогнать pipeline и проверить release bundle без шаманства, устных договоренностей и фразы “ну у меня-то локально работало”.

## Когда его открывать

- перед первым локальным запуском;
- перед выпуском новой версии research-артефактов;
- когда нужно понять, что именно считается минимально честным reproducible handoff;
- когда пайплайн внезапно “вроде запускается”, но по артефактам остается неприятное послевкусие.

## Инварианты, которые здесь важнее удобства

- конфиг сначала валидируется, потом исполняется;
- provenance не теряется: `run_id`, `dataset_version`, `config_hash`, `git commit` должны доехать до manifests;
- backtest остается OOF-only;
- time semantics не меняются ради быстрого локального smoke;
- release bundle проверяется отдельным шагом, а не “на глаз”.

## Минимальный локальный прогон

### 1. Поднять окружение

```powershell
.\scripts\bootstrap.ps1
```

Если зависимости уже стоят, этот шаг все равно полезен: он быстро показывает, не развалился ли базовый toolchain.

### 2. Провалидировать конфиги

```powershell
python -m alpha_research config-validate
```

Если здесь ошибка, дальше не бежим. Иначе это классическая ситуация, где runtime уже уехал, а потом начинается охота на случайный хардкод.

### 3. Прогнать operational ingest surface

```powershell
python -m alpha_research ingest-market
python -m alpha_research ingest-fundamentals
python -m alpha_research ingest-corporate-actions
```

Сейчас эти команды работают через `synthetic vendor stub`. Это честное временное решение: stage path настоящий, но внешнего вендора тут пока нет.

### 4. Собрать report path

```powershell
python -m alpha_research run-report
```

Эта команда должна собрать manifests, sections, figures, review bundle и финальный отчетный слой.

### 5. Проверить release bundle машинно

```powershell
python .\scripts\verify_release_bundle.py --root .
```

Если verifier падает, это уже не “мелкий недочет”. Это значит, что reproducible handoff пробит в конкретном месте: пропал manifest, отчет, figure или в review bundle остались `pending_outputs`.

## Что должно получиться на выходе

- `artifacts/runs/<run_id>/manifests/pipeline_run_manifest.json`
- `artifacts/runs/<run_id>/manifests/review_bundle.json`
- `artifacts/runs/<run_id>/manifests/report_bundle.json`
- `artifacts/runs/<run_id>/reports/final_report.md`
- `artifacts/runs/<run_id>/reports/sections/*.md`
- `artifacts/runs/<run_id>/reports/figures/*.svg`

Если чего-то из этого нет, релизный слой считается недособранным.

## Что проверять руками, даже если verifier зеленый

- соответствует ли `dataset_version` ожиданиям конкретного прогона;
- не потерялись ли `temporary_simplifications` в review bundle;
- нет ли внезапно пустых figure-артефактов;
- не разошлись ли `required_manifests` в review bundle с реальными файлами на диске;
- совпадает ли `config_hash` между bootstrap/config snapshot и pipeline manifest.

## Где здесь еще честный хвост

- внешний vendor path все еще не подключен;
- clean-room прогон на совсем пустой машине еще требует отдельной добивки;
- secrets/runtime ops слой пока не проверен в боевой манере.

То есть runbook уже полезный и рабочий, но это еще не повод делать вид, что operational зрелость закрыта окончательно.
