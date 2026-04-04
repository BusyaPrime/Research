# MASTER SPEC — Production-Grade Alpha Research Platform

> Язык документа: русский. Формат: master-spec для инженерной команды / quant research stack.

## 1. Назначение документа

Это сверхдетализированное техническое задание уровня master-spec для проекта `daily cross-sectional equities alpha research platform`.
Документ намеренно избыточен: он одновременно выполняет роль исследовательской спецификации, архитектурного контракта, machine-readable handoff и backlog-пакета по LEGO-методу.

Цели документа:
- зафиксировать все инварианты времени, данных и исполнения;
- дать команде разработки достаточно мелкую декомпозицию задач;
- включить в единый артефакт YAML-конфиги, схемы таблиц, формулы features, acceptance tests и псевдокод всех pipeline stages;
- сделать проект воспроизводимым, проверяемым и пригодным для демонстрации на quant/ML hiring уровне.

## 2. Базовая постановка

- Asset class: US listed common equities.
- Частота: daily.
- Decision timestamp: после `close_t`.
- Execution timestamp: `open_{t+1}`.
- Основная задача: cross-sectional regression/ranking for next `1d` and `5d` residual/excess returns.
- Портфель: market-neutral long/short.
- Backtest: gross и net of costs.
- Обязательные блоки: PIT, purge/embargo, costs, capacity, regime analysis, decay, robustness, leakage guards.

## 3. Non-negotiable invariants

- `future_data_forbidden`
- `point_in_time_required`
- `test_fold_is_never_touched_during_fit_or_tuning`
- `execution_on_same_bar_is_forbidden_in_baseline`
- `out_of_fold_predictions_only_for_backtest`

Дополнительно:
- запрещено строить universe по будущему знанию о выживших бумагах;
- запрещено тюнить гиперпараметры на test fold;
- запрещено считать финальный backtest на in-sample predictions;
- запрещено скрывать деградацию сигнала после costs;
- любой артефакт должен быть привязан к config hash, dataset version и git commit.

## 4. Репозиторий и слои данных

Проект строится как layered system:
1. raw
2. bronze
3. silver
4. gold
5. folds
6. OOF predictions
7. portfolio targets / executions
8. daily states / holdings
9. reports

Стандартная структура каталогов:

```text
alpha_research/
  configs/
  data/raw/
  data/bronze/
  data/silver/
  data/gold/
  schemas/
  tests/
  pseudocode/
  backlog/
  reports/
```

## 5. Семантика времени

- `trade_date = t` — торговая дата бара.
- `decision_timestamp(t)` — момент после полного закрытия рынка на дате `t`.
- `execution_timestamp(t)` — `open_{t+1}`.
- `available_from` — earliest permissible timestamp для любого fundamental datum.
- `label_start` — не раньше execution timestamp.

Никогда не использовать `fiscal_period_end` как `available_from`.

## 6. Полные схемы таблиц с типами полей

### raw_market_request_manifest

| Поле | Тип | Nullable | Описание |
|---|---|---:|---|
| `request_id` | `string` | нет | Уникальный идентификатор запроса к провайдеру |
| `provider_name` | `string` | нет | Имя провайдера |
| `endpoint_name` | `string` | нет | Имя endpoint |
| `symbols_requested` | `array<string>` | нет | Список запрошенных тикеров |
| `start_date` | `date` | нет | Начало периода |
| `end_date` | `date` | нет | Конец периода |
| `fetched_at_utc` | `timestamp` | нет | Время загрузки |
| `payload_path` | `string` | нет | Путь до raw payload |
| `row_count_raw` | `int64` | нет | Количество сырых строк |
| `checksum` | `string` | нет | Контрольная сумма |

### raw_market_payload

| Поле | Тип | Nullable | Описание |
|---|---|---:|---|
| `provider_symbol` | `string` | нет | Идентификатор тикера у провайдера |
| `trade_date` | `date` | нет | Торговая дата |
| `open` | `float64` | да | Цена открытия |
| `high` | `float64` | да | Максимум |
| `low` | `float64` | да | Минимум |
| `close` | `float64` | да | Цена закрытия |
| `adj_close` | `float64` | да | Скорректированная цена закрытия |
| `volume` | `int64` | да | Объем |
| `currency` | `string` | да | Валюта |
| `raw_payload_version` | `string` | нет | Версия сырого пакета |

### security_master

| Поле | Тип | Nullable | Описание |
|---|---|---:|---|
| `security_id` | `string` | нет | Внутренний стабильный идентификатор бумаги |
| `symbol` | `string` | нет | Текущий отображаемый тикер |
| `security_type` | `string` | нет | Тип инструмента |
| `exchange` | `string` | да | Биржа листинга |
| `listing_date` | `date` | да | Дата листинга |
| `delisting_date` | `date` | да | Дата делистинга |
| `sector` | `string` | да | Сектор |
| `industry` | `string` | да | Индустрия |
| `country` | `string` | да | Страна |
| `currency` | `string` | да | Базовая валюта |
| `is_common_stock` | `bool` | нет | Флаг обычной акции |

### bronze_market_daily

| Поле | Тип | Nullable | Описание |
|---|---|---:|---|
| `security_id` | `string` | нет | Внутренний идентификатор бумаги |
| `symbol` | `string` | нет | Тикер на дату |
| `trade_date` | `date` | нет | Торговая дата |
| `open` | `float64` | да | Открытие |
| `high` | `float64` | да | Максимум |
| `low` | `float64` | да | Минимум |
| `close` | `float64` | да | Закрытие |
| `adj_close` | `float64` | да | Adjusted close |
| `volume` | `int64` | да | Объем |
| `currency` | `string` | да | Валюта |
| `provider_name` | `string` | нет | Провайдер |
| `data_version` | `string` | нет | Версия датасета |

### bronze_fundamentals

| Поле | Тип | Nullable | Описание |
|---|---|---:|---|
| `security_id` | `string` | нет | Внутренний идентификатор бумаги |
| `source_company_id` | `string` | нет | Идентификатор эмитента у источника |
| `form_type` | `string` | да | Тип формы |
| `filing_date` | `date` | да | Дата filing |
| `acceptance_datetime` | `timestamp` | да | Время принятия filing |
| `fiscal_period_end` | `date` | да | Конец отчетного периода |
| `metric_name_raw` | `string` | нет | Сырое имя метрики |
| `metric_name_canonical` | `string` | нет | Каноническое имя метрики |
| `metric_value` | `float64` | да | Значение метрики |
| `metric_unit` | `string` | да | Единица измерения |
| `statement_type` | `string` | да | Тип отчета |
| `available_from` | `timestamp` | нет | Точка времени доступности |
| `is_restatement` | `bool` | нет | Флаг рестейтмента |
| `data_version` | `string` | нет | Версия датасета |

### bronze_corporate_actions

| Поле | Тип | Nullable | Описание |
|---|---|---:|---|
| `security_id` | `string` | нет | Идентификатор бумаги |
| `event_type` | `string` | нет | Тип события |
| `event_date` | `date` | да | Дата события |
| `effective_date` | `date` | да | Дата вступления в силу |
| `split_ratio` | `float64` | да | Коэффициент сплита |
| `dividend_amount` | `float64` | да | Дивиденд |
| `delisting_code` | `string` | да | Код делистинга |
| `old_symbol` | `string` | да | Старый тикер |
| `new_symbol` | `string` | да | Новый тикер |
| `data_version` | `string` | нет | Версия датасета |

### silver_market_pit

| Поле | Тип | Nullable | Описание |
|---|---|---:|---|
| `security_id` | `string` | нет | Идентификатор бумаги |
| `trade_date` | `date` | нет | Торговая дата |
| `open` | `float64` | да | Открытие |
| `high` | `float64` | да | Максимум |
| `low` | `float64` | да | Минимум |
| `close` | `float64` | да | Закрытие |
| `adj_close` | `float64` | да | Adjusted close |
| `volume` | `int64` | да | Объем |
| `dollar_volume` | `float64` | да | close * volume |
| `is_price_valid` | `bool` | нет | Флаг валидности цены |
| `is_volume_valid` | `bool` | нет | Флаг валидности объема |
| `tradable_flag_prelim` | `bool` | нет | Предварительная торгуемость |
| `data_quality_score` | `float64` | нет | Скор качества строки |
| `data_version` | `string` | нет | Версия датасета |

### silver_fundamentals_pit

| Поле | Тип | Nullable | Описание |
|---|---|---:|---|
| `security_id` | `string` | нет | Идентификатор бумаги |
| `available_from` | `timestamp` | нет | Начало интервала доступности |
| `available_to` | `timestamp` | да | Конец интервала доступности |
| `metric_name_canonical` | `string` | нет | Метрика |
| `metric_value` | `float64` | да | Значение |
| `is_latest_known_as_of_date` | `bool` | нет | Флаг последнего факта |
| `staleness_days` | `int32` | да | Давность в днях |
| `is_restatement` | `bool` | нет | Флаг рестейтмента |
| `data_version` | `string` | нет | Версия датасета |

### universe_snapshot

| Поле | Тип | Nullable | Описание |
|---|---|---:|---|
| `date` | `date` | нет | Дата среза universe |
| `security_id` | `string` | нет | Бумага |
| `is_in_universe` | `bool` | нет | Флаг включения |
| `exclusion_reason_code` | `string` | да | Код причины исключения |
| `price_t` | `float64` | да | Цена |
| `adv20_usd_t` | `float64` | да | ADV20 в USD |
| `feature_coverage_ratio` | `float64` | да | Покрытие фичами |
| `data_quality_score` | `float64` | да | Скор качества |
| `liquidity_bucket` | `string` | да | Бакет ликвидности |

### gold_model_panel

| Поле | Тип | Nullable | Описание |
|---|---|---:|---|
| `date` | `date` | нет | Торговая дата |
| `security_id` | `string` | нет | Бумага |
| `symbol` | `string` | нет | Тикер |
| `is_in_universe` | `bool` | нет | Флаг участия |
| `sector` | `string` | да | Сектор |
| `industry` | `string` | да | Индустрия |
| `liquidity_bucket` | `string` | да | Бакет ликвидности |
| `beta_estimate` | `float64` | да | Оценка беты |
| `feature_vector_version` | `string` | нет | Версия набора фичей |
| `label_family_version` | `string` | нет | Версия набора label |
| `row_valid_flag` | `bool` | нет | Валидность строки |
| `row_drop_reason` | `string` | да | Причина отброса |

### oof_predictions

| Поле | Тип | Nullable | Описание |
|---|---|---:|---|
| `date` | `date` | нет | Дата прогноза |
| `security_id` | `string` | нет | Бумага |
| `fold_id` | `string` | нет | Фолд |
| `model_name` | `string` | нет | Модель |
| `raw_prediction` | `float64` | да | Сырой score |
| `rank_prediction` | `float64` | да | Ранг/процентиль |
| `bucket_prediction` | `int32` | да | Бакет score |
| `prediction_timestamp` | `timestamp` | нет | Время генерации |
| `dataset_version` | `string` | нет | Версия датасета |
| `config_hash` | `string` | нет | Хеш конфига |

### portfolio_daily_state

| Поле | Тип | Nullable | Описание |
|---|---|---:|---|
| `date` | `date` | нет | Дата |
| `gross_exposure` | `float64` | нет | Валовая экспозиция |
| `net_exposure` | `float64` | нет | Чистая экспозиция |
| `turnover` | `float64` | нет | Дневной turnover |
| `gross_pnl` | `float64` | нет | Валовый PnL |
| `net_pnl` | `float64` | нет | Чистый PnL |
| `commission_cost` | `float64` | нет | Комиссии |
| `spread_cost` | `float64` | нет | Издержки спреда |
| `slippage_cost` | `float64` | нет | Слиппедж |
| `impact_cost` | `float64` | нет | Импакт |
| `borrow_cost` | `float64` | нет | Borrow |
| `active_positions` | `int32` | нет | Число позиций |
| `aum` | `float64` | нет | Текущее AUM |

### capacity_results

| Поле | Тип | Nullable | Описание |
|---|---|---:|---|
| `aum_level` | `float64` | нет | Уровень AUM |
| `scenario` | `string` | нет | Сценарий participation |
| `net_sharpe` | `float64` | да | Net Sharpe |
| `median_participation` | `float64` | да | Медианное участие в ADV |
| `p95_participation` | `float64` | да | 95-й перцентиль участия |
| `fraction_trades_clipped` | `float64` | да | Доля обрезанных сделок |
| `fraction_names_untradable` | `float64` | да | Доля неторгуемых имен |

## 7. Спецификация labels

Основные формулы labels:

- `label_raw_1d_oo(t) = open_{t+2} / open_{t+1} - 1`
- `label_raw_5d_oo(t) = open_{t+6} / open_{t+1} - 1`
- `label_excess_Hd_oo(t) = label_raw_Hd_oo(t) - benchmark_return(open_{t+1} -> open_{t+1+H})`
- `label_resid_Hd_oo(t)` — residual cross-sectional regression на controls `[benchmark_return, sector_dummies, beta_estimate]` в дату `t`.
- `label_binary_top_bottom_Hd(t)` — `1` для top-quantile, `0` для bottom-quantile, `null` для middle bucket.
- `label_multiclass_quantile_Hd(t)` — номер квантильного бакета `0..Q-1`.

Правило overlap:
- для horizons > 1 day допускается overlap только при активированном purge/embargo;
- purge_days и embargo_days должны быть не меньше максимального live horizon baseline-модели.

## 8. Полный registry features с формулами 1-в-1

### Семейство: returns

| Feature | Формула | Входы | Примечание |
|---|---|---|---|
| `ret_1` | `ret_1(t) = close_t / close_(t-1) - 1` | `close` | Используется только если решение принимается после close_t. |
| `ret_2` | `ret_2(t) = close_t / close_(t-2) - 1` | `close` | Используется только если решение принимается после close_t. |
| `ret_3` | `ret_3(t) = close_t / close_(t-3) - 1` | `close` | Используется только если решение принимается после close_t. |
| `ret_5` | `ret_5(t) = close_t / close_(t-5) - 1` | `close` | Используется только если решение принимается после close_t. |
| `ret_10` | `ret_10(t) = close_t / close_(t-10) - 1` | `close` | Используется только если решение принимается после close_t. |
| `ret_21` | `ret_21(t) = close_t / close_(t-21) - 1` | `close` | Используется только если решение принимается после close_t. |
| `ret_63` | `ret_63(t) = close_t / close_(t-63) - 1` | `close` | Используется только если решение принимается после close_t. |
| `ret_126` | `ret_126(t) = close_t / close_(t-126) - 1` | `close` | Используется только если решение принимается после close_t. |
| `ret_252` | `ret_252(t) = close_t / close_(t-252) - 1` | `close` | Используется только если решение принимается после close_t. |
| `mom_5_ex1` | `mom_5_ex1(t) = close_(t-1) / close_(t-6) - 1` | `close` | Momentum без последнего дня, чтобы отделить эффект short-term reversal. |
| `mom_10_ex1` | `mom_10_ex1(t) = close_(t-1) / close_(t-11) - 1` | `close` | Momentum без последнего дня, чтобы отделить эффект short-term reversal. |
| `mom_21_ex1` | `mom_21_ex1(t) = close_(t-1) / close_(t-22) - 1` | `close` | Momentum без последнего дня, чтобы отделить эффект short-term reversal. |
| `mom_63_ex1` | `mom_63_ex1(t) = close_(t-1) / close_(t-64) - 1` | `close` | Momentum без последнего дня, чтобы отделить эффект short-term reversal. |
| `mom_126_ex1` | `mom_126_ex1(t) = close_(t-1) / close_(t-127) - 1` | `close` | Momentum без последнего дня, чтобы отделить эффект short-term reversal. |
| `mom_252_ex1` | `mom_252_ex1(t) = close_(t-1) / close_(t-253) - 1` | `close` | Momentum без последнего дня, чтобы отделить эффект short-term reversal. |
| `rev_1` | `rev_1(t) = - ret_1(t)` | `ret_1` | Reversal score как отрицание короткого дохода. |
| `rev_2` | `rev_2(t) = - ret_2(t)` | `ret_2` | Reversal score как отрицание короткого дохода. |
| `rev_5` | `rev_5(t) = - ret_5(t)` | `ret_5` | Reversal score как отрицание короткого дохода. |

### Семейство: relative_returns

| Feature | Формула | Входы | Примечание |
|---|---|---|---|
| `ex_bench_5` | `ex_bench_5(t) = ret_5(stock,t) - ret_5(benchmark,t)` | `close, benchmark_close` | Избыточная доходность к бенчмарку. |
| `ex_sector_5` | `ex_sector_5(t) = ret_5(stock,t) - median(ret_5(sector peers,t))` | `ret_n, sector` | Относительная доходность к медиане сектора. |
| `ex_bench_21` | `ex_bench_21(t) = ret_21(stock,t) - ret_21(benchmark,t)` | `close, benchmark_close` | Избыточная доходность к бенчмарку. |
| `ex_sector_21` | `ex_sector_21(t) = ret_21(stock,t) - median(ret_21(sector peers,t))` | `ret_n, sector` | Относительная доходность к медиане сектора. |
| `ex_bench_63` | `ex_bench_63(t) = ret_63(stock,t) - ret_63(benchmark,t)` | `close, benchmark_close` | Избыточная доходность к бенчмарку. |
| `ex_sector_63` | `ex_sector_63(t) = ret_63(stock,t) - median(ret_63(sector peers,t))` | `ret_n, sector` | Относительная доходность к медиане сектора. |

### Семейство: volatility

| Feature | Формула | Входы | Примечание |
|---|---|---|---|
| `vol_5` | `vol_5(t) = std(log(close_i / close_(i-1))) for i in [t-5+1, ..., t]` | `close` | Обычная реализованная волатильность. |
| `vol_10` | `vol_10(t) = std(log(close_i / close_(i-1))) for i in [t-10+1, ..., t]` | `close` | Обычная реализованная волатильность. |
| `vol_21` | `vol_21(t) = std(log(close_i / close_(i-1))) for i in [t-21+1, ..., t]` | `close` | Обычная реализованная волатильность. |
| `vol_63` | `vol_63(t) = std(log(close_i / close_(i-1))) for i in [t-63+1, ..., t]` | `close` | Обычная реализованная волатильность. |
| `down_vol_21` | `down_vol_21(t) = std(min(log_ret_i, 0)) over last 21 trading days` | `close` | Волатильность только по отрицательным доходам. |
| `up_vol_21` | `up_vol_21(t) = std(max(log_ret_i, 0)) over last 21 trading days` | `close` | Волатильность только по положительным доходам. |
| `down_vol_63` | `down_vol_63(t) = std(min(log_ret_i, 0)) over last 63 trading days` | `close` | Волатильность только по отрицательным доходам. |
| `up_vol_63` | `up_vol_63(t) = std(max(log_ret_i, 0)) over last 63 trading days` | `close` | Волатильность только по положительным доходам. |
| `hl_range_21` | `hl_range_21(t) = mean((high_i - low_i) / close_i) for i in [t-20, ..., t]` | `high, low, close` | Средний intraday range. |
| `parkinson_21` | `parkinson_21(t) = sqrt((1 / (4 * 21 * ln(2))) * sum((ln(high_i / low_i))^2))` | `high, low` | Range-based volatility estimator. |
| `gk_21` | `gk_21(t) = sqrt((1 / 21) * sum(0.5 * (ln(high_i / low_i))^2 - (2ln2 - 1) * (ln(close_i / open_i))^2))` | `open, high, low, close` | Garman-Klass volatility estimator. |
| `atr_14` | `atr_14(t) = mean(TR_i) over last 14 days, where TR_i = max(high_i-low_i, abs(high_i-close_(i-1)), abs(low_i-close_(i-1)))` | `high, low, close` | ATR-like volatility proxy. |

### Семейство: liquidity

