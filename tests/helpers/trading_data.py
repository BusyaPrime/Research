from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from alpha_research.config.models import (
    BorrowConfig,
    CapacityConfig,
    CapacityParticipationLimits,
    CostsConfig,
    ParametricCostModel,
    PortfolioConfig,
    PriceAdvBucket,
    SpreadProxyConfig,
)
from alpha_research.time.calendar import ExchangeCalendarAdapter


@dataclass(frozen=True)
class TradingResearchBundle:
    calendar: ExchangeCalendarAdapter
    oof_predictions: pd.DataFrame
    universe_snapshots: pd.DataFrame
    feature_panel: pd.DataFrame
    silver_market: pd.DataFrame


def make_portfolio_config(**overrides) -> PortfolioConfig:
    base = {
        "mode": "decile_equal_weight",
        "gross_exposure": 1.0,
        "net_target": 0.0,
        "long_quantile": 0.2,
        "short_quantile": 0.2,
        "rebalance_frequency": "daily",
        "holding_period_days": 5,
        "overlap_sleeves": True,
        "max_weight_per_name": 0.25,
        "max_sector_net_exposure": 0.2,
        "max_sector_gross_exposure": 1.0,
        "max_turnover_per_rebalance": 1.0,
        "beta_neutralize": False,
        "sector_neutralize": False,
        "max_participation_pct_adv": 0.01,
        "reject_unborrowable_shorts": True,
    }
    base.update(overrides)
    return PortfolioConfig(**base)


def make_costs_config() -> CostsConfig:
    return CostsConfig(
        commission_bps=0.5,
        spread_proxy=SpreadProxyConfig(
            method="bucket_by_price_and_adv",
            buckets=[
                PriceAdvBucket(price_min=5.0, price_max=10.0, adv_bucket="low", half_spread_bps=15.0),
                PriceAdvBucket(price_min=10.0, price_max=25.0, adv_bucket="medium", half_spread_bps=8.0),
                PriceAdvBucket(price_min=25.0, price_max=999999.0, adv_bucket="high", half_spread_bps=3.0),
            ],
        ),
        slippage_proxy=ParametricCostModel(method="participation_based", formula="slippage_bps = base_bps + k1 * sqrt(order_notional / adv_notional)", base_bps=1.0, k1=20.0),
        impact_proxy=ParametricCostModel(method="nonlinear_participation", formula="impact_bps = k2 * sqrt(order_notional / adv_notional)", k2=15.0),
        borrow=BorrowConfig(low_borrow_bps_daily=1.0, medium_borrow_bps_daily=5.0, high_borrow_bps_daily=20.0, hard_to_borrow_policy="ban_or_extreme_stress"),
        scenarios=["optimistic", "base", "stressed", "severely_stressed"],
    )


def make_capacity_config() -> CapacityConfig:
    return CapacityConfig(
        aum_ladder_usd=[1_000_000.0, 5_000_000.0, 10_000_000.0],
        participation_limits=CapacityParticipationLimits(relaxed=0.02, base=0.01, strict=0.005, ultra_strict=0.0025),
        report_metrics=["net_sharpe", "max_participation", "median_participation", "fraction_trades_clipped", "fraction_names_untradable"],
    )


def build_trading_research_bundle() -> TradingResearchBundle:
    calendar = ExchangeCalendarAdapter("XNYS")
    sessions = calendar.calendar.sessions_in_range("2024-06-03", "2024-07-15").tz_localize(None)
    securities = [
        ("SEC_00", "Tech", "high", 0.8),
        ("SEC_01", "Tech", "high", 0.9),
        ("SEC_02", "Tech", "medium", 1.0),
        ("SEC_03", "Tech", "medium", 1.1),
        ("SEC_04", "Finance", "medium", 0.7),
        ("SEC_05", "Finance", "medium", 0.8),
        ("SEC_06", "Finance", "low", 1.2),
        ("SEC_07", "Health", "high", 0.6),
        ("SEC_08", "Health", "low", 1.3),
        ("SEC_09", "Utilities", "low", 1.4),
    ]

    decision_dates = sessions[:-1]
    market_rows: list[dict[str, object]] = []
    feature_rows: list[dict[str, object]] = []
    universe_rows: list[dict[str, object]] = []
    prediction_rows: list[dict[str, object]] = []

    for day_idx, session in enumerate(sessions):
        for sec_idx, (security_id, sector, liquidity_bucket, beta) in enumerate(securities):
            open_px = 20.0 + sec_idx * 2.0 + day_idx * 0.1
            edge = (sec_idx - 4.5) / 9.0
            close_px = open_px * (1.0 + 0.01 * edge)
            adv20 = 2_000_000.0 + sec_idx * 300_000.0
            market_rows.append(
                {
                    "security_id": security_id,
                    "trade_date": session,
                    "open": open_px,
                    "close": close_px,
                    "high": max(open_px, close_px) * 1.01,
                    "low": min(open_px, close_px) * 0.99,
                    "volume": int(adv20 / max(open_px, 1.0)),
                    "dollar_volume": adv20,
                }
            )
            feature_rows.append(
                {
                    "date": session,
                    "security_id": security_id,
                    "sector": sector,
                    "beta_estimate": beta,
                    "adv20": adv20,
                    "liquidity_bucket": liquidity_bucket,
                }
            )
            universe_rows.append(
                {
                    "date": session,
                    "security_id": security_id,
                    "is_in_universe": True,
                    "exclusion_reason_code": pd.NA,
                    "price_t": close_px,
                    "adv20_usd_t": adv20,
                    "feature_coverage_ratio": 1.0,
                    "data_quality_score": 0.99,
                    "liquidity_bucket": liquidity_bucket,
                    "borrow_status": "unborrowable" if security_id == "SEC_09" else liquidity_bucket,
                }
            )

    for day_idx, decision_date in enumerate(decision_dates):
        for sec_idx, (security_id, _, _, _) in enumerate(securities):
            score = (sec_idx - 4.5) + np.sin(day_idx / 3.0) * 0.1
            prediction_rows.append(
                {
                    "date": decision_date,
                    "security_id": security_id,
                    "fold_id": "fold_000",
                    "model_name": "heuristic_blend_score",
                    "raw_prediction": score,
                    "rank_prediction": (sec_idx + 1) / len(securities),
                    "bucket_prediction": int(min(sec_idx, 9)),
                    "prediction_timestamp": pd.Timestamp("2026-01-01T00:00:00Z"),
                    "dataset_version": "ds_trade",
                    "config_hash": "cfg_test",
                }
            )

    return TradingResearchBundle(
        calendar=calendar,
        oof_predictions=pd.DataFrame(prediction_rows),
        universe_snapshots=pd.DataFrame(universe_rows),
        feature_panel=pd.DataFrame(feature_rows),
        silver_market=pd.DataFrame(market_rows),
    )
