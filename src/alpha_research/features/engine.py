from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from alpha_research.features.registry import feature_names_by_family, load_feature_registry
from alpha_research.pit.asof_join import pit_join_fundamentals
from alpha_research.time.calendar import ExchangeCalendarAdapter


def _merge_market_and_reference(
    silver_market: pd.DataFrame,
    security_master: pd.DataFrame,
    universe_snapshot: pd.DataFrame,
    calendar: ExchangeCalendarAdapter,
) -> pd.DataFrame:
    market = silver_market.copy()
    market["trade_date"] = pd.to_datetime(market["trade_date"], errors="coerce").dt.normalize()
    market = market.rename(columns={"trade_date": "date"})

    ref = security_master[["security_id", "symbol", "sector", "industry"]].copy()
    universe = universe_snapshot.copy()
    universe["date"] = pd.to_datetime(universe["date"], errors="coerce").dt.normalize()

    panel = market.merge(ref, on="security_id", how="left").merge(universe, on=["date", "security_id"], how="left")
    panel["is_in_universe"] = panel["is_in_universe"].fillna(False)
    panel["as_of_timestamp"] = panel["date"].map(calendar.decision_timestamp)
    return panel.sort_values(["security_id", "date"], kind="stable").reset_index(drop=True)


def _build_benchmark_frame(benchmark_market: pd.DataFrame) -> pd.DataFrame:
    bench = benchmark_market.copy()
    bench["trade_date"] = pd.to_datetime(bench["trade_date"], errors="coerce").dt.normalize()
    bench = bench.sort_values("trade_date", kind="stable").reset_index(drop=True)
    bench["bench_ret_1"] = bench["close"] / bench["close"].shift(1) - 1.0
    for window in (5, 21, 63):
        bench[f"bench_ret_{window}"] = bench["close"] / bench["close"].shift(window) - 1.0
    return bench.rename(columns={"trade_date": "date", "close": "benchmark_close", "open": "benchmark_open"})


def _rolling_std(values: pd.Series, window: int) -> pd.Series:
    return values.rolling(window=window, min_periods=window).std(ddof=0)


def _percentile_rank(values: pd.Series) -> pd.Series:
    if len(values.dropna()) == 0:
        return pd.Series(np.nan, index=values.index)
    return values.rank(method="average", pct=True)


def _percentile_rank_with_mask(values: pd.Series, mask: pd.Series) -> pd.Series:
    output = pd.Series(np.nan, index=values.index, dtype="float64")
    valid = mask.fillna(False) & values.notna()
    if valid.sum() == 0:
        return output
    output.loc[valid] = values.loc[valid].rank(method="average", pct=True)
    return output


def _rolling_beta(stock_returns: pd.Series, benchmark_returns: pd.Series, window: int = 63, min_periods: int = 21) -> pd.Series:
    stock = pd.to_numeric(stock_returns, errors="coerce")
    bench = pd.to_numeric(benchmark_returns, errors="coerce")
    mean_stock = stock.rolling(window=window, min_periods=min_periods).mean()
    mean_bench = bench.rolling(window=window, min_periods=min_periods).mean()
    mean_cross = (stock * bench).rolling(window=window, min_periods=min_periods).mean()
    mean_bench_sq = (bench * bench).rolling(window=window, min_periods=min_periods).mean()
    covariance = mean_cross - mean_stock * mean_bench
    variance = mean_bench_sq - mean_bench.pow(2)
    return covariance / variance.where(variance.abs() > 1e-12)