| Feature | Формула | Входы | Примечание |
|---|---|---|---|
| `log_volume_1` | `log_volume_1(t) = ln(1 + volume_t)` | `volume` |  |
| `log_dollar_volume_1` | `log_dollar_volume_1(t) = ln(1 + close_t * volume_t)` | `close, volume` |  |
| `adv5` | `adv5(t) = mean(close_i * volume_i) for i in [t-5+1, ..., t]` | `close, volume` | Средний дневной долларовый объем. |
| `adv20` | `adv20(t) = mean(close_i * volume_i) for i in [t-20+1, ..., t]` | `close, volume` | Средний дневной долларовый объем. |
| `adv60` | `adv60(t) = mean(close_i * volume_i) for i in [t-60+1, ..., t]` | `close, volume` | Средний дневной долларовый объем. |
| `volume_surprise_5` | `volume_surprise_5(t) = volume_t / mean(volume_i) for i in [t-5, ..., t-1]` | `volume` |  |
| `volume_surprise_20` | `volume_surprise_20(t) = volume_t / mean(volume_i) for i in [t-20, ..., t-1]` | `volume` |  |
| `amihud_21` | `amihud_21(t) = mean(abs(ret_1(i)) / (close_i * volume_i)) over last 21 days` | `close, volume, ret_1` | Прокси price impact / illiquidity. |
| `turnover_proxy_21` | `turnover_proxy_21(t) = mean(volume_i / shares_outstanding_i) over last 21 days` | `volume, shares_outstanding` | Если shares_outstanding недоступен, используется proxy из float shares или пропуск. |
| `zero_volume_rate_21` | `zero_volume_rate_21(t) = mean(1(volume_i == 0)) over last 21 days` | `volume` |  |
| `liquidity_rank_20` | `liquidity_rank_20(t) = percentile_rank(adv20_t within universe on date t)` | `adv20` | Cross-sectional liquidity percentile. |

### Семейство: trend_state

| Feature | Формула | Входы | Примечание |
|---|---|---|---|
| `px_to_ma20` | `px_to_ma20(t) = close_t / mean(close_i for i in [t-20+1, ..., t]) - 1` | `close` |  |
| `px_to_ma50` | `px_to_ma50(t) = close_t / mean(close_i for i in [t-50+1, ..., t]) - 1` | `close` |  |
| `px_to_ma100` | `px_to_ma100(t) = close_t / mean(close_i for i in [t-100+1, ..., t]) - 1` | `close` |  |
| `px_to_ma200` | `px_to_ma200(t) = close_t / mean(close_i for i in [t-200+1, ..., t]) - 1` | `close` |  |
| `ma20_to_ma50` | `ma20_to_ma50(t) = MA20_t / MA50_t - 1` | `close` |  |
| `ma50_to_ma200` | `ma50_to_ma200(t) = MA50_t / MA200_t - 1` | `close` |  |
| `dist_to_20d_high` | `dist_to_20d_high(t) = close_t / max(high_i over last 20 days) - 1` | `close, high` |  |
| `dist_to_20d_low` | `dist_to_20d_low(t) = close_t / min(low_i over last 20 days) - 1` | `close, low` |  |
| `dist_to_52w_high` | `dist_to_52w_high(t) = close_t / max(high_i over last 252 days) - 1` | `close, high` |  |
| `dist_to_52w_low` | `dist_to_52w_low(t) = close_t / min(low_i over last 252 days) - 1` | `close, low` |  |
| `breakout_20d_up` | `breakout_20d_up(t) = 1 if close_t > max(high_i over [t-20, ..., t-1]) else 0` | `close, high` |  |
| `breakout_20d_down` | `breakout_20d_down(t) = 1 if close_t < min(low_i over [t-20, ..., t-1]) else 0` | `close, low` |  |

### Семейство: cross_sectional_context

| Feature | Формула | Входы | Примечание |
|---|---|---|---|
| `cs_rank_ret_5` | `cs_rank_ret_5(t) = percentile_rank(ret_5 across universe on date t)` | `ret_5` | Cross-sectional percentile. |
| `cs_rank_ret_21` | `cs_rank_ret_21(t) = percentile_rank(ret_21 across universe on date t)` | `ret_21` | Cross-sectional percentile. |
| `cs_rank_ret_63` | `cs_rank_ret_63(t) = percentile_rank(ret_63 across universe on date t)` | `ret_63` | Cross-sectional percentile. |
| `cs_rank_vol_21` | `cs_rank_vol_21(t) = percentile_rank(vol_21 across universe on date t)` | `vol_21` | Cross-sectional percentile. |
| `cs_rank_adv20` | `cs_rank_adv20(t) = percentile_rank(adv20 across universe on date t)` | `adv20` | Cross-sectional percentile. |
| `sector_rank_ret_21` | `sector_rank_ret_21(t) = percentile_rank(ret_21 across same sector on date t)` | `ret_21, sector` | Sector-neutral percentile. |
| `sector_rank_vol_21` | `sector_rank_vol_21(t) = percentile_rank(vol_21 across same sector on date t)` | `vol_21, sector` | Sector-neutral percentile. |
| `sector_rank_adv20` | `sector_rank_adv20(t) = percentile_rank(adv20 across same sector on date t)` | `adv20, sector` | Sector-neutral percentile. |

### Семейство: fundamentals

| Feature | Формула | Входы | Примечание |
|---|---|---|---|
| `book_to_price` | `book_to_price(t) = book_equity_t / market_cap_t` | `book_equity, market_cap` | Value factor. |
| `earnings_yield` | `earnings_yield(t) = net_income_ttm_t / market_cap_t` | `net_income_ttm, market_cap` | Inverse P/E proxy. |
| `sales_yield` | `sales_yield(t) = revenue_ttm_t / market_cap_t` | `revenue_ttm, market_cap` | Inverse P/S proxy. |
| `cashflow_yield` | `cashflow_yield(t) = operating_cashflow_ttm_t / market_cap_t` | `operating_cashflow_ttm, market_cap` | Cash-flow based value factor. |
| `roe` | `roe(t) = net_income_ttm_t / average_book_equity_t` | `net_income_ttm, average_book_equity` | Return on equity. |
| `roa` | `roa(t) = net_income_ttm_t / average_total_assets_t` | `net_income_ttm, average_total_assets` | Return on assets. |
| `gross_profitability` | `gross_profitability(t) = gross_profit_ttm_t / total_assets_t` | `gross_profit_ttm, total_assets` | Quality factor per Novy-Marx style intuition. |
| `operating_margin` | `operating_margin(t) = operating_income_ttm_t / revenue_ttm_t` | `operating_income_ttm, revenue_ttm` | Operating efficiency. |
| `accruals` | `accruals(t) = (net_income_ttm_t - operating_cashflow_ttm_t) / total_assets_t` | `net_income_ttm, operating_cashflow_ttm, total_assets` | Accrual quality proxy. |
| `sales_growth_yoy` | `sales_growth_yoy(t) = revenue_ttm_t / revenue_ttm_(t-252) - 1` | `revenue_ttm` | YoY growth using last available PIT data. |
| `earnings_growth_yoy` | `earnings_growth_yoy(t) = net_income_ttm_t / net_income_ttm_(t-252) - 1` | `net_income_ttm` | YoY earnings growth. |
| `asset_growth_yoy` | `asset_growth_yoy(t) = total_assets_t / total_assets_(t-252) - 1` | `total_assets` | Balance sheet growth factor. |
| `debt_to_equity` | `debt_to_equity(t) = total_debt_t / book_equity_t` | `total_debt, book_equity` | Leverage ratio. |
| `interest_coverage` | `interest_coverage(t) = ebit_ttm_t / interest_expense_ttm_t` | `ebit_ttm, interest_expense_ttm` | Solvency proxy. |
| `current_ratio` | `current_ratio(t) = current_assets_t / current_liabilities_t` | `current_assets, current_liabilities` | Liquidity ratio. |

### Семейство: staleness_flags

| Feature | Формула | Входы | Примечание |
|---|---|---|---|
| `days_since_last_filing` | `days_since_last_filing(t) = trading_days_between(date t and latest available filing date <= t)` | `available_from` |  |
| `fundamental_staleness_90` | `fundamental_staleness_90(t) = 1 if days_since_last_filing(t) > 90 else 0` | `days_since_last_filing` |  |
| `fundamental_staleness_180` | `fundamental_staleness_180(t) = 1 if days_since_last_filing(t) > 180 else 0` | `days_since_last_filing` |  |
| `missing_book_to_price_flag` | `missing_book_to_price_flag(t) = 1 if book_to_price is null else 0` | `book_to_price` |  |
| `missing_quality_flag` | `missing_quality_flag(t) = 1 if any(core quality feature is null) else 0` | `roe, roa, gross_profitability` |  |

### Семейство: interactions

| Feature | Формула | Входы | Примечание |
|---|---|---|---|
| `mom_21_ex1_x_liquidity_rank_20` | `mom_21_ex1_x_liquidity_rank_20(t) = mom_21_ex1(t) * liquidity_rank_20(t)` | `mom_21_ex1, liquidity_rank_20` | Интеракционная feature, подлежащая отдельной ablation-проверке. |
| `rev_1_x_vol_21` | `rev_1_x_vol_21(t) = rev_1(t) * vol_21(t)` | `rev_1, vol_21` | Интеракционная feature, подлежащая отдельной ablation-проверке. |
| `book_to_price_x_roe` | `book_to_price_x_roe(t) = book_to_price(t) * roe(t)` | `book_to_price, roe` | Интеракционная feature, подлежащая отдельной ablation-проверке. |
| `px_to_ma50_x_vol_21` | `px_to_ma50_x_vol_21(t) = px_to_ma50(t) * vol_21(t)` | `px_to_ma50, vol_21` | Интеракционная feature, подлежащая отдельной ablation-проверке. |
| `earnings_yield_x_liquidity_rank_20` | `earnings_yield_x_liquidity_rank_20(t) = earnings_yield(t) * liquidity_rank_20(t)` | `earnings_yield, liquidity_rank_20` | Интеракционная feature, подлежащая отдельной ablation-проверке. |

## 9. Подробные YAML-конфиги

Все критические решения вынесены в YAML. Ниже включены канонические шаблоны.

### project.yaml

```yaml
project_name: alpha_research_platform
project_code: ARP-US-Daily-CS-01
language: ru
market: us_equities
frequency: daily
timezone: America/New_York
decision_timestamp_policy: after_close_t
execution_timestamp_policy: next_open_t_plus_1
base_currency: USD
default_random_seed: 42
tracking:
  backend: mlflow
  tracking_uri: ./mlruns
  log_git_commit: true
  log_dataset_manifest: true
  log_config_snapshot: true
  log_artifacts: true
storage:
  raw_format: json_or_csv_as_received
  normalized_format: parquet
  compression: zstd
  schema_versioning: true
global_invariants:
- future_data_forbidden
- point_in_time_required
- test_fold_is_never_touched_during_fit_or_tuning
- execution_on_same_bar_is_forbidden_in_baseline
- out_of_fold_predictions_only_for_backtest
```

### data_sources.yaml

```yaml
market_provider:
  name: adapter_placeholder
  priority:
  - institutional_vendor
  - polygon_like
  - alpha_vantage_like
  fields_required:
  - open
  - high
  - low
  - close
  - adj_close
  - volume
  - symbol
  - trade_date
  save_raw_payload: true
  save_request_manifest: true
fundamentals_provider:
  name: sec_or_vendor_adapter
  fields_required:
  - filing_date
  - acceptance_datetime
  - fiscal_period_end
  - metric_name
  - metric_value
  - form_type
  - company_id
  available_from_policy: max(acceptance_datetime, filing_date_end_of_day)
  restatement_tracking: true
corporate_actions_provider:
  required_events:
  - split
  - dividend
  - delisting
  - symbol_change
  save_raw_payload: true
security_master_provider:
  required_fields:
  - security_id
  - symbol
  - listing_date
  - delisting_date
  - exchange
  - security_type
  ticker_is_not_primary_key: true
```

### calendar.yaml

```yaml
exchange_calendar: XNYS
use_half_days: true
functions_required:
- is_trading_day
- next_trading_day
- previous_trading_day
- trading_day_distance
- window_by_trading_days
forbid_calendar_day_shift_for_labels: true
```

### universe.yaml

```yaml
eligible_security_types:
- common_stock
excluded_security_types:
- ETF
- ETN
- ADR
- preferred
- warrant
- unit
- OTC
allowed_exchanges:
- NYSE
- NASDAQ
- AMEX
min_price_usd: 5.0
min_adv20_usd: 5000000
optional_min_market_cap_usd: 1000000000
min_feature_coverage_ratio: 0.7
min_data_quality_score: 0.8
liquidity_buckets:
  high: top_30_percent_by_adv20
  medium: middle_40_percent_by_adv20
  low: bottom_30_percent_by_adv20
membership_refresh: daily
log_exclusion_reasons: true
```

### labels.yaml

```yaml
primary_label: label_excess_5d_oo
secondary_labels:
- label_excess_1d_oo
- label_resid_5d_oo
- label_raw_5d_oo
execution_reference: open_t_plus_1
horizons_trading_days:
- 1
- 5
- 10
- 20
families:
- raw
- excess
- residual
- binary_quantile
- multiclass_quantile
overlap_policy:
  allow_overlap: true
  purge_days: 5
  embargo_days: 5
benchmark: SPY_like_proxy_or_index_return
residualization_controls:
- benchmark_return
- sector_dummies
- beta_estimate
```

### features.yaml

```yaml
feature_registry_version: v1
families_enabled:
- returns
- relative_returns
- volatility
- liquidity
- trend_state
- cross_sectional_context
- fundamentals
- staleness_flags
- interactions
default_cross_section_normalization: rank_gaussian_optional_else_percentile
default_missing_policy: add_missing_flag_plus_impute_by_sector_median_for_linear_models
default_winsor_policy:
  lower_pct: 0.5
  upper_pct: 99.5
default_neutralization: sector_and_beta
fundamental_staleness_thresholds_days:
- 45
- 90
- 180
- 365
interaction_cap: 25
```

### preprocessing.yaml

```yaml
winsorization_options:
- name: none
  enabled: false
- name: p1_p99
  enabled: true
  lower_pct: 1.0
  upper_pct: 99.0
- name: p0_5_p99_5
  enabled: true
  lower_pct: 0.5
  upper_pct: 99.5
scalers:
- zscore_by_date
- robust_zscore_by_date
- percentile_rank_by_date
neutralizers:
- none
- sector
- beta
- sector_plus_beta
missing_policies:
- leave_null_for_tree_models
- cross_section_median_impute
- sector_median_impute
- model_native_missing
fold_safe_fit_required: true
```

### models.yaml

```yaml
baseline_models:
- random_score
- heuristic_reversal_score
- heuristic_momentum_score
- heuristic_blend_score
- ridge_regression
- lasso_regression
advanced_models:
- gradient_boosting_regressor
- gradient_boosting_ranker
tuning:
  engine: optuna_or_internal_search
  n_trials_default: 50
  early_stopping_enabled: true
  optimize_metric: validation_rank_ic_mean
sample_weights:
  enabled: true
  policy: optional_inverse_vol_or_liquidity_capped
```

### splits.yaml

```yaml
train_years: 5
validation_months: 12
test_months: 3
step_months: 3
expanding_train: false
purge_days: 5
embargo_days: 5
nested_validation: true
min_train_observations: 100000
persist_fold_artifacts: true
```

### portfolio.yaml

```yaml
mode: decile_equal_weight
gross_exposure: 1.0
net_target: 0.0
long_quantile: 0.1
short_quantile: 0.1
rebalance_frequency: daily
holding_period_days: 5
overlap_sleeves: true
max_weight_per_name: 0.02
max_sector_net_exposure: 0.05
max_sector_gross_exposure: 0.2
max_turnover_per_rebalance: 0.25
beta_neutralize: true
sector_neutralize: true
max_participation_pct_adv: 0.01
reject_unborrowable_shorts: true
```

### costs.yaml

```yaml
commission_bps: 0.5
spread_proxy:
  method: bucket_by_price_and_adv
  buckets:
  - price_min: 5
    price_max: 10
    adv_bucket: low
    half_spread_bps: 15
  - price_min: 10
    price_max: 25
    adv_bucket: medium
    half_spread_bps: 8
  - price_min: 25
    price_max: 999999
    adv_bucket: high
    half_spread_bps: 3
slippage_proxy:
  method: participation_based
  formula: slippage_bps = base_bps + k1 * sqrt(order_notional / adv_notional)
  base_bps: 1.0
  k1: 20.0
impact_proxy:
  method: nonlinear_participation
  formula: impact_bps = k2 * sqrt(order_notional / adv_notional)
  k2: 15.0
borrow:
  low_borrow_bps_daily: 1.0
  medium_borrow_bps_daily: 5.0
  high_borrow_bps_daily: 20.0
  hard_to_borrow_policy: ban_or_extreme_stress
scenarios:
- optimistic
- base
- stressed
- severely_stressed
```

### capacity.yaml

```yaml
aum_ladder_usd:
- 1000000
- 5000000
- 10000000
- 25000000
- 50000000
- 100000000
- 250000000
- 500000000
- 1000000000
participation_limits:
  relaxed: 0.02
  base: 0.01
  strict: 0.005
  ultra_strict: 0.0025
report_metrics:
- net_sharpe
- max_participation
- median_participation
- fraction_trades_clipped
- fraction_names_untradable
```

### reporting.yaml

```yaml
formats:
- markdown
- html
include_sections:
- executive_summary
- time_semantics
- data_lineage
- feature_catalog
- validation_protocol
- model_comparison
- backtest_results
- cost_sensitivity
- capacity_analysis
- regime_analysis
- decay_analysis
- limitations
- next_steps
mandatory_figures:
- universe_size_over_time
- coverage_heatmap
- ic_over_time
- rolling_ic
- equity_curve_gross
- equity_curve_net
- drawdown_curve
- turnover_curve
- cost_decomposition
- exposure_curve
- capacity_curve
- decay_curve
```

### experiments/exp_baseline_linear.yaml

```yaml
experiment_name: baseline_linear_excess_5d
dataset_version: gold_latest
label: label_excess_5d_oo
featureset: all_minus_interactions
preprocessing:
  winsor: p0_5_p99_5
  scaler: zscore_by_date
  neutralizer: sector_plus_beta
model:
  name: ridge_regression
  alpha_grid:
  - 0.1
  - 1.0
  - 10.0
portfolio:
  mode: decile_equal_weight
cost_scenario: base
```

### experiments/exp_gbm_ranker.yaml

```yaml
experiment_name: gbm_ranker_excess_5d
dataset_version: gold_latest
label: label_excess_5d_oo
featureset: all_features_v1
preprocessing:
  winsor: p0_5_p99_5
  scaler: percentile_rank_by_date
  neutralizer: sector_plus_beta
model:
  name: gradient_boosting_ranker
  n_trials: 50
portfolio:
  mode: rank_weighted
cost_scenario: base
```

### experiments/exp_ablation_no_fundamentals.yaml

```yaml
experiment_name: ablation_no_fundamentals
dataset_version: gold_latest
label: label_excess_5d_oo
featureset: technical_liquidity_only
preprocessing:
  winsor: p1_p99
  scaler: robust_zscore_by_date
  neutralizer: sector
model:
  name: gradient_boosting_regressor
  n_trials: 30
portfolio:
  mode: decile_equal_weight
cost_scenario: base
```

### experiments/exp_cost_stress.yaml

```yaml
experiment_name: cost_stress_gbm_ranker
dataset_version: gold_latest
label: label_excess_5d_oo
featureset: all_features_v1
preprocessing:
  winsor: p0_5_p99_5
  scaler: percentile_rank_by_date
  neutralizer: sector_plus_beta
model:
  name: gradient_boosting_ranker
  use_best_previous_params: true
portfolio:
  mode: rank_weighted
cost_scenario: severely_stressed
```

## 10. Machine-readable spec

Ниже — сводный machine-readable spec. Полная версия также лежит отдельным файлом `machine_spec.yaml` в архиве.

