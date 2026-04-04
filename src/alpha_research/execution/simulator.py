from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from alpha_research.config.models import CostsConfig, PortfolioConfig
from alpha_research.execution.costs import TradeCostResult, compute_trade_costs


def generate_trade_list(target_weights: pd.DataFrame, previous_holdings: pd.DataFrame) -> pd.DataFrame:
    target = target_weights[["security_id", "target_weight"]].copy() if not target_weights.empty else pd.DataFrame(columns=["security_id", "target_weight"])
    previous = previous_holdings[["security_id", "weight"]].copy() if not previous_holdings.empty else pd.DataFrame(columns=["security_id", "weight"])
    previous = previous.rename(columns={"weight": "previous_weight"})
    trades = previous.merge(target, on="security_id", how="outer")
    trades["previous_weight"] = pd.to_numeric(trades["previous_weight"], errors="coerce").fillna(0.0)
    trades["target_weight"] = pd.to_numeric(trades["target_weight"], errors="coerce").fillna(0.0)
    trades["trade_weight"] = trades["target_weight"] - trades["previous_weight"]
    trades["abs_trade_weight"] = trades["trade_weight"].abs()
    return trades.sort_values(["abs_trade_weight", "security_id"], ascending=[False, True], kind="stable").reset_index(drop=True)


@dataclass(frozen=True)
class ExecutionResult:
    executed_trades: pd.DataFrame
    holdings_after_execution: pd.DataFrame
    cost_totals: dict[str, float]
    untradable_count: int
    clipped_count: int


def simulate_execution(
    decision_date: str | pd.Timestamp,
    target_weights: pd.DataFrame,
    previous_holdings: pd.DataFrame,
    market_open_frame: pd.DataFrame,
    portfolio_config: PortfolioConfig,
    costs_config: CostsConfig,
    *,
    aum: float,
    scenario: str = "base",
) -> ExecutionResult:
    trades = generate_trade_list(target_weights, previous_holdings)
    target_meta = target_weights.drop(columns=["target_weight"], errors="ignore").drop_duplicates("security_id")
    trades = trades.merge(target_meta, on="security_id", how="left")
    market = market_open_frame.copy()
    trades = trades.merge(market, on="security_id", how="left", suffixes=("", "__market"))
    if "adv20_usd_t__market" in trades.columns:
        trades["adv20_usd_t"] = pd.to_numeric(trades.get("adv20_usd_t"), errors="coerce").fillna(pd.to_numeric(trades["adv20_usd_t__market"], errors="coerce"))
        trades = trades.drop(columns=["adv20_usd_t__market"])
    if "liquidity_bucket__market" in trades.columns:
        trades["liquidity_bucket"] = trades.get("liquidity_bucket", pd.Series(pd.NA, index=trades.index, dtype="string")).fillna(trades["liquidity_bucket__market"])
        trades = trades.drop(columns=["liquidity_bucket__market"])

    trades["date"] = pd.Timestamp(decision_date).normalize()
    trades["adv20_usd_t"] = pd.to_numeric(trades["adv20_usd_t"], errors="coerce")
    trades["open"] = pd.to_numeric(trades["open"], errors="coerce")
    trades["fill_ratio"] = 1.0
    trades["participation_ratio"] = 0.0
    trades["clipped_flag"] = False
    trades["untradable_flag"] = False

    desired_notional = trades["abs_trade_weight"] * float(aum)
    max_notional = trades["adv20_usd_t"].fillna(0.0) * portfolio_config.max_participation_pct_adv
    with np.errstate(divide="ignore", invalid="ignore"):
        trades["fill_ratio"] = np.where(desired_notional > 0, np.minimum(1.0, max_notional / desired_notional), 1.0)
    trades["fill_ratio"] = pd.to_numeric(trades["fill_ratio"], errors="coerce").fillna(0.0).clip(lower=0.0, upper=1.0)

    missing_market = trades["open"].isna() | trades["adv20_usd_t"].isna()
    trades.loc[missing_market, ["fill_ratio", "untradable_flag"]] = [0.0, True]

    if portfolio_config.reject_unborrowable_shorts:
        borrow_status = trades.get("borrow_status", pd.Series("medium", index=trades.index)).astype("string").str.lower()
        blocked_shorts = (trades["trade_weight"] < 0) & (borrow_status == "unborrowable")
        trades.loc[blocked_shorts, ["fill_ratio", "untradable_flag"]] = [0.0, True]

    trades["clipped_flag"] = (trades["fill_ratio"] < 0.999999) & ~trades["untradable_flag"]
    trades["executed_trade_weight"] = trades["trade_weight"] * trades["fill_ratio"]
    trades["executed_notional"] = trades["executed_trade_weight"].abs() * float(aum)
    trades["participation_ratio"] = np.where(trades["adv20_usd_t"] > 0, trades["executed_notional"] / trades["adv20_usd_t"], 0.0)

    cost_result: TradeCostResult = compute_trade_costs(trades, costs_config, scenario=scenario)
    executed = cost_result.trades.copy()
    executed["executed_weight"] = executed["previous_weight"] + executed["executed_trade_weight"]

    holdings = executed.loc[executed["executed_weight"].abs() > 1e-12, ["security_id", "executed_weight", "sector", "beta_estimate", "liquidity_bucket", "borrow_status"]].copy()
    holdings = holdings.rename(columns={"executed_weight": "weight"}).reset_index(drop=True)
    return ExecutionResult(
        executed_trades=executed.reset_index(drop=True),
        holdings_after_execution=holdings,
        cost_totals=cost_result.totals,
        untradable_count=int(executed["untradable_flag"].sum()),
        clipped_count=int(executed["clipped_flag"].sum()),
    )
