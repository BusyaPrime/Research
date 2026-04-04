from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from alpha_research.config.models import CostsConfig


SCENARIO_MULTIPLIERS = {
    "optimistic": 0.75,
    "base": 1.0,
    "stressed": 1.5,
    "severely_stressed": 2.0,
}


def _scenario_multiplier(scenario: str) -> float:
    return SCENARIO_MULTIPLIERS.get(scenario, 1.0)


def calculate_commission_cost(executed_notional: float, costs_config: CostsConfig, *, scenario: str = "base") -> float:
    return abs(float(executed_notional)) * (costs_config.commission_bps * _scenario_multiplier(scenario) / 10_000.0)


def calculate_spread_half_bps(price: float, liquidity_bucket: str, costs_config: CostsConfig, *, scenario: str = "base") -> float:
    price_value = float(price)
    bucket_value = str(liquidity_bucket)
    matched = []
    for bucket in costs_config.spread_proxy.buckets:
        if bucket.price_min <= price_value < bucket.price_max and bucket.adv_bucket == bucket_value:
            matched.append(bucket.half_spread_bps)
    if matched:
        return float(matched[0]) * _scenario_multiplier(scenario)
    fallback = min(bucket.half_spread_bps for bucket in costs_config.spread_proxy.buckets)
    return float(fallback) * _scenario_multiplier(scenario)


def _borrow_bps_daily(borrow_status: str, costs_config: CostsConfig, *, scenario: str = "base") -> float:
    status = str(borrow_status).lower()
    if status == "low":
        value = costs_config.borrow.low_borrow_bps_daily
    elif status == "medium":
        value = costs_config.borrow.medium_borrow_bps_daily
    elif status == "high":
        value = costs_config.borrow.high_borrow_bps_daily
    elif status == "unborrowable":
        value = 0.0 if costs_config.borrow.hard_to_borrow_policy == "ban_or_extreme_stress" else costs_config.borrow.high_borrow_bps_daily * 5.0
    else:
        value = costs_config.borrow.medium_borrow_bps_daily
    return float(value) * _scenario_multiplier(scenario)


def calculate_borrow_cost(holdings: pd.DataFrame, aum: float, costs_config: CostsConfig, *, scenario: str = "base") -> float:
    if holdings.empty:
        return 0.0
    frame = holdings.copy()
    frame["weight"] = pd.to_numeric(frame["weight"], errors="coerce").fillna(0.0)
    frame["borrow_status"] = frame.get("borrow_status", pd.Series("medium", index=frame.index)).fillna("medium")
    shorts = frame.loc[frame["weight"] < 0].copy()
    if shorts.empty:
        return 0.0
    costs = shorts.apply(
        lambda row: abs(float(row["weight"])) * float(aum) * (_borrow_bps_daily(str(row["borrow_status"]), costs_config, scenario=scenario) / 10_000.0),
        axis=1,
    )
    return float(costs.sum())


@dataclass(frozen=True)
class TradeCostResult:
    trades: pd.DataFrame
    totals: dict[str, float]


def compute_trade_costs(executed_trades: pd.DataFrame, costs_config: CostsConfig, *, scenario: str = "base") -> TradeCostResult:
    if executed_trades.empty:
        empty = executed_trades.copy()
        for column in ("commission_cost", "spread_cost", "slippage_cost", "impact_cost", "total_cost"):
            empty[column] = pd.Series(dtype="float64")
        return TradeCostResult(
            trades=empty,
            totals={"commission_cost": 0.0, "spread_cost": 0.0, "slippage_cost": 0.0, "impact_cost": 0.0, "total_cost": 0.0},
        )

    frame = executed_trades.copy()
    frame["executed_notional"] = pd.to_numeric(frame["executed_notional"], errors="coerce").fillna(0.0)
    frame["adv20_usd_t"] = pd.to_numeric(frame["adv20_usd_t"], errors="coerce").replace(0.0, np.nan)
    frame["open"] = pd.to_numeric(frame["open"], errors="coerce").fillna(0.0)
    frame["liquidity_bucket"] = frame.get("liquidity_bucket", pd.Series("medium", index=frame.index)).fillna("medium")
    participation = (frame["executed_notional"].abs() / frame["adv20_usd_t"]).fillna(0.0)

    frame["commission_cost"] = frame["executed_notional"].abs().map(lambda value: calculate_commission_cost(float(value), costs_config, scenario=scenario))
    frame["spread_cost"] = frame.apply(
        lambda row: abs(float(row["executed_notional"])) * (calculate_spread_half_bps(float(row["open"]), str(row["liquidity_bucket"]), costs_config, scenario=scenario) / 10_000.0),
        axis=1,
    )
    slippage_bps = (costs_config.slippage_proxy.base_bps + costs_config.slippage_proxy.k1 * np.sqrt(participation)) * _scenario_multiplier(scenario)
    impact_bps = (costs_config.impact_proxy.k2 * np.sqrt(participation)) * _scenario_multiplier(scenario)
    frame["slippage_cost"] = frame["executed_notional"].abs() * slippage_bps / 10_000.0
    frame["impact_cost"] = frame["executed_notional"].abs() * impact_bps / 10_000.0
    frame["total_cost"] = frame[["commission_cost", "spread_cost", "slippage_cost", "impact_cost"]].sum(axis=1)

    totals = {column: float(frame[column].sum()) for column in ("commission_cost", "spread_cost", "slippage_cost", "impact_cost", "total_cost")}
    return TradeCostResult(trades=frame, totals=totals)