```yaml
spec_version: '1.0'
project:
  name: alpha_research_platform
  scope: daily_cross_sectional_us_equities_alpha_research
  language: ru
  primary_use: master_spec_for_engineering_team
global_invariants:
- future_data_forbidden
- point_in_time_required
- test_fold_is_never_touched_during_fit_or_tuning
- execution_on_same_bar_is_forbidden_in_baseline
- out_of_fold_predictions_only_for_backtest
stage_dag:
- stage_id: S00
  name: bootstrap
  inputs: []
  outputs:
  - repo
  - configs
  - tooling
- stage_id: S01
  name: reference_data
  inputs:
  - security_master_raw
  outputs:
  - security_master_silver
- stage_id: S02
  name: market_ingest
  inputs:
  - provider_market_api
  outputs:
  - raw_market
  - bronze_market
- stage_id: S03
  name: fundamentals_ingest
  inputs:
  - provider_fundamentals_api
  outputs:
  - raw_fundamentals
  - bronze_fundamentals
- stage_id: S04
  name: corporate_actions
  inputs:
  - provider_ca_api
  outputs:
  - bronze_corporate_actions
- stage_id: S05
  name: qa
  inputs:
  - bronze_market
  - bronze_fundamentals
  - bronze_corporate_actions
  outputs:
  - qa_reports
  - silver_inputs
- stage_id: S06
  name: pit
  inputs:
  - silver_inputs
  - security_master_silver
  outputs:
  - silver_market_pit
  - silver_fundamentals_pit
- stage_id: S07
  name: universe
  inputs:
  - silver_market_pit
  - security_master_silver
  outputs:
  - universe_snapshots
- stage_id: S08
  name: features_labels
  inputs:
  - silver_market_pit
  - silver_fundamentals_pit
  - universe_snapshots
  outputs:
  - feature_layer
  - label_layer
- stage_id: S09
  name: gold_panel
  inputs:
  - feature_layer
  - label_layer
  outputs:
  - gold_model_panel
  - dataset_manifest
- stage_id: S10
  name: splits
  inputs:
  - gold_model_panel
  outputs:
  - folds
- stage_id: S11
  name: training
  inputs:
  - gold_model_panel
  - folds
  outputs:
  - models
  - oof_predictions
- stage_id: S12
  name: portfolio
  inputs:
  - oof_predictions
  - universe_snapshots
  outputs:
  - target_weights
  - trades
- stage_id: S13
  name: execution_backtest
  inputs:
  - trades
  - silver_market_pit
  outputs:
  - daily_state
  - holdings
  - net_returns
- stage_id: S14
  name: capacity
  inputs:
  - daily_state
  outputs:
  - capacity_results
- stage_id: S15
  name: evaluation_reporting
  inputs:
  - oof_predictions
  - daily_state
  - capacity_results
  outputs:
  - metrics
  - figures
  - final_report
modules:
  common:
  - logging
  - config
  - paths
  - hashing
  - manifest_helpers
  data:
  - providers
  - bronze_normalizers
  - qa
  pit:
  - asof_join
  - interval_builder
  - timestamp_guards
  universe:
  - filters
  - snapshots
  - exclusion_codes
  labels:
  - raw
  - excess
  - residual
  - quantile
  features:
  - returns
  - volatility
  - liquidity
  - trend
  - fundamentals
  - interactions
  preprocessing:
  - winsor
  - scale
  - neutralize
  - missing
  splits:
  - rolling
  - expanding
  - purge
  - embargo
  models:
  - baselines
  - linear
  - trees
  - ranking
  - tuning
  portfolio:
  - score_to_rank
  - constraints
  - weights
  - rejections
  execution:
  - trade_generation
  - fills
  - costs
  backtest:
  - state_machine
  - pnl
  - attribution
  evaluation:
  - predictive
  - portfolio
  - regime
  - decay
  - capacity
  reporting:
  - tables
  - plots
  - final_report
artifacts_required:
- dataset_manifest
- feature_registry_snapshot
- fold_metadata
- oof_predictions
- holdings_snapshots
- daily_portfolio_state
- capacity_results
- figures
- final_report
cli_commands:
- ingest-market
- ingest-fundamentals
- ingest-corporate-actions
- build-reference
- build-silver
- build-universe
- build-features
- build-labels
- build-gold
- run-train
- run-predict-oof
- run-backtest
- run-capacity
- run-report
- run-full-pipeline
```

## 11. Полные acceptance tests

Acceptance tests нужно трактовать как release-gate. Провал любого leakage/system теста должен блокировать релиз.

### Группа: config_validation

- **TEST-01-01** — Невалидный project.yaml отклоняется schema validator-ом. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-01-02** — Hash конфига меняется при изменении любого параметра. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-01-03** — Experiment config сохраняет snapshot без потери полей. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-01-04** — CLI dry-run печатает resolved config без запуска side effects. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-01-05** — Отсутствующий mandatory field вызывает fail-fast. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-01-06** — Unknown extra field помечается warn или fail по policy. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.

### Группа: calendar_and_time

- **TEST-02-01** — next_trading_day пропускает выходные и праздники. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-02-02** — trading_day_distance корректен на диапазонах с праздниками. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-02-03** — label horizon использует торговые, а не календарные дни. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-02-04** — decision timestamp всегда раньше execution timestamp. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-02-05** — same-bar execution baseline guard срабатывает при нарушении. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-02-06** — timestamp alignment tests ловят неверный start-of-label window. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.

### Группа: market_ingest

- **TEST-03-01** — Raw payload сохраняется без мутаций. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-03-02** — Request manifest создается для каждого batch. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-03-03** — Повторный ingest не ломает idempotency policy. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-03-04** — Pagination не теряет страницы данных. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-03-05** — Provider-side missing symbols логируются отдельно. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-03-06** — Bronze schema валидируется после ingest. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.

### Группа: fundamentals_ingest

- **TEST-04-01** — available_from рассчитывается по policy. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-04-02** — fiscal_period_end не используется как available_from. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-04-03** — Restatement помечается отдельным флагом. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-04-04** — Duplicate facts выявляются и логируются. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-04-05** — Canonical metric names маппятся детерминированно. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-04-06** — Bronze fundamentals schema валидируется. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.

### Группа: corporate_actions

- **TEST-05-01** — Split ratios загружаются и нормализуются. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-05-02** — Dividend events присоединяются к security_id. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-05-03** — Delisting events попадают в canonical layer. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-05-04** — Symbol changes не теряются при нормализации. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-05-05** — Corporate actions manifest содержит row counts. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-05-06** — Invalid corporate action rows помечаются failed extract-ом. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.

### Группа: market_qa

- **TEST-06-01** — OHLC logical consistency check ловит high < low. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-06-02** — Negative volume детектируется как invalid. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-06-03** — Duplicate rows детектируются по security_id-date. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-06-04** — Missing trading day объясняется календарем либо flagged. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-06-05** — Extreme price jumps без action explanation flagged. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-06-06** — Data quality score рассчитывается и сохраняется. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.

### Группа: fundamentals_qa

- **TEST-07-01** — Непарсируемый metric value flagged. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-07-02** — Невалидный metric unit flagged. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-07-03** — Impossible timestamps flagged. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-07-04** — Completeness by metric/year рассчитывается. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-07-05** — Staleness diagnostics считаются корректно. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-07-06** — Fundamental QA report генерируется без пропуска секций. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.

### Группа: pit_engine

- **TEST-08-01** — As-of join не выбирает future row. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-08-02** — При отсутствии доступного факта возвращается null. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-08-03** — При наличии нескольких фактов берется максимальный available_from <= date. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-08-04** — Restated fact не утекает в прошлое. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-08-05** — Source timestamp сохраняется после PIT join. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-08-06** — PIT diagnostics report показывает coverage и null ratios. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.

### Группа: universe

- **TEST-09-01** — Security type filter исключает ETF/ADR/OTC. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-09-02** — Listing/delisting filter уважает дату среза. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-09-03** — Min price filter работает по point-in-time price. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-09-04** — Min ADV filter работает по point-in-time ADV20. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-09-05** — Exclusion reasons логируются детерминированно. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-09-06** — Universe snapshots воспроизводимы на фиксированном датасете. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.

### Группа: labels

- **TEST-10-01** — Open-to-open 1d label начинается после execution timestamp. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-10-02** — Open-to-open 5d label использует trading-day offsets. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-10-03** — Benchmark excess label корректно вычитает benchmark return. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-10-04** — Residual label использует только control variables текущей даты. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-10-05** — Overlap policy сигнализирует нужный purge horizon. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-10-06** — Label sanity report строится по всем horizons. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.

### Группа: features_price

- **TEST-11-01** — ret_21 соответствует формуле close_t/close_t-21 - 1. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-11-02** — mom_21_ex1 исключает последний день. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-11-03** — rev_1 равен отрицанию ret_1. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-11-04** — ex_bench_21 корректно вычитает benchmark. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-11-05** — cs_rank_ret_21 считается внутри даты. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-11-06** — Feature registry содержит metadata для price family. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.

### Группа: features_vol_liq

- **TEST-12-01** — vol_21 использует std log returns. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-12-02** — parkinson_21 соответствует range-based formula. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-12-03** — adv20 равен среднему dollar volume за 20 дней. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-12-04** — volume_surprise_20 использует только прошлые дни. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-12-05** — amihud_21 корректно обращается с нулевым volume. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-12-06** — Trend features генерируются без future leakage. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.

### Группа: features_fundamentals

- **TEST-13-01** — book_to_price использует PIT book equity и market cap. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-13-02** — roe использует average book equity policy. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-13-03** — sales_growth_yoy использует last available PIT values. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-13-04** — days_since_last_filing считается по trading calendar. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-13-05** — missingness flags выставляются корректно. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-13-06** — Interaction features подчиняются interaction cap policy. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.

### Группа: preprocessing

- **TEST-14-01** — Winsorizer не использует test fold при fit. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-14-02** — Z-score scaler считается по cross-section даты. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-14-03** — Robust z-score scaler устойчив к outliers. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-14-04** — Sector neutralization не ломает индекс строк. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-14-05** — Beta neutralization использует корректный beta input. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-14-06** — Fold-safe preprocessing API не имеет test contamination. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.

### Группа: dataset_assembly

- **TEST-15-01** — Silver market и fundamentals собираются в gold panel. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-15-02** — Rows без universe membership помечаются корректно. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-15-03** — Row-level diagnostics содержат drop reason. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-15-04** — Dataset manifest содержит row_count and feature_count. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-15-05** — Feature coverage ratio считается детерминированно. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-15-06** — Gold dataset пишется в parquet с версией. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.

### Группа: splits

- **TEST-16-01** — Rolling split generator создает train/valid/test без overlap. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-16-02** — Expanding split option увеличивает train window. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-16-03** — Purge logic убирает пересекающиеся label windows. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-16-04** — Embargo logic убирает близкие boundary observations. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-16-05** — Fold metadata сохраняется как artifact. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-16-06** — Validation protocol report содержит timeline plot. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.

### Группа: models_and_oof

- **TEST-17-01** — Random baseline дает near-zero predictive skill на sanity fixture. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-17-02** — Heuristic baseline запускается end-to-end. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-17-03** — Ridge/Lasso wrappers сериализуются. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-17-04** — Tuning engine не трогает test fold. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-17-05** — OOF prediction store уникален по date-security-model. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-17-06** — Prediction manifests содержат coverage by fold. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.

### Группа: portfolio_and_execution

- **TEST-18-01** — Score-to-rank mapping монотонен. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-18-02** — Equal-weight decile portfolio соблюдает gross target. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-18-03** — Sector caps enforce-ятся при target weight construction. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-18-04** — Participation cap режет слишком крупные сделки. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-18-05** — Trade list строится из previous holdings и target weights. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-18-06** — Next-open execution simulator пишет fill ratios. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.

### Группа: costs_backtest_capacity

- **TEST-19-01** — Commission model начисляет bps на executed notional. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-19-02** — Spread proxy использует bucket policy. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-19-03** — Borrow model начисляет cost только на shorts. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-19-04** — Backtest state machine обновляет holdings ежедневно. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-19-05** — AUM ladder runner генерирует результаты на всех уровнях капитала. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-19-06** — Capacity outputs содержат fraction_trades_clipped и net_sharpe. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.

### Группа: evaluation_reporting

- **TEST-20-01** — Predictive metrics suite считает IC и rank IC. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-20-02** — Portfolio metrics suite считает Sharpe and max drawdown. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-20-03** — Regime analysis suite считает метрики по режимам. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-20-04** — Decay suite строит response curve по horizons. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-20-05** — Final report generator включает все mandatory sections. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-20-06** — Executive summary template содержит limitations и next steps. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.

### Группа: leakage_and_release

- **TEST-21-01** — Leakage test ловит future feature timestamp. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-21-02** — Leakage test ловит scaler-on-all-data misuse. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-21-03** — Leakage test ловит same-bar execution misuse. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-21-04** — Regression tests на fixture dataset проходят стабильно. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-21-05** — CI pipeline падает при провале unit/integration/leakage tests. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.
- **TEST-21-06** — Release checklist требует manifests, reports и review bundle. Ожидаемый результат: `PASS`. Failure mode: `pipeline_stop_or_release_blocker`.

## 12. Псевдокод всех pipeline stages

# Псевдокод pipeline stages

Ниже собран высокоуровневый псевдокод для каждого обязательного stage.

## bootstrap_pipeline

```python
def bootstrap_project():
    assert repo_exists()
    load_project_config()
    validate_all_config_schemas()
    initialize_logger()
    initialize_tracking_backend()
    create_required_directories()
    write_bootstrap_manifest()
    return "bootstrap_ok"
```

## reference_data_pipeline

```python
def build_reference_layer(raw_reference):
    standardized = normalize_reference_fields(raw_reference)
    standardized = assign_or_validate_security_id(standardized)
    standardized = resolve_symbol_changes(standardized)
    standardized = validate_listing_intervals(standardized)
    standardized = enrich_sector_and_industry(standardized)
    quality = score_reference_quality(standardized)
    output = persist_silver_reference(standardized, quality)
    write_reference_manifest(output)
    return output
```

## market_ingest_pipeline

```python
def ingest_market_data(symbols, start_date, end_date):
    request_id = create_request_id()
    raw_payload = provider.fetch_market_data(symbols, start_date, end_date)
    persist_raw_payload(request_id, raw_payload)
    manifest = build_request_manifest(request_id, symbols, start_date, end_date, raw_payload)
    bronze = normalize_market_payload(raw_payload)
    validate_bronze_market_schema(bronze)
    persist_bronze_market(bronze, manifest)
    return bronze, manifest
```

## fundamentals_ingest_pipeline

```python
def ingest_fundamentals(company_ids, start_date, end_date):
    request_id = create_request_id()
    raw_payload = provider.fetch_fundamentals(company_ids, start_date, end_date)
    persist_raw_payload(request_id, raw_payload)
    parsed = parse_filing_payloads(raw_payload)
    parsed = map_metric_names_to_canonical(parsed)
    parsed["available_from"] = compute_available_from(parsed)
    parsed["is_restatement"] = detect_restatements(parsed)
    validate_bronze_fundamentals_schema(parsed)
    persist_bronze_fundamentals(parsed)
    return parsed
```

## corporate_actions_pipeline

```python
def ingest_corporate_actions(securities, start_date, end_date):
    raw_actions = provider.fetch_corporate_actions(securities, start_date, end_date)
    persist_raw_payload("corporate_actions", raw_actions)
    normalized = normalize_corporate_actions(raw_actions)
    normalized = attach_security_ids(normalized)
    validate_corporate_actions(normalized)
    persist_bronze_corporate_actions(normalized)
    return normalized
```

## qa_pipeline

```python
def run_qa(bronze_market, bronze_fundamentals, bronze_corporate_actions):
    market_report = run_market_qa(bronze_market)
    fundamentals_report = run_fundamentals_qa(bronze_fundamentals)
    ca_report = run_corporate_actions_qa(bronze_corporate_actions)
    assert market_report.status != "fatal"
    assert fundamentals_report.status != "fatal"
    silver_inputs = build_silver_inputs(bronze_market, bronze_fundamentals, bronze_corporate_actions)
    persist_qa_reports(market_report, fundamentals_report, ca_report)
    return silver_inputs
```

## pit_pipeline

```python
def build_pit_layers(silver_inputs, security_master):
    silver_market = build_silver_market(silver_inputs.market)
    silver_fundamentals = build_intervalized_fundamentals(silver_inputs.fundamentals)
    silver_fundamentals = add_available_to(silver_fundamentals)
    run_pit_non_leakage_tests(silver_fundamentals)
    persist_silver_market(silver_market)
    persist_silver_fundamentals_pit(silver_fundamentals)
    return silver_market, silver_fundamentals
```

## universe_pipeline

```python
def build_universe(date, silver_market, security_master, feature_coverage):
    candidates = select_reference_eligible(security_master, date)
    candidates = apply_listing_filters(candidates, date)
    candidates = join_market_fields(candidates, silver_market, date)
    candidates = apply_price_filter(candidates)
    candidates = apply_adv_filter(candidates)
    candidates = apply_quality_filter(candidates)
    candidates = apply_feature_coverage_filter(candidates, feature_coverage)
    universe = assign_liquidity_buckets(candidates)
    exclusions = capture_exclusion_reasons(candidates)
    persist_universe_snapshot(date, universe, exclusions)
    return universe
```

## features_pipeline

```python
def build_features_for_date(date, universe, silver_market, silver_fundamentals):
    panel = initialize_panel_for_date(date, universe)
    panel = add_return_features(panel, silver_market)
    panel = add_relative_return_features(panel, silver_market)
    panel = add_volatility_features(panel, silver_market)
    panel = add_liquidity_features(panel, silver_market)
    panel = add_trend_features(panel, silver_market)
    panel = asof_join_fundamentals(panel, silver_fundamentals, date)
    panel = add_fundamental_features(panel)
    panel = add_staleness_and_missing_flags(panel)
    panel = add_interaction_features(panel)
    validate_feature_ranges(panel)
    persist_raw_feature_panel(date, panel)
    return panel
```

## preprocessing_pipeline

```python
def preprocess_fold(train_df, valid_df, test_df, config):
    preproc = fit_preprocessing_only_on_train(train_df, config)
    train_out = apply_preprocessing(preproc, train_df)
    valid_out = apply_preprocessing(preproc, valid_df)
    test_out = apply_preprocessing(preproc, test_df)
    run_preprocessing_leakage_guards(preproc, train_df, valid_df, test_df)
    return train_out, valid_out, test_out, preproc
```

## labels_pipeline

```python
def build_labels(panel, market_data, benchmark_data, calendar, config):
    for horizon in config.horizons_trading_days:
        start_exec = calendar.next_trading_day(panel.date, 1)
        end_exec = calendar.next_trading_day(start_exec, horizon)
        panel[f"label_raw_{horizon}d_oo"] = compute_open_to_open_return(start_exec, end_exec)
        panel[f"label_excess_{horizon}d_oo"] = subtract_benchmark(panel[f"label_raw_{horizon}d_oo"], benchmark_data, start_exec, end_exec)
        panel[f"label_resid_{horizon}d_oo"] = residualize_cross_section(panel, panel[f"label_excess_{horizon}d_oo"])
    persist_label_layer(panel)
    return panel
```

## dataset_assembly_pipeline

```python
def build_gold_panel(dates, security_master, silver_market, silver_fundamentals, market_benchmark):
    all_rows = []
    for date in dates:
        universe = build_universe(date, silver_market, security_master, feature_coverage=None)
        features = build_features_for_date(date, universe, silver_market, silver_fundamentals)
        labels = build_labels(features.copy(), silver_market, market_benchmark, calendar, label_config)
        row = merge_features_and_labels(features, labels)
        row = add_row_diagnostics(row)
        all_rows.append(row)
    gold = concat_rows(all_rows)
    manifest = build_dataset_manifest(gold)
    persist_gold_panel(gold, manifest)
    return gold, manifest
```

## split_pipeline

```python
def generate_folds(dates, split_config):
    folds = []
    cursor = compute_initial_cursor(dates, split_config.train_years)
    while cursor < max(dates):
        train, valid, test = compute_window_ranges(cursor, split_config)
        train = apply_purge(train, valid, test, split_config.purge_days)
        train = apply_embargo(train, valid, test, split_config.embargo_days)
        assert no_date_overlap(train, valid, test)
        folds.append(make_fold_metadata(train, valid, test))
        cursor = advance_cursor(cursor, split_config.step_months)
    persist_fold_metadata(folds)
    return folds
```

## training_pipeline

```python
def train_models_on_folds(gold_panel, folds, model_registry):
    all_predictions = []
    for fold in folds:
        train_df, valid_df, test_df = materialize_fold(gold_panel, fold)
        train_df, valid_df, test_df, preproc = preprocess_fold(train_df, valid_df, test_df, preprocessing_config)
        for model_name in model_registry.enabled_models():
            model = model_registry.create(model_name)
            best_model = tune_model(model, train_df, valid_df)
            preds = score_test_fold(best_model, test_df)
            artifacts = collect_training_artifacts(best_model, fold, preproc, preds)
            persist_training_artifacts(artifacts)
            all_predictions.append(preds)
    oof = merge_all_predictions(all_predictions)
    persist_oof_predictions(oof)
    return oof
```

## portfolio_pipeline

