from __future__ import annotations

import pandas as pd
import pytest

from alpha_research.execution.simulator import generate_trade_list, simulate_execution
from alpha_research.portfolio.targets import build_portfolio_targets, map_scores_to_ranks
from tests.helpers.trading_data import make_costs_config, make_portfolio_config


def _signal_frame() -> pd.DataFrame:
    date = pd.Timestamp("2024-06-03")
    rows = []
    sectors = ["Tech", "Tech", "Tech", "Finance", "Finance", "Finance", "Health", "Health", "Utilities", "Energy"]
    for idx in range(10):
        rows.append(
            {
                "date": date,
                "security_id": f"SEC_{idx:02d}",
                "raw_prediction": float(10 - idx),
                "is_in_universe": True,
                "sector": sectors[idx],
                "beta_estimate": 0.8 + idx * 0.05,
                "adv20_usd_t": 1_000_000.0 + idx * 100_000.0,
                "liquidity_bucket": "high" if idx < 3 else "medium" if idx < 7 else "low",
                "borrow_status": "unborrowable" if idx == 9 else "medium",
            }
        )
    return pd.DataFrame(rows)


def test_score_to_rank_mapping_is_monotonic() -> None:
    ranked = map_scores_to_ranks(_signal_frame())
    assert ranked["raw_prediction"].is_monotonic_decreasing
    assert ranked["score_rank"].is_monotonic_decreasing


def test_equal_weight_decile_portfolio_respects_gross_target() -> None:
    result = build_portfolio_targets(
        _signal_frame(),
        make_portfolio_config(beta_neutralize=False, max_sector_gross_exposure=1.0, max_sector_net_exposure=1.0, reject_unborrowable_shorts=False),
    )
    weights = result.targets["target_weight"]
    assert weights.abs().sum() == pytest.approx(1.0)
    assert result.targets.loc[result.targets["target_weight"] > 0, "target_weight"].sum() == pytest.approx(0.5)
    assert result.targets.loc[result.targets["target_weight"] < 0, "target_weight"].sum() == pytest.approx(-0.5)


def test_sector_caps_are_enforced_during_target_construction() -> None:
    config = make_portfolio_config(max_sector_gross_exposure=0.2, max_sector_net_exposure=0.05, beta_neutralize=False)
    result = build_portfolio_targets(_signal_frame(), config)
    sector_gross = result.targets.groupby("sector", dropna=False)["target_weight"].apply(lambda values: values.abs().sum())
    sector_net = result.targets.groupby("sector", dropna=False)["target_weight"].sum()
    assert (sector_gross <= config.max_sector_gross_exposure + 1e-10).all()
    assert (sector_net.abs() <= config.max_sector_net_exposure + 1e-10).all()


def test_participation_cap_clips_large_trades() -> None:
    target = pd.DataFrame(
        [
            {"date": pd.Timestamp("2024-06-03"), "security_id": "SEC_00", "target_weight": 0.2, "sector": "Tech", "beta_estimate": 1.0, "adv20_usd_t": 1_000.0, "liquidity_bucket": "low", "borrow_status": "medium"},
        ]
    )
    previous = pd.DataFrame(columns=["security_id", "weight", "sector", "beta_estimate", "liquidity_bucket", "borrow_status"])
    market = pd.DataFrame([{"security_id": "SEC_00", "open": 20.0, "close": 20.2, "adv20_usd_t": 1_000.0, "liquidity_bucket": "low"}])
    execution = simulate_execution(pd.Timestamp("2024-06-03"), target, previous, market, make_portfolio_config(max_participation_pct_adv=0.01), make_costs_config(), aum=1_000_000.0)
    assert execution.executed_trades.loc[0, "fill_ratio"] < 1.0
    assert bool(execution.executed_trades.loc[0, "clipped_flag"]) is True


def test_trade_list_is_built_from_previous_holdings_and_targets() -> None:
    target = pd.DataFrame(
        [
            {"security_id": "SEC_00", "target_weight": 0.10},
            {"security_id": "SEC_01", "target_weight": -0.10},
        ]
    )
    previous = pd.DataFrame(
        [
            {"security_id": "SEC_00", "weight": 0.05},
            {"security_id": "SEC_02", "weight": 0.03},
        ]
    )
    trades = generate_trade_list(target, previous)
    trade_map = trades.set_index("security_id")["trade_weight"].to_dict()
    assert trade_map["SEC_00"] == pytest.approx(0.05)
    assert trade_map["SEC_01"] == pytest.approx(-0.10)
    assert trade_map["SEC_02"] == pytest.approx(-0.03)