def _join_fundamental_inputs(panel: pd.DataFrame, silver_fundamentals: pd.DataFrame) -> pd.DataFrame:
    metric_inputs = [
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
    joined = pit_join_fundamentals(panel, silver_fundamentals, metric_inputs, as_of_column="as_of_timestamp").copy()
    joined["_row_id"] = range(len(joined))

    latest_any = (
        silver_fundamentals[["security_id", "available_from"]]
        .dropna()
        .sort_values(["security_id", "available_from"], kind="stable")
        .drop_duplicates()
    )
    latest_any["available_from"] = pd.to_datetime(latest_any["available_from"], errors="coerce", utc=True)

    result_frames: list[pd.DataFrame] = []
    for security_id, left_group in joined[["_row_id", "security_id", "as_of_timestamp"]].groupby("security_id", sort=False):
        left_sorted = left_group.sort_values("as_of_timestamp", kind="stable")
        right_sorted = latest_any.loc[latest_any["security_id"] == security_id].sort_values("available_from", kind="stable")
        if right_sorted.empty:
            temp = left_sorted.copy()
            temp["latest_filing_available_from"] = pd.NaT
        else:
            temp = pd.merge_asof(
                left_sorted,
                right_sorted,
                left_on="as_of_timestamp",
                right_on="available_from",
                direction="backward",
                allow_exact_matches=True,
            ).rename(columns={"available_from": "latest_filing_available_from"})
        result_frames.append(temp[["_row_id", "latest_filing_available_from"]])
    latest_frame = pd.concat(result_frames, ignore_index=True).sort_values("_row_id", kind="stable")
    joined["latest_filing_available_from"] = latest_frame["latest_filing_available_from"].reset_index(drop=True)
    return joined.drop(columns="_row_id")


@dataclass(frozen=True)
class FeatureBuildResult:
    panel: pd.DataFrame
    feature_columns: list[str]
    feature_coverage: pd.DataFrame


def build_feature_panel(
    silver_market: pd.DataFrame,
    silver_fundamentals: pd.DataFrame,
    security_master: pd.DataFrame,
    universe_snapshot: pd.DataFrame,
    benchmark_market: pd.DataFrame,
    calendar: ExchangeCalendarAdapter,
    *,
    interaction_cap: int = 25,
    root: str | None = None,
) -> FeatureBuildResult:
    registry = load_feature_registry(root)
    panel = _merge_market_and_reference(silver_market, security_master, universe_snapshot, calendar)
    panel = _join_fundamental_inputs(panel, silver_fundamentals)
    bench = _build_benchmark_frame(benchmark_market)
    panel = panel.merge(
        bench[["date", "benchmark_close", "benchmark_open", "bench_ret_1", "bench_ret_5", "bench_ret_21", "bench_ret_63"]],
        on="date",
        how="left",
    )
    panel = panel.sort_values(["security_id", "date"], kind="stable").reset_index(drop=True)

    grouped = panel.groupby("security_id", sort=False)
    close = grouped["close"]
    high = grouped["high"]
    low = grouped["low"]
    open_px = grouped["open"]
    volume = grouped["volume"]
    dollar_volume = grouped["dollar_volume"]

    for window in (1, 2, 3, 5, 10, 21, 63, 126, 252):
        panel[f"ret_{window}"] = panel["close"] / close.shift(window) - 1.0
    for window in (5, 10, 21, 63, 126, 252):
        panel[f"mom_{window}_ex1"] = close.shift(1) / close.shift(window + 1) - 1.0
    for window in (1, 2, 5):
        panel[f"rev_{window}"] = -panel[f"ret_{window}"]

    panel["ex_bench_5"] = panel["ret_5"] - panel["bench_ret_5"]
    panel["ex_bench_21"] = panel["ret_21"] - panel["bench_ret_21"]
    panel["ex_bench_63"] = panel["ret_63"] - panel["bench_ret_63"]

    panel["ex_sector_5"] = panel["ret_5"] - panel.groupby(["date", "sector"], dropna=False)["ret_5"].transform("median")
    panel["ex_sector_21"] = panel["ret_21"] - panel.groupby(["date", "sector"], dropna=False)["ret_21"].transform("median")
    panel["ex_sector_63"] = panel["ret_63"] - panel.groupby(["date", "sector"], dropna=False)["ret_63"].transform("median")
    panel["beta_estimate"] = grouped.apply(lambda frame: _rolling_beta(frame["ret_1"], frame["bench_ret_1"])).reset_index(level=0, drop=True)

    log_returns = np.log(panel["close"] / close.shift(1))
    for window in (5, 10, 21, 63):
        panel[f"vol_{window}"] = grouped.apply(lambda frame: np.log(frame["close"] / frame["close"].shift(1)).rolling(window=window, min_periods=window).std(ddof=0)).reset_index(level=0, drop=True)
    for window in (21, 63):
        panel[f"down_vol_{window}"] = grouped.apply(
            lambda frame: np.log(frame["close"] / frame["close"].shift(1)).clip(upper=0).rolling(window=window, min_periods=window).std(ddof=0)
        ).reset_index(level=0, drop=True)
        panel[f"up_vol_{window}"] = grouped.apply(
            lambda frame: np.log(frame["close"] / frame["close"].shift(1)).clip(lower=0).rolling(window=window, min_periods=window).std(ddof=0)
        ).reset_index(level=0, drop=True)

    panel["hl_range_21"] = grouped.apply(lambda frame: ((frame["high"] - frame["low"]) / frame["close"]).rolling(21, min_periods=21).mean()).reset_index(level=0, drop=True)
    panel["parkinson_21"] = grouped.apply(
        lambda frame: np.sqrt(((np.log(frame["high"] / frame["low"]) ** 2).rolling(21, min_periods=21).sum()) / (4 * 21 * np.log(2)))
    ).reset_index(level=0, drop=True)
    panel["gk_21"] = grouped.apply(
        lambda frame: np.sqrt(
            (
                (
                    0.5 * (np.log(frame["high"] / frame["low"]) ** 2)
                    - (2 * np.log(2) - 1) * (np.log(frame["close"] / frame["open"]) ** 2)
                ).rolling(21, min_periods=21).sum()
            ) / 21
        )
    ).reset_index(level=0, drop=True)
    panel["atr_14"] = grouped.apply(
        lambda frame: pd.concat(
            [
                frame["high"] - frame["low"],
                (frame["high"] - frame["close"].shift(1)).abs(),
                (frame["low"] - frame["close"].shift(1)).abs(),
            ],
            axis=1,
        ).max(axis=1).rolling(14, min_periods=14).mean()
    ).reset_index(level=0, drop=True)

    panel["log_volume_1"] = np.log1p(panel["volume"].clip(lower=0))
    panel["log_dollar_volume_1"] = np.log1p((panel["close"] * panel["volume"]).clip(lower=0))
    for window in (5, 20, 60):
        panel[f"adv{window}"] = dollar_volume.transform(lambda values: values.rolling(window=window, min_periods=window).mean())
    panel["volume_surprise_5"] = panel["volume"] / grouped["volume"].transform(lambda values: values.shift(1).rolling(window=5, min_periods=5).mean())
    panel["volume_surprise_20"] = panel["volume"] / grouped["volume"].transform(lambda values: values.shift(1).rolling(window=20, min_periods=20).mean())
    amihud_raw = np.where((panel["close"] * panel["volume"]) > 0, panel["ret_1"].abs() / (panel["close"] * panel["volume"]), np.nan)
    panel["amihud_21"] = grouped.apply(lambda frame: pd.Series(amihud_raw[frame.index], index=frame.index).rolling(window=21, min_periods=21).mean()).reset_index(level=0, drop=True)
    panel["zero_volume_rate_21"] = grouped["volume"].transform(lambda values: (values == 0).astype(float).rolling(window=21, min_periods=21).mean())

    panel["market_cap"] = panel["close"] * panel["shares_outstanding"]
    panel["turnover_proxy_21"] = (panel["volume"] / panel["shares_outstanding"]).groupby(panel["security_id"], sort=False).transform(lambda values: values.rolling(window=21, min_periods=21).mean())

    for window in (20, 50, 100, 200):
        moving_average = close.transform(lambda values, w=window: values.rolling(window=w, min_periods=w).mean())
        panel[f"px_to_ma{window}"] = panel["close"] / moving_average - 1.0
    ma20 = close.transform(lambda values: values.rolling(window=20, min_periods=20).mean())
    ma50 = close.transform(lambda values: values.rolling(window=50, min_periods=50).mean())
    ma200 = close.transform(lambda values: values.rolling(window=200, min_periods=200).mean())
    panel["ma20_to_ma50"] = ma20 / ma50 - 1.0
    panel["ma50_to_ma200"] = ma50 / ma200 - 1.0
    panel["dist_to_20d_high"] = panel["close"] / high.transform(lambda values: values.rolling(window=20, min_periods=20).max()) - 1.0
    panel["dist_to_20d_low"] = panel["close"] / low.transform(lambda values: values.rolling(window=20, min_periods=20).min()) - 1.0
    panel["dist_to_52w_high"] = panel["close"] / high.transform(lambda values: values.rolling(window=252, min_periods=252).max()) - 1.0
    panel["dist_to_52w_low"] = panel["close"] / low.transform(lambda values: values.rolling(window=252, min_periods=252).min()) - 1.0
    panel["breakout_20d_up"] = (panel["close"] > high.transform(lambda values: values.shift(1).rolling(window=20, min_periods=20).max())).astype("Int64")
    panel["breakout_20d_down"] = (panel["close"] < low.transform(lambda values: values.shift(1).rolling(window=20, min_periods=20).min())).astype("Int64")

    for feature in ("ret_5", "ret_21", "ret_63", "vol_21", "adv20"):
        rank_name = {
            "ret_5": "cs_rank_ret_5",
            "ret_21": "cs_rank_ret_21",
            "ret_63": "cs_rank_ret_63",
            "vol_21": "cs_rank_vol_21",
            "adv20": "cs_rank_adv20",
        }[feature]
        panel[rank_name] = panel.groupby("date", dropna=False, group_keys=False).apply(
            lambda frame, feature_name=feature: _percentile_rank_with_mask(frame[feature_name], frame["is_in_universe"])
        )
    panel["liquidity_rank_20"] = panel.groupby("date", dropna=False, group_keys=False).apply(
        lambda frame: _percentile_rank_with_mask(frame["adv20"], frame["is_in_universe"])
    )
    panel["sector_rank_ret_21"] = panel.groupby(["date", "sector"], dropna=False, group_keys=False).apply(
        lambda frame: _percentile_rank_with_mask(frame["ret_21"], frame["is_in_universe"])
    )
    panel["sector_rank_vol_21"] = panel.groupby(["date", "sector"], dropna=False, group_keys=False).apply(
        lambda frame: _percentile_rank_with_mask(frame["vol_21"], frame["is_in_universe"])
    )
    panel["sector_rank_adv20"] = panel.groupby(["date", "sector"], dropna=False, group_keys=False).apply(
        lambda frame: _percentile_rank_with_mask(frame["adv20"], frame["is_in_universe"])
    )

    book_prev = grouped["book_equity"].shift(252)
    assets_prev = grouped["total_assets"].shift(252)
    revenue_prev = grouped["revenue_ttm"].shift(252)
    income_prev = grouped["net_income_ttm"].shift(252)
    panel["average_book_equity"] = np.where(book_prev.notna(), (panel["book_equity"] + book_prev) / 2.0, panel["book_equity"])
    panel["average_total_assets"] = np.where(assets_prev.notna(), (panel["total_assets"] + assets_prev) / 2.0, panel["total_assets"])

    panel["book_to_price"] = panel["book_equity"] / panel["market_cap"]
    panel["earnings_yield"] = panel["net_income_ttm"] / panel["market_cap"]
    panel["sales_yield"] = panel["revenue_ttm"] / panel["market_cap"]
    panel["cashflow_yield"] = panel["operating_cashflow_ttm"] / panel["market_cap"]
    panel["roe"] = panel["net_income_ttm"] / panel["average_book_equity"]
    panel["roa"] = panel["net_income_ttm"] / panel["average_total_assets"]
    panel["gross_profitability"] = panel["gross_profit_ttm"] / panel["total_assets"]
    panel["operating_margin"] = panel["operating_income_ttm"] / panel["revenue_ttm"]
    panel["accruals"] = (panel["net_income_ttm"] - panel["operating_cashflow_ttm"]) / panel["total_assets"]
    panel["sales_growth_yoy"] = panel["revenue_ttm"] / revenue_prev - 1.0
    panel["earnings_growth_yoy"] = panel["net_income_ttm"] / income_prev - 1.0
    panel["asset_growth_yoy"] = panel["total_assets"] / assets_prev - 1.0
    panel["debt_to_equity"] = panel["total_debt"] / panel["book_equity"]
    panel["interest_coverage"] = panel["ebit_ttm"] / panel["interest_expense_ttm"]
    panel["current_ratio"] = panel["current_assets"] / panel["current_liabilities"]

    panel["days_since_last_filing"] = panel.apply(
        lambda row: calendar.trading_day_distance(pd.Timestamp(row["latest_filing_available_from"]).normalize(), row["date"])
        if pd.notna(row["latest_filing_available_from"])
        else pd.NA,
        axis=1,
    )
    panel["days_since_last_filing"] = pd.to_numeric(panel["days_since_last_filing"], errors="coerce").astype("Int32")
    panel["fundamental_staleness_90"] = (panel["days_since_last_filing"] > 90).astype("Int64")
    panel["fundamental_staleness_180"] = (panel["days_since_last_filing"] > 180).astype("Int64")
    panel["missing_book_to_price_flag"] = panel["book_to_price"].isna().astype("Int64")
    panel["missing_quality_flag"] = panel[["roe", "roa", "gross_profitability"]].isna().any(axis=1).astype("Int64")

    interaction_names = feature_names_by_family("interactions", root=root)
    allowed_interactions = set(interaction_names[: max(interaction_cap, 0)])
    interaction_values = {
        "mom_21_ex1_x_liquidity_rank_20": panel["mom_21_ex1"] * panel["liquidity_rank_20"],
        "rev_1_x_vol_21": panel["rev_1"] * panel["vol_21"],
        "book_to_price_x_roe": panel["book_to_price"] * panel["roe"],
        "px_to_ma50_x_vol_21": panel["px_to_ma50"] * panel["vol_21"],
        "earnings_yield_x_liquidity_rank_20": panel["earnings_yield"] * panel["liquidity_rank_20"],
    }
    for feature_name, values in interaction_values.items():
        if feature_name in allowed_interactions:
            panel[feature_name] = values

    feature_columns = [name for name in registry if name in panel.columns]
    panel = panel.sort_values(["date", "security_id"], kind="stable").reset_index(drop=True)
    panel["feature_coverage_ratio"] = panel[feature_columns].notna().mean(axis=1)
    coverage = panel[["date", "security_id", "feature_coverage_ratio"]].copy()
    return FeatureBuildResult(panel=panel, feature_columns=feature_columns, feature_coverage=coverage)