```python
def build_portfolio_targets(date, oof_predictions, universe_snapshot, portfolio_config):
    preds = select_predictions_for_date(oof_predictions, date)
    preds = join_universe_and_risk(preds, universe_snapshot, date)
    preds = map_scores_to_ranks(preds)
    target = construct_target_weights(preds, portfolio_config)
    target = enforce_name_caps(target, portfolio_config)
    target = enforce_sector_caps(target, portfolio_config)
    target = enforce_beta_neutrality_if_needed(target, portfolio_config)
    rejected = capture_rejected_names(preds, target)
    persist_target_weights(date, target, rejected)
    return target, rejected
```

## execution_pipeline

```python
def simulate_execution(date, target_weights, previous_holdings, market_open_prices, cost_model):
    trades = generate_trade_list(target_weights, previous_holdings)
    trades = apply_participation_limits(trades, cost_model)
    executed = fill_at_next_open(trades, market_open_prices)
    costs = compute_trade_costs(executed, cost_model)
    new_holdings = update_holdings(previous_holdings, executed)
    persist_trade_and_fill_artifacts(date, trades, executed, costs, new_holdings)
    return new_holdings, costs
```

## backtest_pipeline

```python
def run_backtest(dates, oof_predictions, market_data, portfolio_config, cost_model):
    holdings = empty_portfolio()
    states = []
    for date in dates:
        target, rejected = build_portfolio_targets(date, oof_predictions, universe_snapshots, portfolio_config)
        holdings, costs = simulate_execution(date, target, holdings, market_data.open_prices, cost_model)
        pnl = mark_to_market(holdings, market_data, date)
        state = build_daily_state(date, holdings, pnl, costs, rejected)
        persist_daily_state(state)
        states.append(state)
    results = aggregate_backtest(states)
    return results
```

## capacity_pipeline

```python
def run_capacity_analysis(backtest_inputs, capacity_config):
    outputs = []
    for aum in capacity_config.aum_ladder_usd:
        for scenario_name, max_participation in capacity_config.participation_limits.items():
            scenario_inputs = scale_backtest_inputs(backtest_inputs, aum, max_participation)
            result = run_backtest(**scenario_inputs)
            stats = compute_capacity_statistics(result, aum, scenario_name)
            outputs.append(stats)
    persist_capacity_results(outputs)
    return outputs
```

## evaluation_reporting_pipeline

```python
def evaluate_and_report(oof_predictions, daily_states, capacity_results):
    predictive = compute_predictive_metrics(oof_predictions)
    portfolio = compute_portfolio_metrics(daily_states)
    exposures = compute_exposure_metrics(daily_states)
    regimes = compute_regime_breakdown(oof_predictions, daily_states)
    decay = compute_decay_and_aging(oof_predictions, daily_states)
    robustness = compute_ablation_matrices()
    figures = build_all_mandatory_figures(predictive, portfolio, exposures, regimes, decay, capacity_results)
    report = render_final_report(predictive, portfolio, exposures, regimes, decay, robustness, capacity_results, figures)
    persist_report_artifacts(report, figures)
    return report
```

## 13. Полный backlog на 270 задач (LEGO-метод)

Ниже приведен полный backlog. Каждая задача нарезана как минимально самостоятельный строительный блок.

## E00 — Governance and operating model

### E00-T01 — Зафиксировать цели проекта и бизнес-вопросы

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Governance and operating model" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** нет

**Входы:**
- config files
- repository state

**Выходы:**
- artifact for зафиксировать цели проекта и бизнес-вопросы

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Зафиксировать цели проекта и бизнес-вопросы"
- Реализовать основной функциональный путь для задачи "Зафиксировать цели проекта и бизнес-вопросы"
- Добавить логирование, артефакты и manifests для задачи "Зафиксировать цели проекта и бизнес-вопросы"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E00-T02 — Зафиксировать неразрешенные риски и ограничения

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Governance and operating model" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E00-T01

**Входы:**
- config files
- repository state

**Выходы:**
- artifact for зафиксировать неразрешенные риски и ограничения

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Зафиксировать неразрешенные риски и ограничения"
- Реализовать основной функциональный путь для задачи "Зафиксировать неразрешенные риски и ограничения"
- Добавить логирование, артефакты и manifests для задачи "Зафиксировать неразрешенные риски и ограничения"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E00-T03 — Определить RACI по ролям исследователь/инженер/reviewer

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Governance and operating model" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E00-T02

**Входы:**
- config files
- repository state

**Выходы:**
- artifact for определить raci по ролям исследователь/инженер/reviewer

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Определить RACI по ролям исследователь/инженер/reviewer"
- Реализовать основной функциональный путь для задачи "Определить RACI по ролям исследователь/инженер/reviewer"
- Добавить логирование, артефакты и manifests для задачи "Определить RACI по ролям исследователь/инженер/reviewer"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E00-T04 — Описать Definition of Done для каждой фазы

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Governance and operating model" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E00-T03

**Входы:**
- config files
- repository state

**Выходы:**
- artifact for описать definition of done для каждой фазы

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Описать Definition of Done для каждой фазы"
- Реализовать основной функциональный путь для задачи "Описать Definition of Done для каждой фазы"
- Добавить логирование, артефакты и manifests для задачи "Описать Definition of Done для каждой фазы"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E00-T05 — Утвердить naming conventions и versioning policy

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Governance and operating model" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E00-T04

**Входы:**
- config files
- repository state

**Выходы:**
- artifact for утвердить naming conventions и versioning policy

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Утвердить naming conventions и versioning policy"
- Реализовать основной функциональный путь для задачи "Утвердить naming conventions и versioning policy"
- Добавить логирование, артефакты и manifests для задачи "Утвердить naming conventions и versioning policy"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E00-T06 — Утвердить политику работы с экспериментами и rollback

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Governance and operating model" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E00-T05

**Входы:**
- config files
- repository state

**Выходы:**
- artifact for утвердить политику работы с экспериментами и rollback

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Утвердить политику работы с экспериментами и rollback"
- Реализовать основной функциональный путь для задачи "Утвердить политику работы с экспериментами и rollback"
- Добавить логирование, артефакты и manifests для задачи "Утвердить политику работы с экспериментами и rollback"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E00-T07 — Утвердить policy по raw data immutability

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Governance and operating model" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E00-T06

**Входы:**
- config files
- repository state

**Выходы:**
- artifact for утвердить policy по raw data immutability

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Утвердить policy по raw data immutability"
- Реализовать основной функциональный путь для задачи "Утвердить policy по raw data immutability"
- Добавить логирование, артефакты и manifests для задачи "Утвердить policy по raw data immutability"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E00-T08 — Определить ревью-чеклист для anti-leakage

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Governance and operating model" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E00-T07

**Входы:**
- config files
- repository state

**Выходы:**
- artifact for определить ревью-чеклист для anti-leakage

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Определить ревью-чеклист для anti-leakage"
- Реализовать основной функциональный путь для задачи "Определить ревью-чеклист для anti-leakage"
- Добавить логирование, артефакты и manifests для задачи "Определить ревью-чеклист для anti-leakage"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E00-T09 — Сформировать план демонстрации результатов hiring-manager-уровня

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Governance and operating model" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E00-T08

**Входы:**
- config files
- repository state

**Выходы:**
- artifact for сформировать план демонстрации результатов hiring-manager-уровня

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Сформировать план демонстрации результатов hiring-manager-уровня"
- Реализовать основной функциональный путь для задачи "Сформировать план демонстрации результатов hiring-manager-уровня"
- Добавить логирование, артефакты и manifests для задачи "Сформировать план демонстрации результатов hiring-manager-уровня"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E00-T10 — Подготовить master glossary по терминам и сокращениям

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Governance and operating model" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E00-T09

**Входы:**
- config files
- repository state

**Выходы:**
- artifact for подготовить master glossary по терминам и сокращениям

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Подготовить master glossary по терминам и сокращениям"
- Реализовать основной функциональный путь для задачи "Подготовить master glossary по терминам и сокращениям"
- Добавить логирование, артефакты и manifests для задачи "Подготовить master glossary по терминам и сокращениям"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

## E01 — Repository bootstrap and environment

### E01-T01 — Создать skeleton репозитория

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Repository bootstrap and environment" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E00-T10

**Входы:**
- config files
- repository state

**Выходы:**
- artifact for создать skeleton репозитория

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Создать skeleton репозитория"
- Реализовать основной функциональный путь для задачи "Создать skeleton репозитория"
- Добавить логирование, артефакты и manifests для задачи "Создать skeleton репозитория"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E01-T02 — Настроить package manager и lockfile

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Repository bootstrap and environment" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E01-T01, E00-T10

**Входы:**
- config files
- repository state

**Выходы:**
- artifact for настроить package manager и lockfile

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Настроить package manager и lockfile"
- Реализовать основной функциональный путь для задачи "Настроить package manager и lockfile"
- Добавить логирование, артефакты и manifests для задачи "Настроить package manager и lockfile"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E01-T03 — Добавить pyproject и dev tooling

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Repository bootstrap and environment" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E01-T02, E00-T10

**Входы:**
- config files
- repository state

**Выходы:**
- artifact for добавить pyproject и dev tooling

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Добавить pyproject и dev tooling"
- Реализовать основной функциональный путь для задачи "Добавить pyproject и dev tooling"
- Добавить логирование, артефакты и manifests для задачи "Добавить pyproject и dev tooling"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E01-T04 — Настроить Makefile и стандартные команды

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Repository bootstrap and environment" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E01-T03

**Входы:**
- config files
- repository state

**Выходы:**
- artifact for настроить makefile и стандартные команды

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Настроить Makefile и стандартные команды"
- Реализовать основной функциональный путь для задачи "Настроить Makefile и стандартные команды"
- Добавить логирование, артефакты и manifests для задачи "Настроить Makefile и стандартные команды"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E01-T05 — Настроить pre-commit hooks

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Repository bootstrap and environment" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E01-T04

**Входы:**
- config files
- repository state

**Выходы:**
- artifact for настроить pre-commit hooks

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Настроить pre-commit hooks"
- Реализовать основной функциональный путь для задачи "Настроить pre-commit hooks"
- Добавить логирование, артефакты и manifests для задачи "Настроить pre-commit hooks"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E01-T06 — Настроить pytest structure и smoke test

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Repository bootstrap and environment" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E01-T05

**Входы:**
- config files
- repository state

**Выходы:**
- artifact for настроить pytest structure и smoke test

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Настроить pytest structure и smoke test"
- Реализовать основной функциональный путь для задачи "Настроить pytest structure и smoke test"
- Добавить логирование, артефакты и manifests для задачи "Настроить pytest structure и smoke test"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E01-T07 — Настроить lint/format/type-check pipeline

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Repository bootstrap and environment" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E01-T06

**Входы:**
- config files
- repository state

**Выходы:**
- artifact for настроить lint/format/type-check pipeline

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Настроить lint/format/type-check pipeline"
- Реализовать основной функциональный путь для задачи "Настроить lint/format/type-check pipeline"
- Добавить логирование, артефакты и manifests для задачи "Настроить lint/format/type-check pipeline"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E01-T08 — Подготовить .env.example и secrets policy

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Repository bootstrap and environment" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E01-T07

**Входы:**
- config files
- repository state

**Выходы:**
- artifact for подготовить .env.example и secrets policy

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Подготовить .env.example и secrets policy"
- Реализовать основной функциональный путь для задачи "Подготовить .env.example и secrets policy"
- Добавить логирование, артефакты и manifests для задачи "Подготовить .env.example и secrets policy"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E01-T09 — Сделать reproducible local runbook

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Repository bootstrap and environment" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E01-T08

**Входы:**
- config files
- repository state

**Выходы:**
- artifact for сделать reproducible local runbook

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Сделать reproducible local runbook"
- Реализовать основной функциональный путь для задачи "Сделать reproducible local runbook"
- Добавить логирование, артефакты и manifests для задачи "Сделать reproducible local runbook"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E01-T10 — Сделать bootstrap script для новой машины

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Repository bootstrap and environment" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E01-T09

**Входы:**
- config files
- repository state

**Выходы:**
- artifact for сделать bootstrap script для новой машины

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Сделать bootstrap script для новой машины"
- Реализовать основной функциональный путь для задачи "Сделать bootstrap script для новой машины"
- Добавить логирование, артефакты и manifests для задачи "Сделать bootstrap script для новой машины"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

## E02 — Configuration, logging and experiment tracking

### E02-T01 — Создать schema для project config

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Configuration, logging and experiment tracking" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E01-T10

**Входы:**
- config files
- repository state

**Выходы:**
- artifact for создать schema для project config

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Создать schema для project config"
- Реализовать основной функциональный путь для задачи "Создать schema для project config"
- Добавить логирование, артефакты и manifests для задачи "Создать schema для project config"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E02-T02 — Создать schema для data source config

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Configuration, logging and experiment tracking" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E02-T01, E01-T10

**Входы:**
- config files
- repository state

**Выходы:**
- artifact for создать schema для data source config

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Создать schema для data source config"
- Реализовать основной функциональный путь для задачи "Создать schema для data source config"
- Добавить логирование, артефакты и manifests для задачи "Создать schema для data source config"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E02-T03 — Создать schema для experiment config

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Configuration, logging and experiment tracking" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E02-T02, E01-T10

**Входы:**
- config files
- repository state

**Выходы:**
- artifact for создать schema для experiment config

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Создать schema для experiment config"
- Реализовать основной функциональный путь для задачи "Создать schema для experiment config"
- Добавить логирование, артефакты и manifests для задачи "Создать schema для experiment config"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E02-T04 — Реализовать config loader и validation

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Configuration, logging and experiment tracking" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E02-T03

**Входы:**
- config files
- repository state

**Выходы:**
- artifact for реализовать config loader и validation

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать config loader и validation"
- Реализовать основной функциональный путь для задачи "Реализовать config loader и validation"
- Добавить логирование, артефакты и manifests для задачи "Реализовать config loader и validation"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E02-T05 — Реализовать config hash и snapshot persistence

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Configuration, logging and experiment tracking" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E02-T04

**Входы:**
- config files
- repository state

**Выходы:**
- artifact for реализовать config hash и snapshot persistence

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать config hash и snapshot persistence"
- Реализовать основной функциональный путь для задачи "Реализовать config hash и snapshot persistence"
- Добавить логирование, артефакты и manifests для задачи "Реализовать config hash и snapshot persistence"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E02-T06 — Настроить structured logging

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Configuration, logging and experiment tracking" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E02-T05

**Входы:**
- config files
- repository state

**Выходы:**
- artifact for настроить structured logging

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Настроить structured logging"
- Реализовать основной функциональный путь для задачи "Настроить structured logging"
- Добавить логирование, артефакты и manifests для задачи "Настроить structured logging"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E02-T07 — Настроить MLflow experiment hierarchy

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Configuration, logging and experiment tracking" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E02-T06

**Входы:**
- config files
- repository state

**Выходы:**
- artifact for настроить mlflow experiment hierarchy

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Настроить MLflow experiment hierarchy"
- Реализовать основной функциональный путь для задачи "Настроить MLflow experiment hierarchy"
- Добавить логирование, артефакты и manifests для задачи "Настроить MLflow experiment hierarchy"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E02-T08 — Логировать dataset manifests как артефакты

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Configuration, logging and experiment tracking" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E02-T07

**Входы:**
- config files
- repository state

**Выходы:**
- artifact for логировать dataset manifests как артефакты

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Логировать dataset manifests как артефакты"
- Реализовать основной функциональный путь для задачи "Логировать dataset manifests как артефакты"
- Добавить логирование, артефакты и manifests для задачи "Логировать dataset manifests как артефакты"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E02-T09 — Логировать feature registry snapshot в каждом run

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Configuration, logging and experiment tracking" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E02-T08

**Входы:**
- config files
- repository state

**Выходы:**
- artifact for логировать feature registry snapshot в каждом run

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Логировать feature registry snapshot в каждом run"
- Реализовать основной функциональный путь для задачи "Логировать feature registry snapshot в каждом run"
- Добавить логирование, артефакты и manifests для задачи "Логировать feature registry snapshot в каждом run"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E02-T10 — Логировать git commit и environment fingerprint

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Configuration, logging and experiment tracking" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E02-T09

**Входы:**
- config files
- repository state

**Выходы:**
- artifact for логировать git commit и environment fingerprint

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Логировать git commit и environment fingerprint"
- Реализовать основной функциональный путь для задачи "Логировать git commit и environment fingerprint"
- Добавить логирование, артефакты и manifests для задачи "Логировать git commit и environment fingerprint"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

## E03 — Calendars, timestamps and identifiers

### E03-T01 — Реализовать exchange calendar adapter

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Calendars, timestamps and identifiers" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E02-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать exchange calendar adapter

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать exchange calendar adapter"
- Реализовать основной функциональный путь для задачи "Реализовать exchange calendar adapter"
- Добавить логирование, артефакты и manifests для задачи "Реализовать exchange calendar adapter"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E03-T02 — Реализовать next/prev trading day utilities

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Calendars, timestamps and identifiers" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E03-T01, E02-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать next/prev trading day utilities

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать next/prev trading day utilities"
- Реализовать основной функциональный путь для задачи "Реализовать next/prev trading day utilities"
- Добавить логирование, артефакты и manifests для задачи "Реализовать next/prev trading day utilities"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E03-T03 — Реализовать trading-day distance utility

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Calendars, timestamps and identifiers" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E03-T02, E02-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать trading-day distance utility

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать trading-day distance utility"
- Реализовать основной функциональный путь для задачи "Реализовать trading-day distance utility"
- Добавить логирование, артефакты и manifests для задачи "Реализовать trading-day distance utility"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E03-T04 — Зафиксировать decision timestamp semantics

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Calendars, timestamps and identifiers" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E03-T03

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for зафиксировать decision timestamp semantics

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Зафиксировать decision timestamp semantics"
- Реализовать основной функциональный путь для задачи "Зафиксировать decision timestamp semantics"
- Добавить логирование, артефакты и manifests для задачи "Зафиксировать decision timestamp semantics"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E03-T05 — Зафиксировать execution timestamp semantics

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Calendars, timestamps and identifiers" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E03-T04

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for зафиксировать execution timestamp semantics

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Зафиксировать execution timestamp semantics"
- Реализовать основной функциональный путь для задачи "Зафиксировать execution timestamp semantics"
- Добавить логирование, артефакты и manifests для задачи "Зафиксировать execution timestamp semantics"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E03-T06 — Зафиксировать label start timestamp semantics

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Calendars, timestamps and identifiers" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E03-T05

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for зафиксировать label start timestamp semantics

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Зафиксировать label start timestamp semantics"
- Реализовать основной функциональный путь для задачи "Зафиксировать label start timestamp semantics"
- Добавить логирование, артефакты и manifests для задачи "Зафиксировать label start timestamp semantics"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E03-T07 — Стабилизировать internal security_id

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Calendars, timestamps and identifiers" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E03-T06

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for стабилизировать internal security_id

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Стабилизировать internal security_id"
- Реализовать основной функциональный путь для задачи "Стабилизировать internal security_id"
- Добавить логирование, артефакты и manifests для задачи "Стабилизировать internal security_id"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E03-T08 — Обработать ticker changes и ticker reuse

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Calendars, timestamps and identifiers" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E03-T07

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for обработать ticker changes и ticker reuse

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Обработать ticker changes и ticker reuse"
- Реализовать основной функциональный путь для задачи "Обработать ticker changes и ticker reuse"
- Добавить логирование, артефакты и manifests для задачи "Обработать ticker changes и ticker reuse"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E03-T09 — Подготовить identifier mapping audit report

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Calendars, timestamps and identifiers" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E03-T08

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for подготовить identifier mapping audit report

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Подготовить identifier mapping audit report"
- Реализовать основной функциональный путь для задачи "Подготовить identifier mapping audit report"
- Добавить логирование, артефакты и manifests для задачи "Подготовить identifier mapping audit report"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E03-T10 — Добавить tests на timestamp alignment

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Calendars, timestamps and identifiers" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E03-T09

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for добавить tests на timestamp alignment

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Добавить tests на timestamp alignment"
- Реализовать основной функциональный путь для задачи "Добавить tests на timestamp alignment"
- Добавить логирование, артефакты и manifests для задачи "Добавить tests на timestamp alignment"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

## E04 — Security master and reference data

