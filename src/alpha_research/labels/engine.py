from __future__ import annotations

from dataclasses import dataclass
import re

import numpy as np
import pandas as pd

from alpha_research.config.models import LabelsConfig
from alpha_research.time.calendar import ExchangeCalendarAdapter


def _parse_horizon(label_name: str) -> int:
    match = re.search(r"_(\d+)d_", label_name)
    if not match:
        raise ValueError(f"Could not parse horizon from label name: {label_name}")
    return int(match.group(1))


def _build_benchmark_labels(benchmark_market: pd.DataFrame, horizons: list[int]) -> pd.DataFrame:
    bench = benchmark_market.copy()
    bench["trade_date"] = pd.to_datetime(bench["trade_date"], errors="coerce").dt.normalize()
    bench = bench.sort_values("trade_date", kind="stable").reset_index(drop=True)
    for horizon in horizons:
        bench[f"label_raw_{horizon}d_oo"] = bench["open"].shift(-(horizon + 1)) / bench["open"].shift(-1) - 1.0
    return bench.rename(columns={"trade_date": "date"})


def _residualize_by_date(frame: pd.DataFrame, y_column: str, sector_column: str = "sector", beta_column: str = "beta_estimate") -> pd.Series:
    residuals = pd.Series(np.nan, index=frame.index, dtype="float64")
    for date, group in frame.groupby("date", sort=False):
        y = pd.to_numeric(group[y_column], errors="coerce")
        beta_source = group[beta_column] if beta_column in group.columns else pd.Series(0.0, index=group.index, dtype="float64")
        sector_source = group[sector_column] if sector_column in group.columns else pd.Series(pd.NA, index=group.index, dtype="string")
        benchmark_source = group["benchmark_return_current"] if "benchmark_return_current" in group.columns else pd.Series(0.0, index=group.index, dtype="float64")
        beta = pd.to_numeric(beta_source, errors="coerce").fillna(0.0)
        sectors = pd.get_dummies(sector_source, prefix="sector", dummy_na=True, dtype=float)
        benchmark = pd.to_numeric(benchmark_source, errors="coerce").fillna(0.0)
        X = pd.concat(
            [
                pd.Series(1.0, index=group.index, name="intercept"),
                benchmark.rename("benchmark"),
                beta.rename("beta_estimate"),
                sectors,
            ],
            axis=1,
        )
        valid = y.notna()
        if valid.sum() < 2:
            residuals.loc[group.index] = y
            continue
        X_valid = X.loc[valid].astype(float)
        y_valid = y.loc[valid].astype(float)
        coeffs, *_ = np.linalg.lstsq(X_valid.to_numpy(), y_valid.to_numpy(), rcond=None)
        fitted = X_valid.to_numpy() @ coeffs
        residuals.loc[y_valid.index] = y_valid.to_numpy() - fitted
    return residuals


@dataclass(frozen=True)
class LabelBuildResult:
    panel: pd.DataFrame
    overlap_report: dict[str, int | bool]
    sanity_report: pd.DataFrame


def build_label_panel(
    panel: pd.DataFrame,
    silver_market: pd.DataFrame,
    benchmark_market: pd.DataFrame,
    calendar: ExchangeCalendarAdapter,
    labels_config: LabelsConfig,
) -> LabelBuildResult:
    market = silver_market.copy()
    market["trade_date"] = pd.to_datetime(market["trade_date"], errors="coerce").dt.normalize()
    market = market.sort_values(["security_id", "trade_date"], kind="stable").reset_index(drop=True)
    output = panel.copy()
    output["date"] = pd.to_datetime(output["date"], errors="coerce").dt.normalize()

    horizons = sorted(set(labels_config.horizons_trading_days))
    for horizon in horizons:
        label_name = f"label_raw_{horizon}d_oo"
        market[label_name] = market.groupby("security_id", sort=False)["open"].transform(lambda values, h=horizon: values.shift(-(h + 1)) / values.shift(-1) - 1.0)

    benchmark = _build_benchmark_labels(benchmark_market, horizons)
    benchmark_cols = ["date"] + [f"label_raw_{h}d_oo" for h in horizons]
    output = output.merge(market[["security_id", "trade_date"] + [f"label_raw_{h}d_oo" for h in horizons]].rename(columns={"trade_date": "date"}), on=["security_id", "date"], how="left")
    output = output.merge(benchmark[benchmark_cols], on="date", how="left", suffixes=("", "__benchmark"))

    for horizon in horizons:
        output[f"label_excess_{horizon}d_oo"] = output[f"label_raw_{horizon}d_oo"] - output[f"label_raw_{horizon}d_oo__benchmark"]
        output["benchmark_return_current"] = output[f"label_raw_{horizon}d_oo__benchmark"]
        output[f"label_resid_{horizon}d_oo"] = _residualize_by_date(output, f"label_excess_{horizon}d_oo")

        quantiles = output.groupby("date", dropna=False)[f"label_excess_{horizon}d_oo"].transform(lambda values: values.rank(method="average", pct=True))
        output[f"label_binary_top_bottom_{horizon}d"] = pd.Series(pd.NA, index=output.index, dtype="Int64")
        output.loc[quantiles >= 0.9, f"label_binary_top_bottom_{horizon}d"] = 1
        output.loc[quantiles <= 0.1, f"label_binary_top_bottom_{horizon}d"] = 0

        def _multiclass(values: pd.Series) -> pd.Series:
            result = pd.Series(pd.NA, index=values.index, dtype="Int64")
            non_null = values.dropna()
            if len(non_null) < 5:
                return result
            buckets = pd.qcut(non_null.rank(method="first"), q=5, labels=False, duplicates="drop")
            result.loc[non_null.index] = pd.Series(buckets, index=non_null.index).astype("Int64")
            return result

        output[f"label_multiclass_quantile_{horizon}d"] = output.groupby("date", dropna=False)[f"label_excess_{horizon}d_oo"].transform(_multiclass)

    primary_horizon = _parse_horizon(labels_config.primary_label)
    overlap_report = {
        "allow_overlap": labels_config.overlap_policy.allow_overlap,
        "primary_horizon_days": primary_horizon,
        "purge_days": labels_config.overlap_policy.purge_days,
        "embargo_days": labels_config.overlap_policy.embargo_days,
        "required_minimum_purge_days": primary_horizon,
        "required_minimum_embargo_days": primary_horizon,
    }

    sanity_rows = []
    for horizon in horizons:
        for family in ("label_raw", "label_excess", "label_resid"):
            column = f"{family}_{horizon}d_oo"
            sanity_rows.append(
                {
                    "label_name": column,
                    "horizon_days": horizon,
                    "rows": int(len(output)),
                    "non_null": int(output[column].notna().sum()),
                    "mean": float(pd.to_numeric(output[column], errors="coerce").mean()),
                    "std": float(pd.to_numeric(output[column], errors="coerce").std(ddof=0)),
                }
            )
    sanity_report = pd.DataFrame(sanity_rows)
    return LabelBuildResult(panel=output, overlap_report=overlap_report, sanity_report=sanity_report)
