from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from alpha_research.backtest.engine import run_backtest
from alpha_research.config.models import CapacityConfig, CostsConfig, PortfolioConfig
from alpha_research.data.schemas import validate_dataframe
from alpha_research.time.calendar import ExchangeCalendarAdapter


@dataclass(frozen=True)
class CapacityRunResult:
    results: pd.DataFrame
    diagnostics: pd.DataFrame


def _sharpe(returns: pd.Series) -> float | None:
    clean = pd.to_numeric(returns, errors="coerce").dropna()
    if len(clean) < 2:
        return None
    std = float(clean.std(ddof=0))
    if std == 0:
        return None
    return float(clean.mean() / std * np.sqrt(252.0))


def run_capacity_analysis(
    oof_predictions: pd.DataFrame,
    universe_snapshots: pd.DataFrame,
    feature_panel: pd.DataFrame,
    silver_market: pd.DataFrame,
    portfolio_config: PortfolioConfig,
    costs_config: CostsConfig,
    capacity_config: CapacityConfig,
    calendar: ExchangeCalendarAdapter,
    *,
    model_name: str | None = None,
) -> CapacityRunResult:
    result_rows: list[dict[str, object]] = []
    diagnostic_rows: list[dict[str, object]] = []

    for aum_level in capacity_config.aum_ladder_usd:
        for scenario_name, max_participation in capacity_config.participation_limits.model_dump().items():
            scenario_portfolio = portfolio_config.model_copy(update={"max_participation_pct_adv": float(max_participation)})
            backtest = run_backtest(
                oof_predictions,
                universe_snapshots,
                feature_panel,
                silver_market,
                scenario_portfolio,
                costs_config,
                calendar,
                model_name=model_name,
                initial_aum=float(aum_level),
                scenario="base",
            )
            trades = backtest.trades.copy()
            if trades.empty:
                median_participation = None
                p95_participation = None
                fraction_trades_clipped = None
                fraction_names_untradable = None
                max_participation_obs = None
            else:
                median_participation = float(pd.to_numeric(trades["participation_ratio"], errors="coerce").median())
                p95_participation = float(pd.to_numeric(trades["participation_ratio"], errors="coerce").quantile(0.95))
                fraction_trades_clipped = float(pd.to_numeric(trades["clipped_flag"], errors="coerce").fillna(0.0).mean())
                fraction_names_untradable = float(pd.to_numeric(trades["untradable_flag"], errors="coerce").fillna(0.0).mean())
                max_participation_obs = float(pd.to_numeric(trades["participation_ratio"], errors="coerce").max())
            net_sharpe = _sharpe(backtest.daily_returns["net_return"]) if not backtest.daily_returns.empty else None

            result_rows.append(
                {
                    "aum_level": float(aum_level),
                    "scenario": str(scenario_name),
                    "net_sharpe": net_sharpe,
                    "median_participation": median_participation,
                    "p95_participation": p95_participation,
                    "fraction_trades_clipped": fraction_trades_clipped,
                    "fraction_names_untradable": fraction_names_untradable,
                }
            )
            diagnostic_rows.append(
                {
                    "aum_level": float(aum_level),
                    "scenario": str(scenario_name),
                    "max_participation": max_participation_obs,
                    "daily_state_rows": int(len(backtest.daily_state)),
                    "trade_rows": int(len(trades)),
                }
            )

    validated = validate_dataframe(pd.DataFrame(result_rows), "capacity_results")
    diagnostics = pd.DataFrame(diagnostic_rows).sort_values(["aum_level", "scenario"], kind="stable").reset_index(drop=True)
    return CapacityRunResult(results=validated, diagnostics=diagnostics)