### E04-T01 — Собрать reference fields security master

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Security master and reference data" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E03-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for собрать reference fields security master

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Собрать reference fields security master"
- Реализовать основной функциональный путь для задачи "Собрать reference fields security master"
- Добавить логирование, артефакты и manifests для задачи "Собрать reference fields security master"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E04-T02 — Нормализовать exchanges и security types

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Security master and reference data" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E04-T01, E03-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for нормализовать exchanges и security types

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Нормализовать exchanges и security types"
- Реализовать основной функциональный путь для задачи "Нормализовать exchanges и security types"
- Добавить логирование, артефакты и manifests для задачи "Нормализовать exchanges и security types"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E04-T03 — Разметить common stock eligibility

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Security master and reference data" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E04-T02, E03-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for разметить common stock eligibility

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Разметить common stock eligibility"
- Реализовать основной функциональный путь для задачи "Разметить common stock eligibility"
- Добавить логирование, артефакты и manifests для задачи "Разметить common stock eligibility"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E04-T04 — Привязать sector и industry classification

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Security master and reference data" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E04-T03

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for привязать sector и industry classification

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Привязать sector и industry classification"
- Реализовать основной функциональный путь для задачи "Привязать sector и industry classification"
- Добавить логирование, артефакты и manifests для задачи "Привязать sector и industry classification"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E04-T05 — Учесть listing_date и delisting_date

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Security master and reference data" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E04-T04

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for учесть listing_date и delisting_date

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Учесть listing_date и delisting_date"
- Реализовать основной функциональный путь для задачи "Учесть listing_date и delisting_date"
- Добавить логирование, артефакты и manifests для задачи "Учесть listing_date и delisting_date"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E04-T06 — Выявить конфликты symbol-to-security mappings

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Security master and reference data" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E04-T05

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for выявить конфликты symbol-to-security mappings

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Выявить конфликты symbol-to-security mappings"
- Реализовать основной функциональный путь для задачи "Выявить конфликты symbol-to-security mappings"
- Добавить логирование, артефакты и manifests для задачи "Выявить конфликты symbol-to-security mappings"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E04-T07 — Сформировать reference data bronze table

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Security master and reference data" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E04-T06

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for сформировать reference data bronze table

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Сформировать reference data bronze table"
- Реализовать основной функциональный путь для задачи "Сформировать reference data bronze table"
- Добавить логирование, артефакты и manifests для задачи "Сформировать reference data bronze table"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E04-T08 — Сформировать reference data silver table

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Security master and reference data" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E04-T07

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for сформировать reference data silver table

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Сформировать reference data silver table"
- Реализовать основной функциональный путь для задачи "Сформировать reference data silver table"
- Добавить логирование, артефакты и manifests для задачи "Сформировать reference data silver table"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E04-T09 — Реализовать data quality scoring для reference records

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Security master and reference data" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E04-T08

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать data quality scoring для reference records

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать data quality scoring для reference records"
- Реализовать основной функциональный путь для задачи "Реализовать data quality scoring для reference records"
- Добавить логирование, артефакты и manifests для задачи "Реализовать data quality scoring для reference records"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E04-T10 — Подготовить отчет по completeness reference layer

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Security master and reference data" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E04-T09

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for подготовить отчет по completeness reference layer

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Подготовить отчет по completeness reference layer"
- Реализовать основной функциональный путь для задачи "Подготовить отчет по completeness reference layer"
- Добавить логирование, артефакты и manifests для задачи "Подготовить отчет по completeness reference layer"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

## E05 — Market raw ingestion

### E05-T01 — Описать provider adapter contract для market data

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Market raw ingestion" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E04-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for описать provider adapter contract для market data

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Описать provider adapter contract для market data"
- Реализовать основной функциональный путь для задачи "Описать provider adapter contract для market data"
- Добавить логирование, артефакты и manifests для задачи "Описать provider adapter contract для market data"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E05-T02 — Реализовать загрузку raw market payloads

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Market raw ingestion" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E05-T01, E04-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать загрузку raw market payloads

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать загрузку raw market payloads"
- Реализовать основной функциональный путь для задачи "Реализовать загрузку raw market payloads"
- Добавить логирование, артефакты и manifests для задачи "Реализовать загрузку raw market payloads"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E05-T03 — Сохранять request manifest для каждого batch

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Market raw ingestion" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E05-T02, E04-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for сохранять request manifest для каждого batch

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Сохранять request manifest для каждого batch"
- Реализовать основной функциональный путь для задачи "Сохранять request manifest для каждого batch"
- Добавить логирование, артефакты и manifests для задачи "Сохранять request manifest для каждого batch"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E05-T04 — Нормализовать market payload в bronze schema

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Market raw ingestion" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E05-T03

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for нормализовать market payload в bronze schema

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Нормализовать market payload в bronze schema"
- Реализовать основной функциональный путь для задачи "Нормализовать market payload в bronze schema"
- Добавить логирование, артефакты и manifests для задачи "Нормализовать market payload в bronze schema"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E05-T05 — Обрабатывать pagination и retry logic

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Market raw ingestion" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E05-T04

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for обрабатывать pagination и retry logic

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Обрабатывать pagination и retry logic"
- Реализовать основной функциональный путь для задачи "Обрабатывать pagination и retry logic"
- Добавить логирование, артефакты и manifests для задачи "Обрабатывать pagination и retry logic"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E05-T06 — Обрабатывать provider-side missing symbols

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Market raw ingestion" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E05-T05

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for обрабатывать provider-side missing symbols

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Обрабатывать provider-side missing symbols"
- Реализовать основной функциональный путь для задачи "Обрабатывать provider-side missing symbols"
- Добавить логирование, артефакты и manifests для задачи "Обрабатывать provider-side missing symbols"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E05-T07 — Валидировать базовые типы и mandatory fields

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Market raw ingestion" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E05-T06

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for валидировать базовые типы и mandatory fields

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Валидировать базовые типы и mandatory fields"
- Реализовать основной функциональный путь для задачи "Валидировать базовые типы и mandatory fields"
- Добавить логирование, артефакты и manifests для задачи "Валидировать базовые типы и mandatory fields"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E05-T08 — Реализовать incremental ingest policy

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Market raw ingestion" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E05-T07

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать incremental ingest policy

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать incremental ingest policy"
- Реализовать основной функциональный путь для задачи "Реализовать incremental ingest policy"
- Добавить логирование, артефакты и manifests для задачи "Реализовать incremental ingest policy"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E05-T09 — Реализовать backfill policy по датам и тикерам

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Market raw ingestion" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E05-T08

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать backfill policy по датам и тикерам

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать backfill policy по датам и тикерам"
- Реализовать основной функциональный путь для задачи "Реализовать backfill policy по датам и тикерам"
- Добавить логирование, артефакты и manifests для задачи "Реализовать backfill policy по датам и тикерам"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E05-T10 — Сформировать ingest diagnostics report

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Market raw ingestion" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E05-T09

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for сформировать ingest diagnostics report

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Сформировать ingest diagnostics report"
- Реализовать основной функциональный путь для задачи "Сформировать ingest diagnostics report"
- Добавить логирование, артефакты и manifests для задачи "Сформировать ingest diagnostics report"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

## E06 — Fundamentals raw ingestion

### E06-T01 — Описать provider adapter contract для fundamentals

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Fundamentals raw ingestion" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E05-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for описать provider adapter contract для fundamentals

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Описать provider adapter contract для fundamentals"
- Реализовать основной функциональный путь для задачи "Описать provider adapter contract для fundamentals"
- Добавить логирование, артефакты и manifests для задачи "Описать provider adapter contract для fundamentals"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E06-T02 — Реализовать загрузку raw filings/company facts

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Fundamentals raw ingestion" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E06-T01, E05-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать загрузку raw filings/company facts

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать загрузку raw filings/company facts"
- Реализовать основной функциональный путь для задачи "Реализовать загрузку raw filings/company facts"
- Добавить логирование, артефакты и manifests для задачи "Реализовать загрузку raw filings/company facts"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E06-T03 — Извлекать filing_date и acceptance_datetime

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Fundamentals raw ingestion" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E06-T02, E05-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for извлекать filing_date и acceptance_datetime

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Извлекать filing_date и acceptance_datetime"
- Реализовать основной функциональный путь для задачи "Извлекать filing_date и acceptance_datetime"
- Добавить логирование, артефакты и manifests для задачи "Извлекать filing_date и acceptance_datetime"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E06-T04 — Рассчитывать available_from по policy

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Fundamentals raw ingestion" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E06-T03

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for рассчитывать available_from по policy

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Рассчитывать available_from по policy"
- Реализовать основной функциональный путь для задачи "Рассчитывать available_from по policy"
- Добавить логирование, артефакты и manifests для задачи "Рассчитывать available_from по policy"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E06-T05 — Нормализовать metric names в canonical dictionary

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Fundamentals raw ingestion" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E06-T04

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for нормализовать metric names в canonical dictionary

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Нормализовать metric names в canonical dictionary"
- Реализовать основной функциональный путь для задачи "Нормализовать metric names в canonical dictionary"
- Добавить логирование, артефакты и manifests для задачи "Нормализовать metric names в canonical dictionary"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E06-T06 — Сохранять raw payloads и parse manifests

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Fundamentals raw ingestion" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E06-T05

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for сохранять raw payloads и parse manifests

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Сохранять raw payloads и parse manifests"
- Реализовать основной функциональный путь для задачи "Сохранять raw payloads и parse manifests"
- Добавить логирование, артефакты и manifests для задачи "Сохранять raw payloads и parse manifests"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E06-T07 — Размечать restatement events

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Fundamentals raw ingestion" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E06-T06

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for размечать restatement events

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Размечать restatement events"
- Реализовать основной функциональный путь для задачи "Размечать restatement events"
- Добавить логирование, артефакты и manifests для задачи "Размечать restatement events"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E06-T08 — Строить bronze fundamentals table

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Fundamentals raw ingestion" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E06-T07

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for строить bronze fundamentals table

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Строить bronze fundamentals table"
- Реализовать основной функциональный путь для задачи "Строить bronze fundamentals table"
- Добавить логирование, артефакты и manifests для задачи "Строить bronze fundamentals table"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E06-T09 — Реализовать incremental fundamentals ingest

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Fundamentals raw ingestion" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E06-T08

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать incremental fundamentals ingest

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать incremental fundamentals ingest"
- Реализовать основной функциональный путь для задачи "Реализовать incremental fundamentals ingest"
- Добавить логирование, артефакты и manifests для задачи "Реализовать incremental fundamentals ingest"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E06-T10 — Подготовить diagnostics по покрытиям метрик

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Fundamentals raw ingestion" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E06-T09

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for подготовить diagnostics по покрытиям метрик

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Подготовить diagnostics по покрытиям метрик"
- Реализовать основной функциональный путь для задачи "Подготовить diagnostics по покрытиям метрик"
- Добавить логирование, артефакты и manifests для задачи "Подготовить diagnostics по покрытиям метрик"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

## E07 — Corporate actions ingestion

### E07-T01 — Описать contract для corporate actions adapter

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Corporate actions ingestion" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E06-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for описать contract для corporate actions adapter

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Описать contract для corporate actions adapter"
- Реализовать основной функциональный путь для задачи "Описать contract для corporate actions adapter"
- Добавить логирование, артефакты и manifests для задачи "Описать contract для corporate actions adapter"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E07-T02 — Загружать splits

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Corporate actions ingestion" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E07-T01, E06-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for загружать splits

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Загружать splits"
- Реализовать основной функциональный путь для задачи "Загружать splits"
- Добавить логирование, артефакты и manifests для задачи "Загружать splits"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E07-T03 — Загружать dividends

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Corporate actions ingestion" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E07-T02, E06-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for загружать dividends

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Загружать dividends"
- Реализовать основной функциональный путь для задачи "Загружать dividends"
- Добавить логирование, артефакты и manifests для задачи "Загружать dividends"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E07-T04 — Загружать delisting events

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Corporate actions ingestion" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E07-T03

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for загружать delisting events

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Загружать delisting events"
- Реализовать основной функциональный путь для задачи "Загружать delisting events"
- Добавить логирование, артефакты и manifests для задачи "Загружать delisting events"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E07-T05 — Загружать symbol change events

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Corporate actions ingestion" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E07-T04

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for загружать symbol change events

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Загружать symbol change events"
- Реализовать основной функциональный путь для задачи "Загружать symbol change events"
- Добавить логирование, артефакты и manifests для задачи "Загружать symbol change events"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E07-T06 — Нормализовать corporate actions schema

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Corporate actions ingestion" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E07-T05

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for нормализовать corporate actions schema

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Нормализовать corporate actions schema"
- Реализовать основной функциональный путь для задачи "Нормализовать corporate actions schema"
- Добавить логирование, артефакты и manifests для задачи "Нормализовать corporate actions schema"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E07-T07 — Сшить corporate actions с security master

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Corporate actions ingestion" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E07-T06

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for сшить corporate actions с security master

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Сшить corporate actions с security master"
- Реализовать основной функциональный путь для задачи "Сшить corporate actions с security master"
- Добавить логирование, артефакты и manifests для задачи "Сшить corporate actions с security master"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E07-T08 — Проверять consistency split ratios

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Corporate actions ingestion" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E07-T07

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for проверять consistency split ratios

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Проверять consistency split ratios"
- Реализовать основной функциональный путь для задачи "Проверять consistency split ratios"
- Добавить логирование, артефакты и manifests для задачи "Проверять consistency split ratios"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E07-T09 — Строить canonical corporate actions layer

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Corporate actions ingestion" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E07-T08

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for строить canonical corporate actions layer

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Строить canonical corporate actions layer"
- Реализовать основной функциональный путь для задачи "Строить canonical corporate actions layer"
- Добавить логирование, артефакты и manifests для задачи "Строить canonical corporate actions layer"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E07-T10 — Подготовить audit report по corporate actions

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Corporate actions ingestion" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P0`

**Зависимости:** E07-T09

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for подготовить audit report по corporate actions

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Подготовить audit report по corporate actions"
- Реализовать основной функциональный путь для задачи "Подготовить audit report по corporate actions"
- Добавить логирование, артефакты и manifests для задачи "Подготовить audit report по corporate actions"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

## E08 — Market data quality assurance

### E08-T01 — Проверять OHLC positivity

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Market data quality assurance" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E07-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for проверять ohlc positivity

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Проверять OHLC positivity"
- Реализовать основной функциональный путь для задачи "Проверять OHLC positivity"
- Добавить логирование, артефакты и manifests для задачи "Проверять OHLC positivity"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E08-T02 — Проверять OHLC logical consistency

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Market data quality assurance" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E08-T01, E07-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for проверять ohlc logical consistency

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Проверять OHLC logical consistency"
- Реализовать основной функциональный путь для задачи "Проверять OHLC logical consistency"
- Добавить логирование, артефакты и manifests для задачи "Проверять OHLC logical consistency"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E08-T03 — Проверять volume non-negativity

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Market data quality assurance" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E08-T02, E07-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for проверять volume non-negativity

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Проверять volume non-negativity"
- Реализовать основной функциональный путь для задачи "Проверять volume non-negativity"
- Добавить логирование, артефакты и manifests для задачи "Проверять volume non-negativity"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E08-T04 — Проверять duplicate rows

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Market data quality assurance" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E08-T03

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for проверять duplicate rows

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Проверять duplicate rows"
- Реализовать основной функциональный путь для задачи "Проверять duplicate rows"
- Добавить логирование, артефакты и manifests для задачи "Проверять duplicate rows"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E08-T05 — Проверять impossible return spikes

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Market data quality assurance" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E08-T04

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for проверять impossible return spikes

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Проверять impossible return spikes"
- Реализовать основной функциональный путь для задачи "Проверять impossible return spikes"
- Добавить логирование, артефакты и manifests для задачи "Проверять impossible return spikes"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E08-T06 — Проверять missing trading days against calendar

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Market data quality assurance" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E08-T05

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for проверять missing trading days against calendar

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Проверять missing trading days against calendar"
- Реализовать основной функциональный путь для задачи "Проверять missing trading days against calendar"
- Добавить логирование, артефакты и manifests для задачи "Проверять missing trading days against calendar"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E08-T07 — Проверять currency consistency

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Market data quality assurance" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E08-T06

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for проверять currency consistency

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Проверять currency consistency"
- Реализовать основной функциональный путь для задачи "Проверять currency consistency"
- Добавить логирование, артефакты и manifests для задачи "Проверять currency consistency"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E08-T08 — Считать per-symbol data quality scores

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Market data quality assurance" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E08-T07

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for считать per-symbol data quality scores

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Считать per-symbol data quality scores"
- Реализовать основной функциональный путь для задачи "Считать per-symbol data quality scores"
- Добавить логирование, артефакты и manifests для задачи "Считать per-symbol data quality scores"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E08-T09 — Формировать failed-row extracts

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Market data quality assurance" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E08-T08

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for формировать failed-row extracts

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Формировать failed-row extracts"
- Реализовать основной функциональный путь для задачи "Формировать failed-row extracts"
- Добавить логирование, артефакты и manifests для задачи "Формировать failed-row extracts"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E08-T10 — Генерировать market QA summary report

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Market data quality assurance" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E08-T09

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for генерировать market qa summary report

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Генерировать market QA summary report"
- Реализовать основной функциональный путь для задачи "Генерировать market QA summary report"
- Добавить логирование, артефакты и manifests для задачи "Генерировать market QA summary report"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

## E09 — Fundamentals data quality assurance

### E09-T01 — Проверять metric value parseability

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Fundamentals data quality assurance" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E08-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for проверять metric value parseability

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Проверять metric value parseability"
- Реализовать основной функциональный путь для задачи "Проверять metric value parseability"
- Добавить логирование, артефакты и manifests для задачи "Проверять metric value parseability"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E09-T02 — Проверять metric unit consistency

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Fundamentals data quality assurance" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E09-T01, E08-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for проверять metric unit consistency

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Проверять metric unit consistency"
- Реализовать основной функциональный путь для задачи "Проверять metric unit consistency"
- Добавить логирование, артефакты и manifests для задачи "Проверять metric unit consistency"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E09-T03 — Проверять impossible timestamps

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Fundamentals data quality assurance" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E09-T02, E08-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for проверять impossible timestamps

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Проверять impossible timestamps"
- Реализовать основной функциональный путь для задачи "Проверять impossible timestamps"
- Добавить логирование, артефакты и manifests для задачи "Проверять impossible timestamps"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E09-T04 — Проверять duplicate fact collisions

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Fundamentals data quality assurance" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E09-T03

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for проверять duplicate fact collisions

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Проверять duplicate fact collisions"
- Реализовать основной функциональный путь для задачи "Проверять duplicate fact collisions"
- Добавить логирование, артефакты и manifests для задачи "Проверять duplicate fact collisions"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E09-T05 — Проверять abnormal sign/value anomalies

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Fundamentals data quality assurance" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E09-T04

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for проверять abnormal sign/value anomalies

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Проверять abnormal sign/value anomalies"
- Реализовать основной функциональный путь для задачи "Проверять abnormal sign/value anomalies"
- Добавить логирование, артефакты и manifests для задачи "Проверять abnormal sign/value anomalies"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E09-T06 — Проверять restatement handling

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Fundamentals data quality assurance" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E09-T05

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for проверять restatement handling

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Проверять restatement handling"
- Реализовать основной функциональный путь для задачи "Проверять restatement handling"
- Добавить логирование, артефакты и manifests для задачи "Проверять restatement handling"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E09-T07 — Считать staleness diagnostics

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Fundamentals data quality assurance" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E09-T06

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for считать staleness diagnostics

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Считать staleness diagnostics"
- Реализовать основной функциональный путь для задачи "Считать staleness diagnostics"
- Добавить логирование, артефакты и manifests для задачи "Считать staleness diagnostics"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E09-T08 — Считать completeness by metric and year

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Fundamentals data quality assurance" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E09-T07

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for считать completeness by metric and year

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Считать completeness by metric and year"
- Реализовать основной функциональный путь для задачи "Считать completeness by metric and year"
- Добавить логирование, артефакты и manifests для задачи "Считать completeness by metric and year"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E09-T09 — Формировать failed-row extracts для fundamentals

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Fundamentals data quality assurance" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E09-T08

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for формировать failed-row extracts для fundamentals

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Формировать failed-row extracts для fundamentals"
- Реализовать основной функциональный путь для задачи "Формировать failed-row extracts для fundamentals"
- Добавить логирование, артефакты и manifests для задачи "Формировать failed-row extracts для fundamentals"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E09-T10 — Генерировать fundamentals QA summary report

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Fundamentals data quality assurance" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E09-T09

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for генерировать fundamentals qa summary report

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Генерировать fundamentals QA summary report"
- Реализовать основной функциональный путь для задачи "Генерировать fundamentals QA summary report"
- Добавить логирование, артефакты и manifests для задачи "Генерировать fundamentals QA summary report"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

