from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd
import pytest

from alpha_research.features.engine import build_feature_panel
from alpha_research.features.registry import feature_names_by_family, load_feature_registry
from tests.helpers.research_data import build_feature_research_bundle


@lru_cache(maxsize=8)
def _build_result(interaction_cap: int = 25):
    bundle = build_feature_research_bundle()
    result = build_feature_panel(
        bundle.silver_market,
        bundle.silver_fundamentals,
        bundle.security_master,
        bundle.universe_snapshot,
        bundle.benchmark_market,
        bundle.calendar,
        interaction_cap=interaction_cap,
    )
    return bundle, result


def _security_market(bundle, security_id: str) -> pd.DataFrame:
    frame = bundle.silver_market.loc[bundle.silver_market["security_id"] == security_id].copy()
    return frame.sort_values("trade_date", kind="stable").reset_index(drop=True)


def _feature_row(panel: pd.DataFrame, date: pd.Timestamp, security_id: str) -> pd.Series:
    return panel.loc[(panel["date"] == date) & (panel["security_id"] == security_id)].iloc[0]


def test_ret_21_matches_close_over_21_day_formula() -> None:
    bundle, result = _build_result()
    market = _security_market(bundle, "SEC_A")
    row = _feature_row(result.panel, bundle.target_date, "SEC_A")
    expected = market["close"].iloc[-1] / market["close"].iloc[-22] - 1.0
    assert row["ret_21"] == pytest.approx(expected)


def test_mom_21_ex1_excludes_last_day() -> None:
    bundle, result = _build_result()
    market = _security_market(bundle, "SEC_A")
    row = _feature_row(result.panel, bundle.target_date, "SEC_A")
    expected = market["close"].iloc[-2] / market["close"].iloc[-23] - 1.0
    assert row["mom_21_ex1"] == pytest.approx(expected)


def test_rev_1_equals_negative_ret_1() -> None:
    bundle, result = _build_result()
    row = _feature_row(result.panel, bundle.target_date, "SEC_A")
    assert row["rev_1"] == pytest.approx(-row["ret_1"])


def test_ex_bench_21_correctly_subtracts_benchmark() -> None:
    bundle, result = _build_result()
    market = _security_market(bundle, "SEC_A")
    benchmark = bundle.benchmark_market.sort_values("trade_date", kind="stable").reset_index(drop=True)
    row = _feature_row(result.panel, bundle.target_date, "SEC_A")
    stock_ret = market["close"].iloc[-1] / market["close"].iloc[-22] - 1.0
    bench_ret = benchmark["close"].iloc[-1] / benchmark["close"].iloc[-22] - 1.0
    assert row["ex_bench_21"] == pytest.approx(stock_ret - bench_ret)


def test_cs_rank_ret_21_is_computed_within_date() -> None:
    bundle, result = _build_result()
    snapshot = result.panel.loc[result.panel["date"] == bundle.target_date].sort_values("security_id", kind="stable")
    expected = snapshot["ret_21"].rank(method="average", pct=True)
    pd.testing.assert_series_equal(
        snapshot["cs_rank_ret_21"].reset_index(drop=True),
        expected.reset_index(drop=True),
        check_names=False,
    )


def test_feature_registry_contains_metadata_for_price_family() -> None:
    registry = load_feature_registry()
    meta = registry["ret_21"]
    assert meta.family == "returns"
    assert meta.lag_policy == "close_t_decision_safe"
    assert meta.missing_policy
    assert meta.normalization_policy
    assert meta.pit_semantics


def test_vol_21_uses_log_return_std() -> None:
    bundle, result = _build_result()
    market = _security_market(bundle, "SEC_A")
    log_returns = np.log(market["close"] / market["close"].shift(1))
    expected = log_returns.iloc[-21:].std(ddof=0)
    row = _feature_row(result.panel, bundle.target_date, "SEC_A")
    assert row["vol_21"] == pytest.approx(expected)


