from __future__ import annotations

import pandas as pd
import pytest

from alpha_research.backtest.engine import run_backtest
from alpha_research.capacity.engine import run_capacity_analysis
from alpha_research.execution.costs import calculate_borrow_cost, calculate_commission_cost, calculate_spread_half_bps
from tests.helpers.trading_data import build_trading_research_bundle, make_capacity_config, make_costs_config, make_portfolio_config


def test_commission_model_charges_bps_on_executed_notional() -> None:
    cost = calculate_commission_cost(100_000.0, make_costs_config())
    assert cost == pytest.approx(5.0)


def test_spread_proxy_uses_bucket_policy() -> None:
    half_spread = calculate_spread_half_bps(30.0, "high", make_costs_config())
    assert half_spread == pytest.approx(3.0)


def test_spread_proxy_uses_conservative_fallback_for_unknown_bucket() -> None:
    half_spread = calculate_spread_half_bps(30.0, "unknown", make_costs_config())
    assert half_spread == pytest.approx(3.0)


def test_borrow_model_charges_only_on_shorts() -> None:
    holdings = pd.DataFrame(
        [
            {"security_id": "SEC_LONG", "weight": 0.10, "borrow_status": "high"},
            {"security_id": "SEC_SHORT", "weight": -0.10, "borrow_status": "high"},
        ]
    )
    cost = calculate_borrow_cost(holdings, 1_000_000.0, make_costs_config())
    assert cost == pytest.approx(200.0)


def test_borrow_model_defaults_unknown_regime_to_conservative_high_cost() -> None:
    holdings = pd.DataFrame(
        [
            {"security_id": "SEC_SHORT", "weight": -0.10, "borrow_status": "mystery"},
        ]
    )
    cost = calculate_borrow_cost(holdings, 1_000_000.0, make_costs_config())
    assert cost == pytest.approx(200.0)


def test_backtest_state_machine_updates_holdings_daily() -> None:
    bundle = build_trading_research_bundle()
    result = run_backtest(
        bundle.oof_predictions,
        bundle.universe_snapshots,
        bundle.feature_panel,
        bundle.silver_market,
        make_portfolio_config(max_sector_gross_exposure=1.0, max_sector_net_exposure=1.0),
        make_costs_config(),
        bundle.calendar,
        model_name="heuristic_blend_score",
        initial_aum=1_000_000.0,
    )
    assert len(result.daily_state) == bundle.oof_predictions["date"].nunique()
    assert result.holdings_snapshots["date"].nunique() == len(result.daily_state)
    assert len(result.holdings_snapshots) > 0


def test_aum_ladder_runner_generates_results_for_all_levels() -> None:
    bundle = build_trading_research_bundle()
    capacity_config = make_capacity_config()
    result = run_capacity_analysis(
        bundle.oof_predictions,
        bundle.universe_snapshots,
        bundle.feature_panel,
        bundle.silver_market,
        make_portfolio_config(max_sector_gross_exposure=1.0, max_sector_net_exposure=1.0),
        make_costs_config(),
        capacity_config,
        bundle.calendar,
        model_name="heuristic_blend_score",
    )
    expected_rows = len(capacity_config.aum_ladder_usd) * len(capacity_config.participation_limits.model_dump())
    assert len(result.results) == expected_rows


def test_capacity_outputs_include_fraction_trades_clipped_and_net_sharpe() -> None:
    bundle = build_trading_research_bundle()
    result = run_capacity_analysis(
        bundle.oof_predictions,
        bundle.universe_snapshots,
        bundle.feature_panel,
        bundle.silver_market,
        make_portfolio_config(max_sector_gross_exposure=1.0, max_sector_net_exposure=1.0),
        make_costs_config(),
        make_capacity_config(),
        bundle.calendar,
        model_name="heuristic_blend_score",
    )
    assert {"fraction_trades_clipped", "net_sharpe"}.issubset(result.results.columns)
    assert result.results["fraction_trades_clipped"].notna().any()
    assert result.results["net_sharpe"].notna().any()