## E10 — Point-in-time engine

### E10-T01 — Реализовать as-of join primitive

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Point-in-time engine" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E09-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать as-of join primitive

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать as-of join primitive"
- Реализовать основной функциональный путь для задачи "Реализовать as-of join primitive"
- Добавить логирование, артефакты и manifests для задачи "Реализовать as-of join primitive"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E10-T02 — Реализовать PIT join для fundamentals

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Point-in-time engine" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E10-T01, E09-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать pit join для fundamentals

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать PIT join для fundamentals"
- Реализовать основной функциональный путь для задачи "Реализовать PIT join для fundamentals"
- Добавить логирование, артефакты и manifests для задачи "Реализовать PIT join для fundamentals"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E10-T03 — Реализовать PIT join для sector/classification snapshots

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Point-in-time engine" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E10-T02, E09-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать pit join для sector/classification snapshots

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать PIT join для sector/classification snapshots"
- Реализовать основной функциональный путь для задачи "Реализовать PIT join для sector/classification snapshots"
- Добавить логирование, артефакты и manifests для задачи "Реализовать PIT join для sector/classification snapshots"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E10-T04 — Добавить available_to interval support

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Point-in-time engine" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E10-T03

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for добавить available_to interval support

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Добавить available_to interval support"
- Реализовать основной функциональный путь для задачи "Добавить available_to interval support"
- Добавить логирование, артефакты и manifests для задачи "Добавить available_to interval support"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E10-T05 — Запретить join по fiscal_period_end в baseline

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Point-in-time engine" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E10-T04

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for запретить join по fiscal_period_end в baseline

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Запретить join по fiscal_period_end в baseline"
- Реализовать основной функциональный путь для задачи "Запретить join по fiscal_period_end в baseline"
- Добавить логирование, артефакты и manifests для задачи "Запретить join по fiscal_period_end в baseline"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E10-T06 — Логировать source timestamps после joins

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Point-in-time engine" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E10-T05

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for логировать source timestamps после joins

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Логировать source timestamps после joins"
- Реализовать основной функциональный путь для задачи "Логировать source timestamps после joins"
- Добавить логирование, артефакты и manifests для задачи "Логировать source timestamps после joins"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E10-T07 — Добавить tests на future-data rejection

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Point-in-time engine" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E10-T06

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for добавить tests на future-data rejection

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Добавить tests на future-data rejection"
- Реализовать основной функциональный путь для задачи "Добавить tests на future-data rejection"
- Добавить логирование, артефакты и manifests для задачи "Добавить tests на future-data rejection"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E10-T08 — Добавить tests на restatement non-leakage

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Point-in-time engine" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E10-T07

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for добавить tests на restatement non-leakage

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Добавить tests на restatement non-leakage"
- Реализовать основной функциональный путь для задачи "Добавить tests на restatement non-leakage"
- Добавить логирование, артефакты и manifests для задачи "Добавить tests на restatement non-leakage"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E10-T09 — Сформировать PIT diagnostics report

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Point-in-time engine" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E10-T08

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for сформировать pit diagnostics report

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Сформировать PIT diagnostics report"
- Реализовать основной функциональный путь для задачи "Сформировать PIT diagnostics report"
- Добавить логирование, артефакты и manifests для задачи "Сформировать PIT diagnostics report"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E10-T10 — Сформировать PIT policy documentation

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Point-in-time engine" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E10-T09

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for сформировать pit policy documentation

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Сформировать PIT policy documentation"
- Реализовать основной функциональный путь для задачи "Сформировать PIT policy documentation"
- Добавить логирование, артефакты и manifests для задачи "Сформировать PIT policy documentation"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

## E11 — Universe construction

### E11-T01 — Реализовать filter по security type

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Universe construction" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E10-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать filter по security type

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать filter по security type"
- Реализовать основной функциональный путь для задачи "Реализовать filter по security type"
- Добавить логирование, артефакты и manifests для задачи "Реализовать filter по security type"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E11-T02 — Реализовать filter по listing status

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Universe construction" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E11-T01, E10-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать filter по listing status

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать filter по listing status"
- Реализовать основной функциональный путь для задачи "Реализовать filter по listing status"
- Добавить логирование, артефакты и manifests для задачи "Реализовать filter по listing status"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E11-T03 — Реализовать filter по exchange

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Universe construction" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E11-T02, E10-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать filter по exchange

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать filter по exchange"
- Реализовать основной функциональный путь для задачи "Реализовать filter по exchange"
- Добавить логирование, артефакты и manifests для задачи "Реализовать filter по exchange"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E11-T04 — Реализовать filter по min price

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Universe construction" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E11-T03

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать filter по min price

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать filter по min price"
- Реализовать основной функциональный путь для задачи "Реализовать filter по min price"
- Добавить логирование, артефакты и manifests для задачи "Реализовать filter по min price"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E11-T05 — Реализовать filter по min ADV20

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Universe construction" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E11-T04

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать filter по min adv20

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать filter по min ADV20"
- Реализовать основной функциональный путь для задачи "Реализовать filter по min ADV20"
- Добавить логирование, артефакты и manifests для задачи "Реализовать filter по min ADV20"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E11-T06 — Реализовать filter по feature coverage

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Universe construction" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E11-T05

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать filter по feature coverage

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать filter по feature coverage"
- Реализовать основной функциональный путь для задачи "Реализовать filter по feature coverage"
- Добавить логирование, артефакты и manifests для задачи "Реализовать filter по feature coverage"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E11-T07 — Реализовать filter по data quality score

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Universe construction" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E11-T06

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать filter по data quality score

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать filter по data quality score"
- Реализовать основной функциональный путь для задачи "Реализовать filter по data quality score"
- Добавить логирование, артефакты и manifests для задачи "Реализовать filter по data quality score"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E11-T08 — Строить universe snapshots на каждую дату

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Universe construction" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E11-T07

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for строить universe snapshots на каждую дату

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Строить universe snapshots на каждую дату"
- Реализовать основной функциональный путь для задачи "Строить universe snapshots на каждую дату"
- Добавить логирование, артефакты и manifests для задачи "Строить universe snapshots на каждую дату"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E11-T09 — Логировать exclusion reasons

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Universe construction" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E11-T08

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for логировать exclusion reasons

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Логировать exclusion reasons"
- Реализовать основной функциональный путь для задачи "Логировать exclusion reasons"
- Добавить логирование, артефакты и manifests для задачи "Логировать exclusion reasons"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E11-T10 — Генерировать universe stability report

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Universe construction" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E11-T09

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for генерировать universe stability report

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Генерировать universe stability report"
- Реализовать основной функциональный путь для задачи "Генерировать universe stability report"
- Добавить логирование, артефакты и manifests для задачи "Генерировать universe stability report"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

## E12 — Label engine

### E12-T01 — Реализовать open-to-open 1d labels

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Label engine" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E11-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать open-to-open 1d labels

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать open-to-open 1d labels"
- Реализовать основной функциональный путь для задачи "Реализовать open-to-open 1d labels"
- Добавить логирование, артефакты и manifests для задачи "Реализовать open-to-open 1d labels"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E12-T02 — Реализовать open-to-open 5d labels

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Label engine" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E12-T01, E11-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать open-to-open 5d labels

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать open-to-open 5d labels"
- Реализовать основной функциональный путь для задачи "Реализовать open-to-open 5d labels"
- Добавить логирование, артефакты и manifests для задачи "Реализовать open-to-open 5d labels"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E12-T03 — Реализовать open-to-open 10d labels

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Label engine" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E12-T02, E11-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать open-to-open 10d labels

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать open-to-open 10d labels"
- Реализовать основной функциональный путь для задачи "Реализовать open-to-open 10d labels"
- Добавить логирование, артефакты и manifests для задачи "Реализовать open-to-open 10d labels"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E12-T04 — Реализовать benchmark excess labels

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Label engine" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E12-T03

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать benchmark excess labels

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать benchmark excess labels"
- Реализовать основной функциональный путь для задачи "Реализовать benchmark excess labels"
- Добавить логирование, артефакты и manifests для задачи "Реализовать benchmark excess labels"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E12-T05 — Реализовать residual labels с sector/beta controls

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Label engine" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E12-T04

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать residual labels с sector/beta controls

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать residual labels с sector/beta controls"
- Реализовать основной функциональный путь для задачи "Реализовать residual labels с sector/beta controls"
- Добавить логирование, артефакты и manifests для задачи "Реализовать residual labels с sector/beta controls"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E12-T06 — Реализовать binary top-bottom labels

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Label engine" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E12-T05

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать binary top-bottom labels

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать binary top-bottom labels"
- Реализовать основной функциональный путь для задачи "Реализовать binary top-bottom labels"
- Добавить логирование, артефакты и manifests для задачи "Реализовать binary top-bottom labels"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E12-T07 — Реализовать multiclass quantile labels

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Label engine" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E12-T06

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать multiclass quantile labels

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать multiclass quantile labels"
- Реализовать основной функциональный путь для задачи "Реализовать multiclass quantile labels"
- Добавить логирование, артефакты и manifests для задачи "Реализовать multiclass quantile labels"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E12-T08 — Проверить overlap policy и purge hints

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Label engine" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E12-T07

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for проверить overlap policy и purge hints

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Проверить overlap policy и purge hints"
- Реализовать основной функциональный путь для задачи "Проверить overlap policy и purge hints"
- Добавить логирование, артефакты и manifests для задачи "Проверить overlap policy и purge hints"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E12-T09 — Сделать label sanity plots

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Label engine" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E12-T08

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for сделать label sanity plots

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Сделать label sanity plots"
- Реализовать основной функциональный путь для задачи "Сделать label sanity plots"
- Добавить логирование, артефакты и manifests для задачи "Сделать label sanity plots"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E12-T10 — Подготовить label specification report

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Label engine" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E12-T09

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for подготовить label specification report

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Подготовить label specification report"
- Реализовать основной функциональный путь для задачи "Подготовить label specification report"
- Добавить логирование, артефакты и manifests для задачи "Подготовить label specification report"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

## E13 — Price, momentum and relative-return features

### E13-T01 — Реализовать raw return features

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Price, momentum and relative-return features" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E12-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать raw return features

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать raw return features"
- Реализовать основной функциональный путь для задачи "Реализовать raw return features"
- Добавить логирование, артефакты и manifests для задачи "Реализовать raw return features"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E13-T02 — Реализовать ex-1 momentum features

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Price, momentum and relative-return features" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E13-T01, E12-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать ex-1 momentum features

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать ex-1 momentum features"
- Реализовать основной функциональный путь для задачи "Реализовать ex-1 momentum features"
- Добавить логирование, артефакты и manifests для задачи "Реализовать ex-1 momentum features"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E13-T03 — Реализовать reversal features

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Price, momentum and relative-return features" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E13-T02, E12-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать reversal features

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать reversal features"
- Реализовать основной функциональный путь для задачи "Реализовать reversal features"
- Добавить логирование, артефакты и manifests для задачи "Реализовать reversal features"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E13-T04 — Реализовать benchmark-relative return features

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Price, momentum and relative-return features" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E13-T03

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать benchmark-relative return features

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать benchmark-relative return features"
- Реализовать основной функциональный путь для задачи "Реализовать benchmark-relative return features"
- Добавить логирование, артефакты и manifests для задачи "Реализовать benchmark-relative return features"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E13-T05 — Реализовать sector-relative return features

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Price, momentum and relative-return features" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E13-T04

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать sector-relative return features

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать sector-relative return features"
- Реализовать основной функциональный путь для задачи "Реализовать sector-relative return features"
- Добавить логирование, артефакты и manifests для задачи "Реализовать sector-relative return features"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E13-T06 — Реализовать cross-sectional return ranks

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Price, momentum and relative-return features" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E13-T05

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать cross-sectional return ranks

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать cross-sectional return ranks"
- Реализовать основной функциональный путь для задачи "Реализовать cross-sectional return ranks"
- Добавить логирование, артефакты и manifests для задачи "Реализовать cross-sectional return ranks"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E13-T07 — Реализовать rolling drawup/drawdown primitives

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Price, momentum and relative-return features" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E13-T06

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать rolling drawup/drawdown primitives

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать rolling drawup/drawdown primitives"
- Реализовать основной функциональный путь для задачи "Реализовать rolling drawup/drawdown primitives"
- Добавить логирование, артефакты и manifests для задачи "Реализовать rolling drawup/drawdown primitives"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E13-T08 — Реализовать price gap features при наличии open

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Price, momentum and relative-return features" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E13-T07

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать price gap features при наличии open

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать price gap features при наличии open"
- Реализовать основной функциональный путь для задачи "Реализовать price gap features при наличии open"
- Добавить логирование, артефакты и manifests для задачи "Реализовать price gap features при наличии open"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E13-T09 — Провести feature sanity diagnostics для price family

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Price, momentum and relative-return features" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E13-T08

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for провести feature sanity diagnostics для price family

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Провести feature sanity diagnostics для price family"
- Реализовать основной функциональный путь для задачи "Провести feature sanity diagnostics для price family"
- Добавить логирование, артефакты и manifests для задачи "Провести feature sanity diagnostics для price family"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E13-T10 — Зарегистрировать price family в feature registry

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Price, momentum and relative-return features" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E13-T09

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for зарегистрировать price family в feature registry

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Зарегистрировать price family в feature registry"
- Реализовать основной функциональный путь для задачи "Зарегистрировать price family в feature registry"
- Добавить логирование, артефакты и manifests для задачи "Зарегистрировать price family в feature registry"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

## E14 — Volatility, liquidity and trend features

### E14-T01 — Реализовать realized volatility features

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Volatility, liquidity and trend features" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E13-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать realized volatility features

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать realized volatility features"
- Реализовать основной функциональный путь для задачи "Реализовать realized volatility features"
- Добавить логирование, артефакты и manifests для задачи "Реализовать realized volatility features"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E14-T02 — Реализовать downside/upside volatility features

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Volatility, liquidity and trend features" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E14-T01, E13-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать downside/upside volatility features

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать downside/upside volatility features"
- Реализовать основной функциональный путь для задачи "Реализовать downside/upside volatility features"
- Добавить логирование, артефакты и manifests для задачи "Реализовать downside/upside volatility features"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E14-T03 — Реализовать Parkinson and Garman-Klass features

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Volatility, liquidity and trend features" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E14-T02, E13-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать parkinson and garman-klass features

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать Parkinson and Garman-Klass features"
- Реализовать основной функциональный путь для задачи "Реализовать Parkinson and Garman-Klass features"
- Добавить логирование, артефакты и manifests для задачи "Реализовать Parkinson and Garman-Klass features"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E14-T04 — Реализовать ATR-like features

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Volatility, liquidity and trend features" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E14-T03

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать atr-like features

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать ATR-like features"
- Реализовать основной функциональный путь для задачи "Реализовать ATR-like features"
- Добавить логирование, артефакты и manifests для задачи "Реализовать ATR-like features"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E14-T05 — Реализовать ADV features

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Volatility, liquidity and trend features" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E14-T04

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать adv features

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать ADV features"
- Реализовать основной функциональный путь для задачи "Реализовать ADV features"
- Добавить логирование, артефакты и manifests для задачи "Реализовать ADV features"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E14-T06 — Реализовать volume surprise features

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Volatility, liquidity and trend features" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E14-T05

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать volume surprise features

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать volume surprise features"
- Реализовать основной функциональный путь для задачи "Реализовать volume surprise features"
- Добавить логирование, артефакты и manifests для задачи "Реализовать volume surprise features"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E14-T07 — Реализовать Amihud and turnover proxies

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Volatility, liquidity and trend features" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E14-T06

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать amihud and turnover proxies

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать Amihud and turnover proxies"
- Реализовать основной функциональный путь для задачи "Реализовать Amihud and turnover proxies"
- Добавить логирование, артефакты и manifests для задачи "Реализовать Amihud and turnover proxies"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E14-T08 — Реализовать moving-average distance features

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Volatility, liquidity and trend features" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E14-T07

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать moving-average distance features

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать moving-average distance features"
- Реализовать основной функциональный путь для задачи "Реализовать moving-average distance features"
- Добавить логирование, артефакты и manifests для задачи "Реализовать moving-average distance features"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E14-T09 — Реализовать breakout and distance-to-high-low features

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Volatility, liquidity and trend features" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E14-T08

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать breakout and distance-to-high-low features

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать breakout and distance-to-high-low features"
- Реализовать основной функциональный путь для задачи "Реализовать breakout and distance-to-high-low features"
- Добавить логирование, артефакты и manifests для задачи "Реализовать breakout and distance-to-high-low features"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E14-T10 — Зарегистрировать vol/liquidity/trend families в registry

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Volatility, liquidity and trend features" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E14-T09

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for зарегистрировать vol/liquidity/trend families в registry

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Зарегистрировать vol/liquidity/trend families в registry"
- Реализовать основной функциональный путь для задачи "Зарегистрировать vol/liquidity/trend families в registry"
- Добавить логирование, артефакты и manifests для задачи "Зарегистрировать vol/liquidity/trend families в registry"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

## E15 — Fundamental and staleness features

### E15-T01 — Реализовать valuation features

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Fundamental and staleness features" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E14-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать valuation features

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать valuation features"
- Реализовать основной функциональный путь для задачи "Реализовать valuation features"
- Добавить логирование, артефакты и manifests для задачи "Реализовать valuation features"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E15-T02 — Реализовать quality features

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Fundamental and staleness features" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E15-T01, E14-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать quality features

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать quality features"
- Реализовать основной функциональный путь для задачи "Реализовать quality features"
- Добавить логирование, артефакты и manifests для задачи "Реализовать quality features"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E15-T03 — Реализовать growth features

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Fundamental and staleness features" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E15-T02, E14-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать growth features

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать growth features"
- Реализовать основной функциональный путь для задачи "Реализовать growth features"
- Добавить логирование, артефакты и manifests для задачи "Реализовать growth features"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E15-T04 — Реализовать leverage features

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Fundamental and staleness features" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E15-T03

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать leverage features

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать leverage features"
- Реализовать основной функциональный путь для задачи "Реализовать leverage features"
- Добавить логирование, артефакты и manifests для задачи "Реализовать leverage features"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E15-T05 — Реализовать solvency and liquidity ratios

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Fundamental and staleness features" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E15-T04

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать solvency and liquidity ratios

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать solvency and liquidity ratios"
- Реализовать основной функциональный путь для задачи "Реализовать solvency and liquidity ratios"
- Добавить логирование, артефакты и manifests для задачи "Реализовать solvency and liquidity ratios"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E15-T06 — Реализовать days-since-last-filing feature

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Fundamental and staleness features" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E15-T05

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать days-since-last-filing feature

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать days-since-last-filing feature"
- Реализовать основной функциональный путь для задачи "Реализовать days-since-last-filing feature"
- Добавить логирование, артефакты и manifests для задачи "Реализовать days-since-last-filing feature"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E15-T07 — Реализовать staleness threshold flags

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Fundamental and staleness features" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E15-T06

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать staleness threshold flags

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать staleness threshold flags"
- Реализовать основной функциональный путь для задачи "Реализовать staleness threshold flags"
- Добавить логирование, артефакты и manifests для задачи "Реализовать staleness threshold flags"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E15-T08 — Реализовать missingness flags for key metrics

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Fundamental and staleness features" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E15-T07

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать missingness flags for key metrics

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать missingness flags for key metrics"
- Реализовать основной функциональный путь для задачи "Реализовать missingness flags for key metrics"
- Добавить логирование, артефакты и manifests для задачи "Реализовать missingness flags for key metrics"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E15-T09 — Реализовать fundamental interaction features

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Fundamental and staleness features" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E15-T08

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать fundamental interaction features

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать fundamental interaction features"
- Реализовать основной функциональный путь для задачи "Реализовать fundamental interaction features"
- Добавить логирование, артефакты и manifests для задачи "Реализовать fundamental interaction features"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E15-T10 — Зарегистрировать fundamentals family в registry

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Fundamental and staleness features" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E15-T09

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for зарегистрировать fundamentals family в registry

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Зарегистрировать fundamentals family в registry"
- Реализовать основной функциональный путь для задачи "Зарегистрировать fundamentals family в registry"
- Добавить логирование, артефакты и manifests для задачи "Зарегистрировать fundamentals family в registry"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