def test_next_open_execution_simulator_records_fill_ratios() -> None:
    signal = _signal_frame().iloc[:2].copy()
    signal.loc[0, "target_weight"] = 0.1
    signal.loc[1, "target_weight"] = -0.1
    target = signal[["date", "security_id", "target_weight", "sector", "beta_estimate", "adv20_usd_t", "liquidity_bucket", "borrow_status"]]
    previous = pd.DataFrame(columns=["security_id", "weight", "sector", "beta_estimate", "liquidity_bucket", "borrow_status"])
    market = pd.DataFrame(
        [
            {"security_id": "SEC_00", "open": 20.0, "close": 20.2, "adv20_usd_t": 50_000.0, "liquidity_bucket": "high"},
            {"security_id": "SEC_01", "open": 21.0, "close": 20.8, "adv20_usd_t": 50_000.0, "liquidity_bucket": "high"},
        ]
    )
    execution = simulate_execution(pd.Timestamp("2024-06-03"), target, previous, market, make_portfolio_config(max_participation_pct_adv=0.02), make_costs_config(), aum=1_000_000.0)
    assert "fill_ratio" in execution.executed_trades.columns
    assert execution.executed_trades["fill_ratio"].between(0, 1).all()


def test_constrained_beta_neutralization_hits_near_zero_beta_exposure() -> None:
    date = pd.Timestamp("2024-06-03")
    signal = pd.DataFrame(
        [
            {"date": date, "security_id": "SEC_A", "raw_prediction": 4.0, "is_in_universe": True, "sector": "Tech", "beta_estimate": 0.7, "adv20_usd_t": 2_000_000.0, "liquidity_bucket": "high", "borrow_status": "medium"},
            {"date": date, "security_id": "SEC_B", "raw_prediction": 3.0, "is_in_universe": True, "sector": "Finance", "beta_estimate": 0.9, "adv20_usd_t": 2_100_000.0, "liquidity_bucket": "high", "borrow_status": "medium"},
            {"date": date, "security_id": "SEC_C", "raw_prediction": 2.0, "is_in_universe": True, "sector": "Tech", "beta_estimate": 0.6, "adv20_usd_t": 2_200_000.0, "liquidity_bucket": "high", "borrow_status": "medium"},
            {"date": date, "security_id": "SEC_D", "raw_prediction": 1.0, "is_in_universe": True, "sector": "Finance", "beta_estimate": 1.4, "adv20_usd_t": 2_300_000.0, "liquidity_bucket": "high", "borrow_status": "medium"},
        ]
    )
    config = make_portfolio_config(
        beta_neutralize=True,
        sector_neutralize=False,
        long_quantile=0.5,
        short_quantile=0.5,
        max_weight_per_name=0.45,
        max_sector_gross_exposure=1.0,
        max_sector_net_exposure=1.0,
        reject_unborrowable_shorts=False,
    )
    result = build_portfolio_targets(signal, config)
    active = result.targets.loc[result.targets["target_weight"].abs() > 1e-12].copy()
    beta_exposure = float((pd.to_numeric(active["beta_estimate"], errors="coerce") * active["target_weight"]).sum())
    assert abs(beta_exposure) <= 1e-8
    assert active.loc[active["target_weight"] > 0, "target_weight"].sum() == pytest.approx(0.5, abs=1e-8)
    assert active.loc[active["target_weight"] < 0, "target_weight"].sum() == pytest.approx(-0.5, abs=1e-8)


def test_sector_neutralization_zeroes_sector_net_when_longs_and_shorts_exist() -> None:
    date = pd.Timestamp("2024-06-03")
    signal = pd.DataFrame(
        [
            {"date": date, "security_id": "SEC_A", "raw_prediction": 4.0, "is_in_universe": True, "sector": "Tech", "beta_estimate": 0.8, "adv20_usd_t": 2_000_000.0, "liquidity_bucket": "high", "borrow_status": "medium"},
            {"date": date, "security_id": "SEC_B", "raw_prediction": 3.0, "is_in_universe": True, "sector": "Finance", "beta_estimate": 0.9, "adv20_usd_t": 2_100_000.0, "liquidity_bucket": "high", "borrow_status": "medium"},
            {"date": date, "security_id": "SEC_C", "raw_prediction": 2.0, "is_in_universe": True, "sector": "Tech", "beta_estimate": 1.1, "adv20_usd_t": 2_200_000.0, "liquidity_bucket": "high", "borrow_status": "medium"},
            {"date": date, "security_id": "SEC_D", "raw_prediction": 1.0, "is_in_universe": True, "sector": "Finance", "beta_estimate": 1.2, "adv20_usd_t": 2_300_000.0, "liquidity_bucket": "high", "borrow_status": "medium"},
        ]
    )
    config = make_portfolio_config(
        beta_neutralize=False,
        sector_neutralize=True,
        long_quantile=0.5,
        short_quantile=0.5,
        max_weight_per_name=0.30,
        max_sector_gross_exposure=1.0,
        max_sector_net_exposure=1.0,
        reject_unborrowable_shorts=False,
    )
    result = build_portfolio_targets(signal, config)
    active = result.targets.loc[result.targets["target_weight"].abs() > 1e-12].copy()
    sector_net = active.groupby("sector", dropna=False)["target_weight"].sum()
    assert sector_net["Tech"] == pytest.approx(0.0, abs=1e-8)
    assert sector_net["Finance"] == pytest.approx(0.0, abs=1e-8)
