# Anti-leakage review checklist

Это короткий список вопросов, который reviewer должен прогонять перед тем, как верить любому красивому графику.

## Time semantics

- решение действительно принимается после `close_t`?
- baseline execution действительно идет на `open_{t+1}`?
- labels стартуют не раньше execution timestamp?

## PIT и fundamentals

- join идет по `available_from`, а не по `fiscal_period_end`?
- restated data не протекает назад без явной PIT-логики?
- future-data guard покрывает ключевые точки входа?

## Universe

- нет survivor bias в фильтрах?
- price/ADV/listing eligibility считаются point-in-time?
- exclusion reasons сохраняются и объяснимы?

## Features

- любая feature живет в registry?
- лаги и доступность данных соответствуют decision timestamp?
- нет ли feature, которая знает цену исполнения заранее?

## Labels

- label alignment соответствует next-open execution semantics?
- overlap, purge и embargo не сведены к декоративным словам?

## Splits и preprocessing

- scaler / winsor / neutralizer fit'ятся только на train fold?
- tuning не видит test fold?
- backtest идет только по OOF predictions?

## Portfolio и execution

- portfolio строится из OOF, а не из retrained-on-all?
- participation caps реально применяются?
- gross и net результаты разведены?
- borrow assumptions для shorts учтены?

## Reporting

- ограничения перечислены явно?
- temporary simplifications видны в report/review bundle?
- manifests позволяют восстановить источник результата?