## E16 — Preprocessing and neutralization

### E16-T01 — Реализовать lag application layer

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Preprocessing and neutralization" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E15-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать lag application layer

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать lag application layer"
- Реализовать основной функциональный путь для задачи "Реализовать lag application layer"
- Добавить логирование, артефакты и manifests для задачи "Реализовать lag application layer"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E16-T02 — Реализовать invalid masking layer

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Preprocessing and neutralization" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E16-T01, E15-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать invalid masking layer

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать invalid masking layer"
- Реализовать основной функциональный путь для задачи "Реализовать invalid masking layer"
- Добавить логирование, артефакты и manifests для задачи "Реализовать invalid masking layer"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E16-T03 — Реализовать winsorizer

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Preprocessing and neutralization" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E16-T02, E15-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать winsorizer

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать winsorizer"
- Реализовать основной функциональный путь для задачи "Реализовать winsorizer"
- Добавить логирование, артефакты и manifests для задачи "Реализовать winsorizer"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E16-T04 — Реализовать z-score scaler by date

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Preprocessing and neutralization" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E16-T03

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать z-score scaler by date

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать z-score scaler by date"
- Реализовать основной функциональный путь для задачи "Реализовать z-score scaler by date"
- Добавить логирование, артефакты и manifests для задачи "Реализовать z-score scaler by date"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E16-T05 — Реализовать robust z-score scaler by date

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Preprocessing and neutralization" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E16-T04

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать robust z-score scaler by date

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать robust z-score scaler by date"
- Реализовать основной функциональный путь для задачи "Реализовать robust z-score scaler by date"
- Добавить логирование, артефакты и manifests для задачи "Реализовать robust z-score scaler by date"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E16-T06 — Реализовать percentile-rank normalization

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Preprocessing and neutralization" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E16-T05

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать percentile-rank normalization

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать percentile-rank normalization"
- Реализовать основной функциональный путь для задачи "Реализовать percentile-rank normalization"
- Добавить логирование, артефакты и manifests для задачи "Реализовать percentile-rank normalization"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E16-T07 — Реализовать sector neutralization

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Preprocessing and neutralization" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E16-T06

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать sector neutralization

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать sector neutralization"
- Реализовать основной функциональный путь для задачи "Реализовать sector neutralization"
- Добавить логирование, артефакты и manifests для задачи "Реализовать sector neutralization"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E16-T08 — Реализовать beta neutralization

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Preprocessing and neutralization" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E16-T07

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать beta neutralization

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать beta neutralization"
- Реализовать основной функциональный путь для задачи "Реализовать beta neutralization"
- Добавить логирование, артефакты и manifests для задачи "Реализовать beta neutralization"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E16-T09 — Реализовать fold-safe fit/apply API

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Preprocessing and neutralization" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E16-T08

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать fold-safe fit/apply api

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать fold-safe fit/apply API"
- Реализовать основной функциональный путь для задачи "Реализовать fold-safe fit/apply API"
- Добавить логирование, артефакты и manifests для задачи "Реализовать fold-safe fit/apply API"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E16-T10 — Подготовить preprocessing diagnostics report

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Preprocessing and neutralization" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E16-T09

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for подготовить preprocessing diagnostics report

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Подготовить preprocessing diagnostics report"
- Реализовать основной функциональный путь для задачи "Подготовить preprocessing diagnostics report"
- Добавить логирование, артефакты и manifests для задачи "Подготовить preprocessing diagnostics report"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

## E17 — Dataset assembly and manifests

### E17-T01 — Собрать silver market layer

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Dataset assembly and manifests" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E16-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for собрать silver market layer

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Собрать silver market layer"
- Реализовать основной функциональный путь для задачи "Собрать silver market layer"
- Добавить логирование, артефакты и manifests для задачи "Собрать silver market layer"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E17-T02 — Собрать silver fundamentals PIT layer

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Dataset assembly and manifests" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E17-T01, E16-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for собрать silver fundamentals pit layer

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Собрать silver fundamentals PIT layer"
- Реализовать основной функциональный путь для задачи "Собрать silver fundamentals PIT layer"
- Добавить логирование, артефакты и manifests для задачи "Собрать silver fundamentals PIT layer"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E17-T03 — Собрать universe snapshot layer

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Dataset assembly and manifests" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E17-T02, E16-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for собрать universe snapshot layer

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Собрать universe snapshot layer"
- Реализовать основной функциональный путь для задачи "Собрать universe snapshot layer"
- Добавить логирование, артефакты и manifests для задачи "Собрать universe snapshot layer"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E17-T04 — Собрать raw feature layer

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Dataset assembly and manifests" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E17-T03

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for собрать raw feature layer

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Собрать raw feature layer"
- Реализовать основной функциональный путь для задачи "Собрать raw feature layer"
- Добавить логирование, артефакты и manifests для задачи "Собрать raw feature layer"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E17-T05 — Собрать processed feature layer

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Dataset assembly and manifests" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E17-T04

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for собрать processed feature layer

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Собрать processed feature layer"
- Реализовать основной функциональный путь для задачи "Собрать processed feature layer"
- Добавить логирование, артефакты и manifests для задачи "Собрать processed feature layer"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E17-T06 — Присоединить labels к feature panel

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Dataset assembly and manifests" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E17-T05

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for присоединить labels к feature panel

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Присоединить labels к feature panel"
- Реализовать основной функциональный путь для задачи "Присоединить labels к feature panel"
- Добавить логирование, артефакты и manifests для задачи "Присоединить labels к feature panel"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E17-T07 — Считать row-level diagnostics

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Dataset assembly and manifests" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E17-T06

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for считать row-level diagnostics

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Считать row-level diagnostics"
- Реализовать основной функциональный путь для задачи "Считать row-level diagnostics"
- Добавить логирование, артефакты и manifests для задачи "Считать row-level diagnostics"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E17-T08 — Сохранить gold model panel

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Dataset assembly and manifests" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E17-T07

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for сохранить gold model panel

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Сохранить gold model panel"
- Реализовать основной функциональный путь для задачи "Сохранить gold model panel"
- Добавить логирование, артефакты и manifests для задачи "Сохранить gold model panel"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E17-T09 — Сгенерировать dataset manifest

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Dataset assembly and manifests" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E17-T08

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for сгенерировать dataset manifest

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Сгенерировать dataset manifest"
- Реализовать основной функциональный путь для задачи "Сгенерировать dataset manifest"
- Добавить логирование, артефакты и manifests для задачи "Сгенерировать dataset manifest"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E17-T10 — Сгенерировать dataset coverage report

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Dataset assembly and manifests" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P1`

**Зависимости:** E17-T09

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for сгенерировать dataset coverage report

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Сгенерировать dataset coverage report"
- Реализовать основной функциональный путь для задачи "Сгенерировать dataset coverage report"
- Добавить логирование, артефакты и manifests для задачи "Сгенерировать dataset coverage report"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

## E18 — Split engine and walk-forward validation

### E18-T01 — Реализовать rolling split generator

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Split engine and walk-forward validation" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E17-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать rolling split generator

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать rolling split generator"
- Реализовать основной функциональный путь для задачи "Реализовать rolling split generator"
- Добавить логирование, артефакты и manifests для задачи "Реализовать rolling split generator"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E18-T02 — Реализовать expanding split option

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Split engine and walk-forward validation" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E18-T01, E17-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать expanding split option

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать expanding split option"
- Реализовать основной функциональный путь для задачи "Реализовать expanding split option"
- Добавить логирование, артефакты и manifests для задачи "Реализовать expanding split option"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E18-T03 — Реализовать purge logic

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Split engine and walk-forward validation" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E18-T02, E17-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать purge logic

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать purge logic"
- Реализовать основной функциональный путь для задачи "Реализовать purge logic"
- Добавить логирование, артефакты и manifests для задачи "Реализовать purge logic"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E18-T04 — Реализовать embargo logic

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Split engine and walk-forward validation" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E18-T03

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать embargo logic

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать embargo logic"
- Реализовать основной функциональный путь для задачи "Реализовать embargo logic"
- Добавить логирование, артефакты и manifests для задачи "Реализовать embargo logic"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E18-T05 — Сохранять fold metadata

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Split engine and walk-forward validation" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E18-T04

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for сохранять fold metadata

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Сохранять fold metadata"
- Реализовать основной функциональный путь для задачи "Сохранять fold metadata"
- Добавить логирование, артефакты и manifests для задачи "Сохранять fold metadata"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E18-T06 — Визуализировать fold timeline

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Split engine and walk-forward validation" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E18-T05

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for визуализировать fold timeline

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Визуализировать fold timeline"
- Реализовать основной функциональный путь для задачи "Визуализировать fold timeline"
- Добавить логирование, артефакты и manifests для задачи "Визуализировать fold timeline"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E18-T07 — Проверять no-date-overlap invariant

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Split engine and walk-forward validation" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E18-T06

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for проверять no-date-overlap invariant

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Проверять no-date-overlap invariant"
- Реализовать основной функциональный путь для задачи "Проверять no-date-overlap invariant"
- Добавить логирование, артефакты и manifests для задачи "Проверять no-date-overlap invariant"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E18-T08 — Проверять no-label-overlap leakage invariant

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Split engine and walk-forward validation" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E18-T07

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for проверять no-label-overlap leakage invariant

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Проверять no-label-overlap leakage invariant"
- Реализовать основной функциональный путь для задачи "Проверять no-label-overlap leakage invariant"
- Добавить логирование, артефакты и manifests для задачи "Проверять no-label-overlap leakage invariant"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E18-T09 — Поддержать nested tuning protocol

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Split engine and walk-forward validation" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E18-T08

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for поддержать nested tuning protocol

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Поддержать nested tuning protocol"
- Реализовать основной функциональный путь для задачи "Поддержать nested tuning protocol"
- Добавить логирование, артефакты и manifests для задачи "Поддержать nested tuning protocol"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E18-T10 — Сформировать validation protocol report

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Split engine and walk-forward validation" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E18-T09

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for сформировать validation protocol report

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Сформировать validation protocol report"
- Реализовать основной функциональный путь для задачи "Сформировать validation protocol report"
- Добавить логирование, артефакты и manifests для задачи "Сформировать validation protocol report"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

## E19 — Baselines and linear models

### E19-T01 — Реализовать random-score baseline

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Baselines and linear models" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E18-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать random-score baseline

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать random-score baseline"
- Реализовать основной функциональный путь для задачи "Реализовать random-score baseline"
- Добавить логирование, артефакты и manifests для задачи "Реализовать random-score baseline"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E19-T02 — Реализовать heuristic reversal baseline

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Baselines and linear models" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E19-T01, E18-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать heuristic reversal baseline

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать heuristic reversal baseline"
- Реализовать основной функциональный путь для задачи "Реализовать heuristic reversal baseline"
- Добавить логирование, артефакты и manifests для задачи "Реализовать heuristic reversal baseline"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E19-T03 — Реализовать heuristic momentum baseline

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Baselines and linear models" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E19-T02, E18-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать heuristic momentum baseline

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать heuristic momentum baseline"
- Реализовать основной функциональный путь для задачи "Реализовать heuristic momentum baseline"
- Добавить логирование, артефакты и manifests для задачи "Реализовать heuristic momentum baseline"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E19-T04 — Реализовать heuristic blended baseline

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Baselines and linear models" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E19-T03

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать heuristic blended baseline

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать heuristic blended baseline"
- Реализовать основной функциональный путь для задачи "Реализовать heuristic blended baseline"
- Добавить логирование, артефакты и manifests для задачи "Реализовать heuristic blended baseline"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E19-T05 — Реализовать ridge regression baseline

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Baselines and linear models" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E19-T04

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать ridge regression baseline

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать ridge regression baseline"
- Реализовать основной функциональный путь для задачи "Реализовать ridge regression baseline"
- Добавить логирование, артефакты и manifests для задачи "Реализовать ridge regression baseline"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E19-T06 — Реализовать lasso regression baseline

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Baselines and linear models" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E19-T05

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать lasso regression baseline

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать lasso regression baseline"
- Реализовать основной функциональный путь для задачи "Реализовать lasso regression baseline"
- Добавить логирование, артефакты и manifests для задачи "Реализовать lasso regression baseline"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E19-T07 — Реализовать elastic-net optional baseline

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Baselines and linear models" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E19-T06

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать elastic-net optional baseline

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать elastic-net optional baseline"
- Реализовать основной функциональный путь для задачи "Реализовать elastic-net optional baseline"
- Добавить логирование, артефакты и manifests для задачи "Реализовать elastic-net optional baseline"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E19-T08 — Реализовать baseline comparison harness

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Baselines and linear models" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E19-T07

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать baseline comparison harness

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать baseline comparison harness"
- Реализовать основной функциональный путь для задачи "Реализовать baseline comparison harness"
- Добавить логирование, артефакты и manifests для задачи "Реализовать baseline comparison harness"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E19-T09 — Сохранять linear model coefficients by fold

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Baselines and linear models" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E19-T08

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for сохранять linear model coefficients by fold

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Сохранять linear model coefficients by fold"
- Реализовать основной функциональный путь для задачи "Сохранять linear model coefficients by fold"
- Добавить логирование, артефакты и manifests для задачи "Сохранять linear model coefficients by fold"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E19-T10 — Сформировать baseline comparison report

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Baselines and linear models" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E19-T09

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for сформировать baseline comparison report

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Сформировать baseline comparison report"
- Реализовать основной функциональный путь для задачи "Сформировать baseline comparison report"
- Добавить логирование, артефакты и manifests для задачи "Сформировать baseline comparison report"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

## E20 — Tree models and tuning

### E20-T01 — Реализовать gradient boosting regressor wrapper

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Tree models and tuning" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E19-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать gradient boosting regressor wrapper

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать gradient boosting regressor wrapper"
- Реализовать основной функциональный путь для задачи "Реализовать gradient boosting regressor wrapper"
- Добавить логирование, артефакты и manifests для задачи "Реализовать gradient boosting regressor wrapper"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E20-T02 — Реализовать gradient boosting ranker wrapper

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Tree models and tuning" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E20-T01, E19-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать gradient boosting ranker wrapper

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать gradient boosting ranker wrapper"
- Реализовать основной функциональный путь для задачи "Реализовать gradient boosting ranker wrapper"
- Добавить логирование, артефакты и manifests для задачи "Реализовать gradient boosting ranker wrapper"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E20-T03 — Описать search space для tuning

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Tree models and tuning" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E20-T02, E19-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for описать search space для tuning

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Описать search space для tuning"
- Реализовать основной функциональный путь для задачи "Описать search space для tuning"
- Добавить логирование, артефакты и manifests для задачи "Описать search space для tuning"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E20-T04 — Реализовать Optuna/internal tuner adapter

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Tree models and tuning" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E20-T03

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать optuna/internal tuner adapter

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать Optuna/internal tuner adapter"
- Реализовать основной функциональный путь для задачи "Реализовать Optuna/internal tuner adapter"
- Добавить логирование, артефакты и manifests для задачи "Реализовать Optuna/internal tuner adapter"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E20-T05 — Реализовать early stopping logging

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Tree models and tuning" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E20-T04

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать early stopping logging

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать early stopping logging"
- Реализовать основной функциональный путь для задачи "Реализовать early stopping logging"
- Добавить логирование, артефакты и manifests для задачи "Реализовать early stopping logging"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E20-T06 — Логировать feature importance per fold

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Tree models and tuning" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E20-T05

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for логировать feature importance per fold

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Логировать feature importance per fold"
- Реализовать основной функциональный путь для задачи "Логировать feature importance per fold"
- Добавить логирование, артефакты и manifests для задачи "Логировать feature importance per fold"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E20-T07 — Реализовать calibration diagnostics

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Tree models and tuning" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E20-T06

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать calibration diagnostics

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать calibration diagnostics"
- Реализовать основной функциональный путь для задачи "Реализовать calibration diagnostics"
- Добавить логирование, артефакты и manifests для задачи "Реализовать calibration diagnostics"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E20-T08 — Сравнить regression vs ranking objective

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Tree models and tuning" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E20-T07

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for сравнить regression vs ranking objective

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Сравнить regression vs ranking objective"
- Реализовать основной функциональный путь для задачи "Сравнить regression vs ranking objective"
- Добавить логирование, артефакты и manifests для задачи "Сравнить regression vs ranking objective"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E20-T09 — Сохранить best params и tuning traces

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Tree models and tuning" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E20-T08

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for сохранить best params и tuning traces

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Сохранить best params и tuning traces"
- Реализовать основной функциональный путь для задачи "Сохранить best params и tuning traces"
- Добавить логирование, артефакты и manifests для задачи "Сохранить best params и tuning traces"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E20-T10 — Сформировать advanced model report

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Tree models and tuning" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E20-T09

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for сформировать advanced model report

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Сформировать advanced model report"
- Реализовать основной функциональный путь для задачи "Сформировать advanced model report"
- Добавить логирование, артефакты и manifests для задачи "Сформировать advanced model report"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

## E21 — OOF predictions and prediction store

### E21-T01 — Реализовать standardized prediction schema

**Цель:** Реализовать завершенный LEGO-компонент в эпике "OOF predictions and prediction store" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E20-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать standardized prediction schema

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать standardized prediction schema"
- Реализовать основной функциональный путь для задачи "Реализовать standardized prediction schema"
- Добавить логирование, артефакты и manifests для задачи "Реализовать standardized prediction schema"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E21-T02 — Сохранять raw predictions per fold

**Цель:** Реализовать завершенный LEGO-компонент в эпике "OOF predictions and prediction store" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E21-T01, E20-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for сохранять raw predictions per fold

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Сохранять raw predictions per fold"
- Реализовать основной функциональный путь для задачи "Сохранять raw predictions per fold"
- Добавить логирование, артефакты и manifests для задачи "Сохранять raw predictions per fold"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E21-T03 — Сохранять rank predictions per fold

**Цель:** Реализовать завершенный LEGO-компонент в эпике "OOF predictions and prediction store" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E21-T02, E20-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for сохранять rank predictions per fold

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Сохранять rank predictions per fold"
- Реализовать основной функциональный путь для задачи "Сохранять rank predictions per fold"
- Добавить логирование, артефакты и manifests для задачи "Сохранять rank predictions per fold"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E21-T04 — Сохранять bucket predictions per fold

**Цель:** Реализовать завершенный LEGO-компонент в эпике "OOF predictions and prediction store" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E21-T03

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for сохранять bucket predictions per fold

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Сохранять bucket predictions per fold"
- Реализовать основной функциональный путь для задачи "Сохранять bucket predictions per fold"
- Добавить логирование, артефакты и manifests для задачи "Сохранять bucket predictions per fold"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E21-T05 — Сшивать all folds into OOF table

**Цель:** Реализовать завершенный LEGO-компонент в эпике "OOF predictions and prediction store" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E21-T04

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for сшивать all folds into oof table

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Сшивать all folds into OOF table"
- Реализовать основной функциональный путь для задачи "Сшивать all folds into OOF table"
- Добавить логирование, артефакты и manifests для задачи "Сшивать all folds into OOF table"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E21-T06 — Проверять uniqueness by date-security-model

**Цель:** Реализовать завершенный LEGO-компонент в эпике "OOF predictions and prediction store" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E21-T05

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for проверять uniqueness by date-security-model

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Проверять uniqueness by date-security-model"
- Реализовать основной функциональный путь для задачи "Проверять uniqueness by date-security-model"
- Добавить логирование, артефакты и manifests для задачи "Проверять uniqueness by date-security-model"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E21-T07 — Сохранять prediction manifests

**Цель:** Реализовать завершенный LEGO-компонент в эпике "OOF predictions and prediction store" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E21-T06

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for сохранять prediction manifests

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Сохранять prediction manifests"
- Реализовать основной функциональный путь для задачи "Сохранять prediction manifests"
- Добавить логирование, артефакты и manifests для задачи "Сохранять prediction manifests"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E21-T08 — Добавить prediction coverage diagnostics