def test_parkinson_21_matches_range_based_formula() -> None:
    bundle, result = _build_result()
    market = _security_market(bundle, "SEC_A")
    window = market.iloc[-21:]
    expected = np.sqrt(((np.log(window["high"] / window["low"]) ** 2).sum()) / (4.0 * 21.0 * np.log(2.0)))
    row = _feature_row(result.panel, bundle.target_date, "SEC_A")
    assert row["parkinson_21"] == pytest.approx(expected)


def test_adv20_equals_mean_dollar_volume_over_20_days() -> None:
    bundle, result = _build_result()
    market = _security_market(bundle, "SEC_A")
    expected = market["dollar_volume"].iloc[-20:].mean()
    row = _feature_row(result.panel, bundle.target_date, "SEC_A")
    assert row["adv20"] == pytest.approx(expected)


def test_volume_surprise_20_uses_only_past_days() -> None:
    bundle, result = _build_result()
    market = _security_market(bundle, "SEC_A")
    expected = market["volume"].iloc[-1] / market["volume"].iloc[-21:-1].mean()
    row = _feature_row(result.panel, bundle.target_date, "SEC_A")
    assert row["volume_surprise_20"] == pytest.approx(expected)


def test_amihud_21_handles_zero_volume_without_infinities() -> None:
    bundle, result = _build_result()
    market = _security_market(bundle, "SEC_E")
    returns = market["close"] / market["close"].shift(1) - 1.0
    raw = np.where((market["close"] * market["volume"]) > 0, returns.abs() / (market["close"] * market["volume"]), np.nan)
    expected = pd.Series(raw).rolling(window=21, min_periods=21).mean().iloc[-1]
    row = _feature_row(result.panel, bundle.target_date, "SEC_E")
    assert not np.isinf(row["amihud_21"]) if pd.notna(row["amihud_21"]) else True
    if pd.isna(expected):
        assert pd.isna(row["amihud_21"])
    else:
        assert row["amihud_21"] == pytest.approx(expected)


def test_trend_features_are_generated_without_future_leakage() -> None:
    bundle, result = _build_result()
    market = _security_market(bundle, "SEC_A")
    previous_high = market["high"].shift(1).iloc[-20:].max()
    expected = int(market["close"].iloc[-1] > previous_high)
    row = _feature_row(result.panel, bundle.target_date, "SEC_A")
    assert row["breakout_20d_up"] == expected


def test_book_to_price_uses_pit_book_equity_and_market_cap() -> None:
    bundle, result = _build_result()
    row = _feature_row(result.panel, bundle.target_date, "SEC_A")
    expected = 200.0 / (row["close"] * 52_000_000.0)
    assert row["book_to_price"] == pytest.approx(expected)


def test_roe_uses_average_book_equity_policy() -> None:
    bundle, result = _build_result()
    row = _feature_row(result.panel, bundle.target_date, "SEC_A")
    expected = 40.0 / ((200.0 + 100.0) / 2.0)
    assert row["roe"] == pytest.approx(expected)


def test_sales_growth_yoy_uses_last_available_pit_values() -> None:
    bundle, result = _build_result()
    row = _feature_row(result.panel, bundle.target_date, "SEC_A")
    expected = 260.0 / 200.0 - 1.0
    assert row["sales_growth_yoy"] == pytest.approx(expected)


def test_days_since_last_filing_uses_trading_calendar() -> None:
    bundle, result = _build_result()
    row = _feature_row(result.panel, bundle.target_date, "SEC_A")
    expected = bundle.calendar.trading_day_distance(pd.Timestamp("2024-07-01"), bundle.target_date)
    assert row["days_since_last_filing"] == expected


def test_missingness_flags_are_set_correctly() -> None:
    bundle, result = _build_result()
    row = _feature_row(result.panel, bundle.target_date, "SEC_E")
    assert row["missing_book_to_price_flag"] == 1
    assert row["missing_quality_flag"] == 1


def test_interaction_features_respect_interaction_cap_policy() -> None:
    _, result = _build_result(interaction_cap=2)
    interaction_names = feature_names_by_family("interactions")
    expected_present = set(interaction_names[:2])
    expected_absent = set(interaction_names[2:])
    assert expected_present.issubset(result.panel.columns)
    assert expected_present.issubset(result.feature_columns)
    assert expected_absent.isdisjoint(result.panel.columns)
