from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from alpha_research.config.models import LabelOverlapPolicy, LabelsConfig
from alpha_research.pit.builders import build_silver_fundamentals_pit, build_silver_market
from alpha_research.time.calendar import ExchangeCalendarAdapter


@dataclass(frozen=True)
class FeatureResearchBundle:
    calendar: ExchangeCalendarAdapter
    dates: pd.DatetimeIndex
    target_date: pd.Timestamp
    silver_market: pd.DataFrame
    silver_fundamentals: pd.DataFrame
    security_master: pd.DataFrame
    universe_snapshot: pd.DataFrame
    benchmark_market: pd.DataFrame


@dataclass(frozen=True)
class LabelResearchBundle:
    calendar: ExchangeCalendarAdapter
    dates: pd.DatetimeIndex
    panel: pd.DataFrame
    silver_market: pd.DataFrame
    benchmark_market: pd.DataFrame
    labels_config: LabelsConfig


def build_feature_research_bundle() -> FeatureResearchBundle:
    calendar = ExchangeCalendarAdapter("XNYS")
    dates = calendar.calendar.sessions_in_range("2024-01-02", "2025-01-31").tz_localize(None)[:260]
    securities = [
        ("SEC_A", "AAA", "Technology", "Software"),
        ("SEC_B", "BBB", "Technology", "Hardware"),
        ("SEC_C", "CCC", "Financials", "Banks"),
        ("SEC_D", "DDD", "Financials", "Insurance"),
        ("SEC_E", "EEE", "Health Care", "Biotech"),
    ]
    day_index = np.arange(len(dates))

    security_master = pd.DataFrame(
        [
            {
                "security_id": security_id,
                "symbol": symbol,
                "security_type": "common_stock",
                "exchange": "NASDAQ" if idx % 2 == 0 else "NYSE",
                "listing_date": "2020-01-01",
                "delisting_date": None,
                "sector": sector,
                "industry": industry,
                "country": "US",
                "currency": "USD",
                "is_common_stock": True,
            }
            for idx, (security_id, symbol, sector, industry) in enumerate(securities)
        ]
    )

    market_rows: list[dict[str, object]] = []
    for idx, (security_id, _, _, _) in enumerate(securities):
        base_price = 25.0 + idx * 7.5
        trend = 0.11 + idx * 0.02
        seasonal = np.sin(day_index / 9.0 + idx) * (0.7 + 0.1 * idx)
        close = base_price + trend * day_index + seasonal
        open_px = close * (0.997 + idx * 0.0002)
        high = np.maximum(open_px, close) * (1.01 + 0.0005 * np.cos(day_index / 11.0))
        low = np.minimum(open_px, close) * (0.99 - 0.0003 * np.sin(day_index / 13.0))
        volume = 450_000 + idx * 90_000 + (day_index % 23) * 4_000
        if security_id == "SEC_E":
            volume = volume.astype("int64")
            volume[day_index % 17 == 0] = 0

        for i, date in enumerate(dates):
            market_rows.append(
                {
                    "security_id": security_id,
                    "trade_date": date,
                    "open": float(open_px[i]),
                    "high": float(high[i]),
                    "low": float(low[i]),
                    "close": float(close[i]),
                    "adj_close": float(close[i]),
                    "volume": int(volume[i]),
                    "dollar_volume": float(close[i] * volume[i]),
                    "is_price_valid": True,
                    "is_volume_valid": True,
                    "tradable_flag_prelim": True,
                    "data_quality_score": 0.97 - idx * 0.01,
                    "data_version": "test_v1",
                }
            )
    silver_market = build_silver_market(pd.DataFrame(market_rows))

    benchmark_close = 100.0 + 0.18 * day_index + np.sin(day_index / 10.0) * 1.4
    benchmark_open = benchmark_close * 0.999
    benchmark_market = pd.DataFrame(
        {
            "trade_date": dates,
            "open": benchmark_open,
            "high": benchmark_close * 1.01,
            "low": benchmark_close * 0.99,
            "close": benchmark_close,
        }
    )

    adv20 = (
        silver_market.sort_values(["security_id", "trade_date"], kind="stable")
        .groupby("security_id", sort=False)["dollar_volume"]
        .transform(lambda values: values.rolling(window=20, min_periods=1).mean())
    )
    universe_snapshot = pd.DataFrame(
        {
            "date": silver_market["trade_date"],
            "security_id": silver_market["security_id"],
            "is_in_universe": True,
            "exclusion_reason_code": pd.Series(pd.NA, index=silver_market.index, dtype="string"),
            "price_t": silver_market["close"],
            "adv20_usd_t": adv20,
            "feature_coverage_ratio": 1.0,
            "data_quality_score": silver_market["data_quality_score"],
            "liquidity_bucket": silver_market["security_id"].map(
                {
                    "SEC_A": "high",
                    "SEC_B": "high",
                    "SEC_C": "medium",
                    "SEC_D": "medium",
                    "SEC_E": "low",
                }
            ),
        }
    )

    old_available = pd.Timestamp("2024-01-01T20:00:00Z")
    new_available = pd.Timestamp("2024-07-01T20:00:00Z")
    metric_payloads = {
        "SEC_A": {
            "old": {
                "book_equity": 100.0,
                "net_income_ttm": 20.0,
                "revenue_ttm": 200.0,
                "operating_cashflow_ttm": 22.0,
                "gross_profit_ttm": 60.0,
                "operating_income_ttm": 35.0,
                "total_assets": 320.0,
                "total_debt": 80.0,
                "ebit_ttm": 40.0,
                "interest_expense_ttm": 5.0,
                "current_assets": 120.0,
                "current_liabilities": 60.0,
                "shares_outstanding": 50_000_000.0,
            },
            "new": {
                "book_equity": 200.0,
                "net_income_ttm": 40.0,
                "revenue_ttm": 260.0,
                "operating_cashflow_ttm": 45.0,
                "gross_profit_ttm": 82.0,
                "operating_income_ttm": 50.0,
                "total_assets": 380.0,
                "total_debt": 96.0,
                "ebit_ttm": 58.0,
                "interest_expense_ttm": 6.0,
                "current_assets": 140.0,
                "current_liabilities": 68.0,
                "shares_outstanding": 52_000_000.0,
            },
        },
        "SEC_B": {
            "old": {
                "book_equity": 130.0,
                "net_income_ttm": 24.0,
                "revenue_ttm": 225.0,
                "operating_cashflow_ttm": 27.0,
                "gross_profit_ttm": 68.0,
                "operating_income_ttm": 39.0,
                "total_assets": 350.0,
                "total_debt": 88.0,
                "ebit_ttm": 45.0,
                "interest_expense_ttm": 5.5,
                "current_assets": 130.0,
                "current_liabilities": 63.0,
                "shares_outstanding": 48_000_000.0,
            },
            "new": {
                "book_equity": 180.0,
                "net_income_ttm": 34.0,
                "revenue_ttm": 270.0,
                "operating_cashflow_ttm": 36.0,
                "gross_profit_ttm": 79.0,
                "operating_income_ttm": 46.0,
                "total_assets": 395.0,
                "total_debt": 102.0,
                "ebit_ttm": 53.0,
                "interest_expense_ttm": 6.4,
                "current_assets": 142.0,
                "current_liabilities": 70.0,
                "shares_outstanding": 49_000_000.0,
            },
        },
        "SEC_C": {
            "old": {
                "book_equity": 150.0,
                "net_income_ttm": 18.0,
                "revenue_ttm": 240.0,
                "operating_cashflow_ttm": 20.0,
                "gross_profit_ttm": 75.0,
                "operating_income_ttm": 32.0,
                "total_assets": 420.0,
                "total_debt": 110.0,
                "ebit_ttm": 36.0,
                "interest_expense_ttm": 7.0,
                "current_assets": 155.0,
                "current_liabilities": 74.0,
                "shares_outstanding": 60_000_000.0,
            },
            "new": {
                "book_equity": 175.0,
                "net_income_ttm": 23.0,
                "revenue_ttm": 255.0,
                "operating_cashflow_ttm": 25.0,
                "gross_profit_ttm": 83.0,
                "operating_income_ttm": 36.0,
                "total_assets": 445.0,
                "total_debt": 120.0,
                "ebit_ttm": 42.0,
                "interest_expense_ttm": 7.6,
                "current_assets": 162.0,
                "current_liabilities": 78.0,
                "shares_outstanding": 61_500_000.0,
            },
        },
        "SEC_D": {
            "old": {
                "book_equity": 110.0,
                "net_income_ttm": 16.0,
                "revenue_ttm": 180.0,
                "operating_cashflow_ttm": 18.0,
                "gross_profit_ttm": 54.0,
                "operating_income_ttm": 28.0,
                "total_assets": 310.0,
                "total_debt": 95.0,
                "ebit_ttm": 33.0,
                "interest_expense_ttm": 6.2,
                "current_assets": 118.0,
                "current_liabilities": 58.0,
                "shares_outstanding": 43_000_000.0,
            },
            "new": {
                "book_equity": 150.0,
                "net_income_ttm": 24.0,
                "revenue_ttm": 205.0,
                "operating_cashflow_ttm": 28.0,
                "gross_profit_ttm": 63.0,
                "operating_income_ttm": 34.0,
                "total_assets": 335.0,
                "total_debt": 99.0,
                "ebit_ttm": 39.0,
                "interest_expense_ttm": 6.6,
                "current_assets": 126.0,
                "current_liabilities": 60.0,
                "shares_outstanding": 44_500_000.0,
            },
        },
        "SEC_E": {
            "old": {
                "net_income_ttm": 12.0,
                "revenue_ttm": 150.0,
                "operating_cashflow_ttm": 13.0,
                "operating_income_ttm": 20.0,
                "total_assets": 260.0,
                "total_debt": 70.0,
                "ebit_ttm": 24.0,
                "interest_expense_ttm": 4.2,
                "current_assets": 95.0,
                "current_liabilities": 50.0,
                "shares_outstanding": 39_000_000.0,
            },
            "new": {
                "net_income_ttm": 13.0,
                "revenue_ttm": 162.0,
                "operating_cashflow_ttm": 14.0,
                "operating_income_ttm": 21.0,
                "total_assets": 280.0,
                "total_debt": 74.0,
                "ebit_ttm": 25.0,
                "interest_expense_ttm": 4.5,
                "current_assets": 99.0,
                "current_liabilities": 52.0,
                "shares_outstanding": 40_000_000.0,
            },
        },
    }

    bronze_rows: list[dict[str, object]] = []
    for security_id, payload in metric_payloads.items():
        for version_name, available_from in (("old", old_available), ("new", new_available)):
            filing_date = available_from.normalize()
            fiscal_period_end = filing_date - pd.Timedelta(days=90)
            for metric_name, metric_value in payload[version_name].items():
                bronze_rows.append(
                    {
                        "security_id": security_id,
                        "source_company_id": security_id.replace("SEC", "COMP"),
                        "form_type": "10-Q",
                        "filing_date": filing_date,
                        "acceptance_datetime": available_from,
                        "fiscal_period_end": fiscal_period_end,
                        "metric_name_raw": metric_name.upper(),
                        "metric_name_canonical": metric_name,
                        "metric_value": metric_value,
                        "metric_unit": "USD" if metric_name != "shares_outstanding" else "shares",
                        "statement_type": "fundamentals",
                        "available_from": available_from,
                        "is_restatement": False,
                        "data_version": "test_v1",
                    }
                )
    silver_fundamentals = build_silver_fundamentals_pit(pd.DataFrame(bronze_rows))

    return FeatureResearchBundle(
        calendar=calendar,
        dates=dates,
        target_date=dates[-1],
        silver_market=silver_market,
        silver_fundamentals=silver_fundamentals,
        security_master=security_master,
        universe_snapshot=universe_snapshot,
        benchmark_market=benchmark_market,
    )