**Цель:** Реализовать завершенный LEGO-компонент в эпике "OOF predictions and prediction store" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E21-T07

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for добавить prediction coverage diagnostics

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Добавить prediction coverage diagnostics"
- Реализовать основной функциональный путь для задачи "Добавить prediction coverage diagnostics"
- Добавить логирование, артефакты и manifests для задачи "Добавить prediction coverage diagnostics"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E21-T09 — Подготовить OOF-only guardrails

**Цель:** Реализовать завершенный LEGO-компонент в эпике "OOF predictions and prediction store" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E21-T08

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for подготовить oof-only guardrails

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Подготовить OOF-only guardrails"
- Реализовать основной функциональный путь для задачи "Подготовить OOF-only guardrails"
- Добавить логирование, артефакты и manifests для задачи "Подготовить OOF-only guardrails"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E21-T10 — Сформировать prediction store report

**Цель:** Реализовать завершенный LEGO-компонент в эпике "OOF predictions and prediction store" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E21-T09

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for сформировать prediction store report

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Сформировать prediction store report"
- Реализовать основной функциональный путь для задачи "Сформировать prediction store report"
- Добавить логирование, артефакты и manifests для задачи "Сформировать prediction store report"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

## E22 — Portfolio construction and constraints

### E22-T01 — Реализовать score-to-rank mapping

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Portfolio construction and constraints" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E21-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать score-to-rank mapping

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать score-to-rank mapping"
- Реализовать основной функциональный путь для задачи "Реализовать score-to-rank mapping"
- Добавить логирование, артефакты и manifests для задачи "Реализовать score-to-rank mapping"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E22-T02 — Реализовать equal-weight decile portfolio

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Portfolio construction and constraints" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E22-T01, E21-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать equal-weight decile portfolio

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать equal-weight decile portfolio"
- Реализовать основной функциональный путь для задачи "Реализовать equal-weight decile portfolio"
- Добавить логирование, артефакты и manifests для задачи "Реализовать equal-weight decile portfolio"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E22-T03 — Реализовать rank-weighted portfolio

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Portfolio construction and constraints" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E22-T02, E21-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать rank-weighted portfolio

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать rank-weighted portfolio"
- Реализовать основной функциональный путь для задачи "Реализовать rank-weighted portfolio"
- Добавить логирование, артефакты и manifests для задачи "Реализовать rank-weighted portfolio"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E22-T04 — Реализовать sector-neutral portfolio mode

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Portfolio construction and constraints" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E22-T03

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать sector-neutral portfolio mode

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать sector-neutral portfolio mode"
- Реализовать основной функциональный путь для задачи "Реализовать sector-neutral portfolio mode"
- Добавить логирование, артефакты и manifests для задачи "Реализовать sector-neutral portfolio mode"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E22-T05 — Реализовать beta-neutral portfolio mode

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Portfolio construction and constraints" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E22-T04

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать beta-neutral portfolio mode

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать beta-neutral portfolio mode"
- Реализовать основной функциональный путь для задачи "Реализовать beta-neutral portfolio mode"
- Добавить логирование, артефакты и manifests для задачи "Реализовать beta-neutral portfolio mode"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E22-T06 — Реализовать name caps and sector caps

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Portfolio construction and constraints" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E22-T05

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать name caps and sector caps

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать name caps and sector caps"
- Реализовать основной функциональный путь для задачи "Реализовать name caps and sector caps"
- Добавить логирование, артефакты и manifests для задачи "Реализовать name caps and sector caps"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E22-T07 — Реализовать turnover caps

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Portfolio construction and constraints" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E22-T06

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать turnover caps

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать turnover caps"
- Реализовать основной функциональный путь для задачи "Реализовать turnover caps"
- Добавить логирование, артефакты и manifests для задачи "Реализовать turnover caps"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E22-T08 — Реализовать participation caps

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Portfolio construction and constraints" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E22-T07

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать participation caps

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать participation caps"
- Реализовать основной функциональный путь для задачи "Реализовать participation caps"
- Добавить логирование, артефакты и manifests для задачи "Реализовать participation caps"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E22-T09 — Логировать rejected names and reasons

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Portfolio construction and constraints" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E22-T08

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for логировать rejected names and reasons

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Логировать rejected names and reasons"
- Реализовать основной функциональный путь для задачи "Логировать rejected names and reasons"
- Добавить логирование, артефакты и manifests для задачи "Логировать rejected names and reasons"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E22-T10 — Сформировать portfolio construction report

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Portfolio construction and constraints" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E22-T09

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for сформировать portfolio construction report

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Сформировать portfolio construction report"
- Реализовать основной функциональный путь для задачи "Сформировать portfolio construction report"
- Добавить логирование, артефакты и manifests для задачи "Сформировать portfolio construction report"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

## E23 — Costs and execution simulation

### E23-T01 — Реализовать commission model

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Costs and execution simulation" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E22-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать commission model

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать commission model"
- Реализовать основной функциональный путь для задачи "Реализовать commission model"
- Добавить логирование, артефакты и manifests для задачи "Реализовать commission model"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E23-T02 — Реализовать spread proxy model

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Costs and execution simulation" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E23-T01, E22-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать spread proxy model

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать spread proxy model"
- Реализовать основной функциональный путь для задачи "Реализовать spread proxy model"
- Добавить логирование, артефакты и manifests для задачи "Реализовать spread proxy model"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E23-T03 — Реализовать slippage proxy model

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Costs and execution simulation" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E23-T02, E22-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать slippage proxy model

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать slippage proxy model"
- Реализовать основной функциональный путь для задачи "Реализовать slippage proxy model"
- Добавить логирование, артефакты и manifests для задачи "Реализовать slippage proxy model"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E23-T04 — Реализовать impact proxy model

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Costs and execution simulation" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E23-T03

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать impact proxy model

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать impact proxy model"
- Реализовать основной функциональный путь для задачи "Реализовать impact proxy model"
- Добавить логирование, артефакты и manifests для задачи "Реализовать impact proxy model"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E23-T05 — Реализовать borrow model

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Costs and execution simulation" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E23-T04

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать borrow model

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать borrow model"
- Реализовать основной функциональный путь для задачи "Реализовать borrow model"
- Добавить логирование, артефакты и manifests для задачи "Реализовать borrow model"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E23-T06 — Реализовать cost scenario switching

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Costs and execution simulation" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E23-T05

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать cost scenario switching

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать cost scenario switching"
- Реализовать основной функциональный путь для задачи "Реализовать cost scenario switching"
- Добавить логирование, артефакты и manifests для задачи "Реализовать cost scenario switching"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E23-T07 — Реализовать trade generation from target weights

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Costs and execution simulation" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E23-T06

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать trade generation from target weights

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать trade generation from target weights"
- Реализовать основной функциональный путь для задачи "Реализовать trade generation from target weights"
- Добавить логирование, артефакты и manifests для задачи "Реализовать trade generation from target weights"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E23-T08 — Реализовать next-open execution simulation

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Costs and execution simulation" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E23-T07

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать next-open execution simulation

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать next-open execution simulation"
- Реализовать основной функциональный путь для задачи "Реализовать next-open execution simulation"
- Добавить логирование, артефакты и manifests для задачи "Реализовать next-open execution simulation"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E23-T09 — Логировать fill ratios and clipped trades

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Costs and execution simulation" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E23-T08

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for логировать fill ratios and clipped trades

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Логировать fill ratios and clipped trades"
- Реализовать основной функциональный путь для задачи "Логировать fill ratios and clipped trades"
- Добавить логирование, артефакты и manifests для задачи "Логировать fill ratios and clipped trades"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E23-T10 — Сформировать execution-cost diagnostics report

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Costs and execution simulation" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E23-T09

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for сформировать execution-cost diagnostics report

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Сформировать execution-cost diagnostics report"
- Реализовать основной функциональный путь для задачи "Сформировать execution-cost diagnostics report"
- Добавить логирование, артефакты и manifests для задачи "Сформировать execution-cost diagnostics report"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

## E24 — Backtest engine and capacity

### E24-T01 — Реализовать daily portfolio state machine

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Backtest engine and capacity" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E23-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать daily portfolio state machine

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать daily portfolio state machine"
- Реализовать основной функциональный путь для задачи "Реализовать daily portfolio state machine"
- Добавить логирование, артефакты и manifests для задачи "Реализовать daily portfolio state machine"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E24-T02 — Реализовать holdings snapshots

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Backtest engine and capacity" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E24-T01, E23-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать holdings snapshots

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать holdings snapshots"
- Реализовать основной функциональный путь для задачи "Реализовать holdings snapshots"
- Добавить логирование, артефакты и manifests для задачи "Реализовать holdings snapshots"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E24-T03 — Реализовать gross PnL accounting

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Backtest engine and capacity" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E24-T02, E23-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать gross pnl accounting

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать gross PnL accounting"
- Реализовать основной функциональный путь для задачи "Реализовать gross PnL accounting"
- Добавить логирование, артефакты и manifests для задачи "Реализовать gross PnL accounting"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E24-T04 — Реализовать net PnL accounting

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Backtest engine and capacity" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E24-T03

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать net pnl accounting

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать net PnL accounting"
- Реализовать основной функциональный путь для задачи "Реализовать net PnL accounting"
- Добавить логирование, артефакты и manifests для задачи "Реализовать net PnL accounting"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E24-T05 — Реализовать long-short attribution

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Backtest engine and capacity" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E24-T04

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать long-short attribution

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать long-short attribution"
- Реализовать основной функциональный путь для задачи "Реализовать long-short attribution"
- Добавить логирование, артефакты и manifests для задачи "Реализовать long-short attribution"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E24-T06 — Реализовать sleeve logic for multi-day holds

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Backtest engine and capacity" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E24-T05

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать sleeve logic for multi-day holds

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать sleeve logic for multi-day holds"
- Реализовать основной функциональный путь для задачи "Реализовать sleeve logic for multi-day holds"
- Добавить логирование, артефакты и manifests для задачи "Реализовать sleeve logic for multi-day holds"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E24-T07 — Реализовать AUM ladder runner

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Backtest engine and capacity" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E24-T06

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать aum ladder runner

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать AUM ladder runner"
- Реализовать основной функциональный путь для задачи "Реализовать AUM ladder runner"
- Добавить логирование, артефакты и manifests для задачи "Реализовать AUM ladder runner"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E24-T08 — Реализовать participation statistics

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Backtest engine and capacity" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E24-T07

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать participation statistics

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать participation statistics"
- Реализовать основной функциональный путь для задачи "Реализовать participation statistics"
- Добавить логирование, артефакты и manifests для задачи "Реализовать participation statistics"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E24-T09 — Реализовать capacity sensitivity outputs

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Backtest engine and capacity" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E24-T08

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать capacity sensitivity outputs

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать capacity sensitivity outputs"
- Реализовать основной функциональный путь для задачи "Реализовать capacity sensitivity outputs"
- Добавить логирование, артефакты и manifests для задачи "Реализовать capacity sensitivity outputs"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E24-T10 — Сформировать backtest-and-capacity report

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Backtest engine and capacity" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E24-T09

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for сформировать backtest-and-capacity report

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Сформировать backtest-and-capacity report"
- Реализовать основной функциональный путь для задачи "Сформировать backtest-and-capacity report"
- Добавить логирование, артефакты и manifests для задачи "Сформировать backtest-and-capacity report"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

## E25 — Evaluation, robustness and reporting

### E25-T01 — Реализовать predictive metrics suite

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Evaluation, robustness and reporting" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E24-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать predictive metrics suite

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать predictive metrics suite"
- Реализовать основной функциональный путь для задачи "Реализовать predictive metrics suite"
- Добавить логирование, артефакты и manifests для задачи "Реализовать predictive metrics suite"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E25-T02 — Реализовать portfolio metrics suite

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Evaluation, robustness and reporting" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E25-T01, E24-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать portfolio metrics suite

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать portfolio metrics suite"
- Реализовать основной функциональный путь для задачи "Реализовать portfolio metrics suite"
- Добавить логирование, артефакты и manifests для задачи "Реализовать portfolio metrics suite"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E25-T03 — Реализовать exposure diagnostics suite

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Evaluation, robustness and reporting" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E25-T02, E24-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать exposure diagnostics suite

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать exposure diagnostics suite"
- Реализовать основной функциональный путь для задачи "Реализовать exposure diagnostics suite"
- Добавить логирование, артефакты и manifests для задачи "Реализовать exposure diagnostics suite"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E25-T04 — Реализовать regime analysis suite

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Evaluation, robustness and reporting" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E25-T03

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать regime analysis suite

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать regime analysis suite"
- Реализовать основной функциональный путь для задачи "Реализовать regime analysis suite"
- Добавить логирование, артефакты и manifests для задачи "Реализовать regime analysis suite"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E25-T05 — Реализовать decay and model-aging suite

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Evaluation, robustness and reporting" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E25-T04

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать decay and model-aging suite

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать decay and model-aging suite"
- Реализовать основной функциональный путь для задачи "Реализовать decay and model-aging suite"
- Добавить логирование, артефакты и manifests для задачи "Реализовать decay and model-aging suite"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E25-T06 — Реализовать feature-family ablation matrix

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Evaluation, robustness and reporting" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E25-T05

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать feature-family ablation matrix

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать feature-family ablation matrix"
- Реализовать основной функциональный путь для задачи "Реализовать feature-family ablation matrix"
- Добавить логирование, артефакты и manifests для задачи "Реализовать feature-family ablation matrix"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E25-T07 — Реализовать preprocessing ablation matrix

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Evaluation, robustness and reporting" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E25-T06

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать preprocessing ablation matrix

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать preprocessing ablation matrix"
- Реализовать основной функциональный путь для задачи "Реализовать preprocessing ablation matrix"
- Добавить логирование, артефакты и manifests для задачи "Реализовать preprocessing ablation matrix"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E25-T08 — Реализовать cost sensitivity matrix

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Evaluation, robustness and reporting" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E25-T07

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать cost sensitivity matrix

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать cost sensitivity matrix"
- Реализовать основной функциональный путь для задачи "Реализовать cost sensitivity matrix"
- Добавить логирование, артефакты и manifests для задачи "Реализовать cost sensitivity matrix"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E25-T09 — Реализовать final report generator

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Evaluation, robustness and reporting" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E25-T08

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for реализовать final report generator

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Реализовать final report generator"
- Реализовать основной функциональный путь для задачи "Реализовать final report generator"
- Добавить логирование, артефакты и manifests для задачи "Реализовать final report generator"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E25-T10 — Сформировать executive summary template

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Evaluation, robustness and reporting" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E25-T09

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for сформировать executive summary template

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Сформировать executive summary template"
- Реализовать основной функциональный путь для задачи "Сформировать executive summary template"
- Добавить логирование, артефакты и manifests для задачи "Сформировать executive summary template"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

## E26 — Testing, CI and release readiness

### E26-T01 — Написать unit tests for utilities

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Testing, CI and release readiness" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E25-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for написать unit tests for utilities

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Написать unit tests for utilities"
- Реализовать основной функциональный путь для задачи "Написать unit tests for utilities"
- Добавить логирование, артефакты и manifests для задачи "Написать unit tests for utilities"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E26-T02 — Написать unit tests for feature formulas

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Testing, CI and release readiness" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E26-T01, E25-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for написать unit tests for feature formulas

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Написать unit tests for feature formulas"
- Реализовать основной функциональный путь для задачи "Написать unit tests for feature formulas"
- Добавить логирование, артефакты и manifests для задачи "Написать unit tests for feature formulas"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E26-T03 — Написать unit tests for label formulas

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Testing, CI and release readiness" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E26-T02, E25-T10

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for написать unit tests for label formulas

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Написать unit tests for label formulas"
- Реализовать основной функциональный путь для задачи "Написать unit tests for label formulas"
- Добавить логирование, артефакты и manifests для задачи "Написать unit tests for label formulas"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E26-T04 — Написать integration tests for data pipeline

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Testing, CI and release readiness" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E26-T03

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for написать integration tests for data pipeline

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Написать integration tests for data pipeline"
- Реализовать основной функциональный путь для задачи "Написать integration tests for data pipeline"
- Добавить логирование, артефакты и manifests для задачи "Написать integration tests for data pipeline"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E26-T05 — Написать leakage tests

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Testing, CI and release readiness" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E26-T04

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for написать leakage tests

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Написать leakage tests"
- Реализовать основной функциональный путь для задачи "Написать leakage tests"
- Добавить логирование, артефакты и manifests для задачи "Написать leakage tests"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E26-T06 — Написать regression tests on fixed fixture dataset

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Testing, CI and release readiness" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E26-T05

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for написать regression tests on fixed fixture dataset

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Написать regression tests on fixed fixture dataset"
- Реализовать основной функциональный путь для задачи "Написать regression tests on fixed fixture dataset"
- Добавить логирование, артефакты и manifests для задачи "Написать regression tests on fixed fixture dataset"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E26-T07 — Настроить CI pipeline

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Testing, CI and release readiness" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E26-T06

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for настроить ci pipeline

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Настроить CI pipeline"
- Реализовать основной функциональный путь для задачи "Настроить CI pipeline"
- Добавить логирование, артефакты и manifests для задачи "Настроить CI pipeline"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E26-T08 — Добавить style/type/test gates

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Testing, CI and release readiness" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E26-T07

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for добавить style/type/test gates

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Добавить style/type/test gates"
- Реализовать основной функциональный путь для задачи "Добавить style/type/test gates"
- Добавить логирование, артефакты и manifests для задачи "Добавить style/type/test gates"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E26-T09 — Подготовить release checklist and packaging

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Testing, CI and release readiness" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E26-T08

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for подготовить release checklist and packaging

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Подготовить release checklist and packaging"
- Реализовать основной функциональный путь для задачи "Подготовить release checklist and packaging"
- Добавить логирование, артефакты и manifests для задачи "Подготовить release checklist and packaging"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

### E26-T10 — Подготовить reviewer handoff bundle

**Цель:** Реализовать завершенный LEGO-компонент в эпике "Testing, CI and release readiness" без скрытых зависимостей и с явными acceptance criteria.

**Приоритет:** `P2`

**Зависимости:** E26-T09

**Входы:**
- config files
- repository state
- outputs of previous epics

**Выходы:**
- artifact for подготовить reviewer handoff bundle

**Микрошаги LEGO:**
- Уточнить границы и инварианты для задачи "Подготовить reviewer handoff bundle"
- Реализовать основной функциональный путь для задачи "Подготовить reviewer handoff bundle"
- Добавить логирование, артефакты и manifests для задачи "Подготовить reviewer handoff bundle"
- Покрыть задачу тестами и подготовить acceptance evidence

**Acceptance criteria:**
- Код или спецификация добавлены в соответствующий модуль
- Все обязательные поля/артефакты сохраняются
- Логи, manifests и метрики доступны для ревью
- Нет нарушения point-in-time и anti-leakage инвариантов

## 14. Порядок сборки проекта агентом разработки

Рекомендуемый порядок:
1. bootstrap и config contracts;
2. reference/security master;
3. ingest layers;
4. QA;
5. PIT;
6. universe;
7. labels + features;
8. preprocessing + gold panel;
9. splits;
10. baselines;
11. advanced models;
12. OOF store;
13. portfolio and execution;
14. backtest and capacity;
15. evaluation/reporting;
16. tests/CI/release.

## 15. Что считать финальным DoD

- End-to-end pipeline выполняется без ручных notebook-шагов.
- Все manifests и artifacts присутствуют.
- Все features зарегистрированы и документированы.
- Все labels выровнены с execution semantics.
- Все модели оцениваются только через purged walk-forward.
- Финальный backtest использует только OOF predictions.
- Есть gross/net/cost/capacity/regime/decay/ablation sections.
- Все acceptance tests зеленые или явно задокументированы как waived with justification.

## 16. Состав архива

- `MASTER_SPEC.md` — главный файл со всем содержимым.
- `machine_spec.yaml` — machine-readable сводка.
- `configs/*.yaml` — шаблоны конфигов.
- `schemas/table_schemas.yaml` — полные схемы таблиц.
- `schemas/feature_registry.yaml` — реестр features с формулами.
- `tests/acceptance_tests.yaml` — acceptance suite.
- `pseudocode/pipeline_pseudocode.md` — псевдокод pipeline stages.
- `backlog/backlog.yaml` и `backlog/backlog.csv` — backlog в machine-readable и tabular виде.
