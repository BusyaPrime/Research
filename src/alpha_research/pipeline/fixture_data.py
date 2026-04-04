from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from alpha_research.pit.builders import build_silver_fundamentals_pit, build_silver_market
from alpha_research.reference.security_master import build_security_master
from alpha_research.time.calendar import ExchangeCalendarAdapter


METRIC_NAMES = [
    "book_equity",
    "net_income_ttm",
    "revenue_ttm",
    "operating_cashflow_ttm",
    "gross_profit_ttm",
    "operating_income_ttm",
    "total_assets",
    "total_debt",
    "ebit_ttm",
    "interest_expense_ttm",
    "current_assets",
    "current_liabilities",
    "shares_outstanding",
]

SECTOR_SEQUENCE = [
    ("Technology", "Software"),
    ("Technology", "Hardware"),
    ("Financials", "Banks"),
    ("Financials", "Insurance"),
    ("Health Care", "Biotech"),
    ("Industrials", "Machinery"),
    ("Consumer Discretionary", "Retail"),
    ("Energy", "Exploration"),
]


@dataclass(frozen=True)
class SyntheticResearchBundle:
    calendar: ExchangeCalendarAdapter
    security_master: pd.DataFrame
    silver_market: pd.DataFrame
    silver_fundamentals: pd.DataFrame
    benchmark_market: pd.DataFrame
    notes: list[str]


def _build_security_master_frame(n_securities: int) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for idx in range(n_securities):
        sector, industry = SECTOR_SEQUENCE[idx % len(SECTOR_SEQUENCE)]
        rows.append(
            {
                "security_id": f"SEC_{idx:03d}",
                "symbol": f"S{idx:03d}",
                "security_type": "common_stock",
                "exchange": "NASDAQ" if idx % 3 != 0 else "NYSE",
                "listing_date": "2013-01-02",
                "delisting_date": None,
                "sector": sector,
                "industry": industry,
                "country": "US",
                "currency": "USD",
                "is_common_stock": True,
            }
        )
    return build_security_master(pd.DataFrame(rows))


def _build_benchmark_market(dates: pd.DatetimeIndex) -> tuple[pd.DataFrame, np.ndarray]:
    day_index = np.arange(len(dates), dtype="float64")
    returns = (
        0.00015
        + 0.0007 * np.sin(day_index / 31.0)
        + 0.0005 * np.cos(day_index / 73.0)
    )
    close = 100.0 * np.exp(np.cumsum(returns))
    overnight = 0.0001 * np.sin(day_index / 19.0)
    open_px = close / np.exp(returns * 0.45 + overnight)
    high = np.maximum(open_px, close) * (1.0015 + 0.0003 * np.abs(np.sin(day_index / 7.0)))
    low = np.minimum(open_px, close) * (0.9985 - 0.0002 * np.abs(np.cos(day_index / 9.0)))
    benchmark = pd.DataFrame(
        {
            "trade_date": dates,
            "open": open_px,
            "high": high,
            "low": low,
            "close": close,
        }
    )
    return benchmark, returns