def build_label_research_bundle() -> LabelResearchBundle:
    calendar = ExchangeCalendarAdapter("XNYS")
    dates = calendar.calendar.sessions_in_range("2024-01-02", "2024-02-01").tz_localize(None)[:8]
    securities = [
        ("SEC_A", "Technology", 0.8, [100, 101, 103, 105, 107, 110, 111, 114]),
        ("SEC_B", "Technology", 1.0, [102, 103, 104, 106, 108, 109, 111, 113]),
        ("SEC_C", "Financials", 1.2, [98, 99, 101, 102, 103, 105, 106, 108]),
        ("SEC_D", "Financials", 1.4, [95, 96, 97, 99, 101, 102, 104, 107]),
        ("SEC_E", "Health Care", 0.6, [105, 106, 108, 109, 111, 112, 114, 117]),
    ]
    market_rows: list[dict[str, object]] = []
    panel_rows: list[dict[str, object]] = []
    for security_id, sector, beta_estimate, opens in securities:
        opens_array = np.asarray(opens, dtype=float)
        closes_array = opens_array * 1.002
        for i, date in enumerate(dates):
            market_rows.append(
                {
                    "security_id": security_id,
                    "trade_date": date,
                    "open": float(opens_array[i]),
                    "high": float(opens_array[i] * 1.01),
                    "low": float(opens_array[i] * 0.99),
                    "close": float(closes_array[i]),
                    "adj_close": float(closes_array[i]),
                    "volume": 500_000 + i * 10_000,
                    "dollar_volume": float(closes_array[i] * (500_000 + i * 10_000)),
                    "is_price_valid": True,
                    "is_volume_valid": True,
                    "tradable_flag_prelim": True,
                    "data_quality_score": 0.99,
                    "data_version": "label_test_v1",
                }
            )
            panel_rows.append(
                {
                    "date": date,
                    "security_id": security_id,
                    "sector": sector,
                    "beta_estimate": beta_estimate,
                }
            )

    benchmark_opens = np.asarray([100, 101, 103, 104, 106, 108, 109, 111], dtype=float)
    benchmark_market = pd.DataFrame(
        {
            "trade_date": dates,
            "open": benchmark_opens,
            "high": benchmark_opens * 1.01,
            "low": benchmark_opens * 0.99,
            "close": benchmark_opens * 1.002,
        }
    )
    labels_config = LabelsConfig(
        primary_label="label_excess_5d_oo",
        secondary_labels=["label_excess_1d_oo", "label_resid_5d_oo", "label_raw_5d_oo"],
        execution_reference="open_t_plus_1",
        horizons_trading_days=[1, 5],
        families=["raw", "excess", "residual", "binary_quantile", "multiclass_quantile"],
        overlap_policy=LabelOverlapPolicy(allow_overlap=True, purge_days=5, embargo_days=5),
        benchmark="SPY_like_proxy_or_index_return",
        residualization_controls=["benchmark_return", "sector_dummies", "beta_estimate"],
    )
    return LabelResearchBundle(
        calendar=calendar,
        dates=dates,
        panel=pd.DataFrame(panel_rows),
        silver_market=build_silver_market(pd.DataFrame(market_rows)),
        benchmark_market=benchmark_market,
        labels_config=labels_config,
    )
