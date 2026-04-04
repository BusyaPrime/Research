from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from alpha_research.config.models import CostsConfig, PortfolioConfig
from alpha_research.data.schemas import validate_dataframe
from alpha_research.execution.costs import calculate_borrow_cost
from alpha_research.execution.simulator import simulate_execution
from alpha_research.portfolio.targets import build_portfolio_targets, prepare_portfolio_inputs
from alpha_research.time.calendar import ExchangeCalendarAdapter


@dataclass(frozen=True)
class BacktestResult:
    daily_state: pd.DataFrame
    holdings_snapshots: pd.DataFrame
    trades: pd.DataFrame
    daily_returns: pd.DataFrame


def _mark_to_market(holdings: pd.DataFrame, market_close_frame: pd.DataFrame, aum_open: float) -> tuple[pd.DataFrame, float, float]:
    if holdings.empty:
        empty = holdings.copy()
        empty["open"] = pd.Series(dtype="float64")
        empty["close"] = pd.Series(dtype="float64")
        empty["asset_return"] = pd.Series(dtype="float64")
        empty["close_value"] = pd.Series(dtype="float64")
        return empty, 0.0, float(aum_open)

    market = market_close_frame.copy()
    market["open"] = pd.to_numeric(market["open"], errors="coerce")
    market["close"] = pd.to_numeric(market["close"], errors="coerce")
    merged = holdings.merge(market[["security_id", "open", "close"]], on="security_id", how="left")
    merged["asset_return"] = np.where(merged["open"].notna() & merged["close"].notna() & (merged["open"] != 0), merged["close"] / merged["open"] - 1.0, 0.0)
    merged["open_value"] = merged["weight"] * float(aum_open)
    merged["close_value"] = merged["open_value"] * (1.0 + merged["asset_return"])
    gross_pnl = float((merged["close_value"] - merged["open_value"]).sum())
    gross_aum_close = float(aum_open + gross_pnl)
    return merged, gross_pnl, gross_aum_close


def run_backtest(
    oof_predictions: pd.DataFrame,
    universe_snapshots: pd.DataFrame,
    feature_panel: pd.DataFrame,
    silver_market: pd.DataFrame,
    portfolio_config: PortfolioConfig,
    costs_config: CostsConfig,
    calendar: ExchangeCalendarAdapter,
    *,
    model_name: str | None = None,
    initial_aum: float = 1_000_000.0,
    scenario: str = "base",
) -> BacktestResult:
    predictions = oof_predictions.copy()
    predictions["date"] = pd.to_datetime(predictions["date"], errors="coerce").dt.normalize()
    decision_dates = sorted(predictions["date"].dropna().unique())

    holdings = pd.DataFrame(columns=["security_id", "weight", "sector", "beta_estimate", "liquidity_bucket", "borrow_status"])
    current_aum = float(initial_aum)
    state_rows: list[dict[str, object]] = []
    holdings_rows: list[dict[str, object]] = []
    trade_rows: list[pd.DataFrame] = []
    return_rows: list[dict[str, float | pd.Timestamp]] = []

    market = silver_market.copy()
    market["trade_date"] = pd.to_datetime(market["trade_date"], errors="coerce").dt.normalize()

    for decision_date in decision_dates:
        signal_frame = prepare_portfolio_inputs(decision_date, predictions, universe_snapshots, feature_panel, model_name=model_name)
        target_result = build_portfolio_targets(signal_frame, portfolio_config)
        execution_date = calendar.next_trading_day(decision_date, 1)
        market_exec = market.loc[market["trade_date"] == execution_date, ["security_id", "open", "close"]].copy()
        feature_exec = feature_panel.copy()
        feature_exec["date"] = pd.to_datetime(feature_exec["date"], errors="coerce").dt.normalize()
        feature_exec = feature_exec.loc[feature_exec["date"] == execution_date, ["security_id", "adv20", "liquidity_bucket"]].copy()
        feature_exec = feature_exec.rename(columns={"adv20": "adv20_usd_t"})
        market_exec = market_exec.merge(feature_exec, on="security_id", how="left")

        execution_result = simulate_execution(
            decision_date,
            target_result.targets,
            holdings,
            market_exec,
            portfolio_config,
            costs_config,
            aum=current_aum,
            scenario=scenario,
        )
        trade_rows.append(execution_result.executed_trades.assign(execution_date=execution_date))

        marked_holdings, gross_pnl, _ = _mark_to_market(execution_result.holdings_after_execution, market_exec, current_aum)
        borrow_cost = calculate_borrow_cost(execution_result.holdings_after_execution, current_aum, costs_config, scenario=scenario)
        total_cost = execution_result.cost_totals["total_cost"] + borrow_cost
        net_pnl = gross_pnl - total_cost
        next_aum = float(current_aum + net_pnl)

        if not marked_holdings.empty and next_aum != 0:
            close_weights = marked_holdings["close_value"] / next_aum
            holdings = marked_holdings[["security_id", "sector", "beta_estimate", "liquidity_bucket", "borrow_status"]].copy()
            holdings["weight"] = close_weights.to_numpy(dtype="float64")
        else:
            holdings = pd.DataFrame(columns=["security_id", "weight", "sector", "beta_estimate", "liquidity_bucket", "borrow_status"])

        gross_exposure = float(holdings["weight"].abs().sum()) if not holdings.empty else 0.0
        net_exposure = float(holdings["weight"].sum()) if not holdings.empty else 0.0
        turnover = float(execution_result.executed_trades["executed_trade_weight"].abs().sum()) if not execution_result.executed_trades.empty else 0.0
        state_rows.append(
            {
                "date": execution_date,
                "gross_exposure": gross_exposure,
                "net_exposure": net_exposure,
                "turnover": turnover,
                "gross_pnl": gross_pnl,
                "net_pnl": net_pnl,
                "commission_cost": execution_result.cost_totals["commission_cost"],
                "spread_cost": execution_result.cost_totals["spread_cost"],
                "slippage_cost": execution_result.cost_totals["slippage_cost"],
                "impact_cost": execution_result.cost_totals["impact_cost"],
                "borrow_cost": borrow_cost,
                "active_positions": int(len(holdings)),
                "aum": next_aum,
            }
        )
        return_rows.append({"date": execution_date, "gross_return": gross_pnl / current_aum if current_aum else 0.0, "net_return": net_pnl / current_aum if current_aum else 0.0})
        holdings_rows.append(holdings.assign(date=execution_date, aum=next_aum))
        current_aum = next_aum

    state = validate_dataframe(pd.DataFrame(state_rows), "portfolio_daily_state")
    holdings_snapshots = pd.concat(holdings_rows, ignore_index=True) if holdings_rows else pd.DataFrame(columns=["date", "security_id", "weight", "sector", "beta_estimate", "liquidity_bucket", "borrow_status", "aum"])
    trades = pd.concat(trade_rows, ignore_index=True) if trade_rows else pd.DataFrame()
    daily_returns = pd.DataFrame(return_rows)
    return BacktestResult(daily_state=state, holdings_snapshots=holdings_snapshots, trades=trades, daily_returns=daily_returns)
