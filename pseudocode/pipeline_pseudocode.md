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