def _build_market_frame(
    dates: pd.DatetimeIndex,
    security_master: pd.DataFrame,
    benchmark_returns: np.ndarray,
    seed: int,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    day_index = np.arange(len(dates), dtype="float64")
    rows: list[pd.DataFrame] = []
    for idx, security in enumerate(security_master.itertuples(index=False)):
        base_price = 12.0 + (idx % 12) * 3.5 + (idx // 12) * 1.25
        beta = 0.55 + 0.05 * (idx % 8)
        style_wave = 0.0012 * np.sin((day_index + idx) / (11.0 + (idx % 5)))
        slow_wave = 0.0008 * np.cos((day_index + idx) / (37.0 + (idx % 7)))
        noise = rng.normal(0.0, 0.0018 + 0.0002 * (idx % 4), size=len(dates))
        returns = 0.00008 + beta * benchmark_returns + style_wave + slow_wave + noise
        close = base_price * np.exp(np.cumsum(returns))
        overnight = 0.0003 * np.sin((day_index + idx) / 17.0)
        open_px = close / np.exp(returns * 0.55 + overnight)
        high = np.maximum(open_px, close) * (1.002 + 0.0004 * np.abs(np.cos((day_index + idx) / 5.0)))
        low = np.minimum(open_px, close) * (0.998 - 0.0003 * np.abs(np.sin((day_index + idx) / 6.0)))
        shares_turnover = 0.003 + 0.0008 * (idx % 10)
        shares_outstanding = 25_000_000 + idx * 1_250_000
        volume = shares_outstanding * (shares_turnover + 0.001 * np.sin((day_index + idx) / 23.0))
        volume = np.maximum(volume, shares_outstanding * 0.0008).astype("int64")
        rows.append(
            pd.DataFrame(
                {
                    "security_id": security.security_id,
                    "trade_date": dates,
                    "open": open_px,
                    "high": high,
                    "low": low,
                    "close": close,
                    "adj_close": close,
                    "volume": volume,
                    "dollar_volume": close * volume,
                    "is_price_valid": True,
                    "is_volume_valid": True,
                    "tradable_flag_prelim": True,
                    "data_quality_score": 0.985 - (idx % 5) * 0.01,
                    "data_version": "synthetic_fixture_v1",
                }
            )
        )
    return build_silver_market(pd.concat(rows, ignore_index=True))


def _fundamental_value_map(security_idx: int, quarter_idx: int) -> dict[str, float]:
    base_equity = 250_000_000 + security_idx * 18_000_000
    revenue = 500_000_000 + security_idx * 26_000_000
    growth = 1.0 + 0.02 * quarter_idx
    cyclicality = 1.0 + 0.03 * np.sin((quarter_idx + security_idx) / 3.0)
    total_assets = base_equity * 2.6 * growth
    return {
        "book_equity": base_equity * growth * cyclicality,
        "net_income_ttm": revenue * 0.08 * growth * cyclicality,
        "revenue_ttm": revenue * growth,
        "operating_cashflow_ttm": revenue * 0.1 * growth * cyclicality,
        "gross_profit_ttm": revenue * 0.36 * growth,
        "operating_income_ttm": revenue * 0.14 * growth,
        "total_assets": total_assets,
        "total_debt": total_assets * 0.28,
        "ebit_ttm": revenue * 0.13 * growth,
        "interest_expense_ttm": revenue * 0.012 * growth,
        "current_assets": total_assets * 0.34,
        "current_liabilities": total_assets * 0.15,
        "shares_outstanding": 25_000_000 + security_idx * 1_250_000,
    }


def _build_fundamentals_frame(dates: pd.DatetimeIndex, security_master: pd.DataFrame) -> pd.DataFrame:
    available_dates = dates[20::63]
    rows: list[dict[str, object]] = []
    for idx, security in enumerate(security_master.itertuples(index=False)):
        for quarter_idx, available_date in enumerate(available_dates):
            available_ts = (
                pd.Timestamp(available_date)
                .tz_localize("America/New_York")
                .replace(hour=20, minute=0, second=0)
                .tz_convert("UTC")
            )
            filing_date = pd.Timestamp(available_date).normalize()
            fiscal_period_end = filing_date - pd.Timedelta(days=90)
            values = _fundamental_value_map(idx, quarter_idx)
            for metric_name in METRIC_NAMES:
                rows.append(
                    {
                        "security_id": security.security_id,
                        "source_company_id": f"COMP_{idx:03d}",
                        "form_type": "10-Q",
                        "filing_date": filing_date,
                        "acceptance_datetime": available_ts,
                        "fiscal_period_end": fiscal_period_end,
                        "metric_name_raw": metric_name.upper(),
                        "metric_name_canonical": metric_name,
                        "metric_value": values[metric_name],
                        "metric_unit": "shares" if metric_name == "shares_outstanding" else "USD",
                        "statement_type": "fundamentals",
                        "available_from": available_ts,
                        "is_restatement": False,
                        "data_version": "synthetic_fixture_v1",
                    }
                )
    return build_silver_fundamentals_pit(pd.DataFrame(rows))


def build_synthetic_research_bundle(
    *,
    start_date: str = "2014-01-02",
    end_date: str = "2025-12-31",
    n_securities: int = 36,
    seed: int = 42,
) -> SyntheticResearchBundle:
    calendar = ExchangeCalendarAdapter("XNYS")
    dates = calendar.calendar.sessions_in_range(start_date, end_date).tz_localize(None)
    security_master = _build_security_master_frame(n_securities)
    benchmark_market, benchmark_returns = _build_benchmark_market(dates)
    silver_market = _build_market_frame(dates, security_master, benchmark_returns, seed)
    silver_fundamentals = _build_fundamentals_frame(dates, security_master)
    notes = [
        "TEMPORARY SIMPLIFICATION: operational pipeline uses deterministic synthetic data until real vendor adapters are configured.",
        "Synthetic bundle preserves time semantics, PIT available_from rules, OOF discipline, and artifact reproducibility contracts.",
    ]
    return SyntheticResearchBundle(
        calendar=calendar,
        security_master=security_master,
        silver_market=silver_market,
        silver_fundamentals=silver_fundamentals,
        benchmark_market=benchmark_market,
        notes=notes,
    )
