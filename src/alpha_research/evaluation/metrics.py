from __future__ import annotations

import re

import numpy as np
import pandas as pd


def compute_predictive_metrics(predictions: pd.DataFrame, labels: pd.DataFrame, *, label_column: str) -> pd.DataFrame:
    merged = predictions.merge(labels[["date", "security_id", label_column]], on=["date", "security_id"], how="left")
    rows: list[dict[str, float | pd.Timestamp]] = []
    for date, group in merged.groupby("date", sort=False):
        subset = group[["raw_prediction", label_column]].dropna()
        if len(subset) < 2:
            ic = np.nan
            rank_ic = np.nan
        else:
            ic = float(subset["raw_prediction"].corr(subset[label_column]))
            rank_ic = float(subset["raw_prediction"].rank(method="average").corr(subset[label_column].rank(method="average")))
        rows.append({"date": pd.Timestamp(date), "ic": ic, "rank_ic": rank_ic})
    metrics = pd.DataFrame(rows)
    summary = pd.DataFrame(
        [
            {
                "metric": "ic_mean",
                "value": float(pd.to_numeric(metrics["ic"], errors="coerce").mean()),
            },
            {
                "metric": "rank_ic_mean",
                "value": float(pd.to_numeric(metrics["rank_ic"], errors="coerce").mean()),
            },
        ]
    )
    return pd.concat([metrics, summary], axis=0, ignore_index=True, sort=False)


def compute_portfolio_metrics(daily_state: pd.DataFrame, *, initial_aum: float | None = None) -> pd.DataFrame:
    state = daily_state.copy().sort_values("date", kind="stable").reset_index(drop=True)
    if state.empty:
        return pd.DataFrame([{"metric": "net_sharpe", "value": np.nan}, {"metric": "max_drawdown", "value": np.nan}])

    previous_aum = pd.Series(state["aum"].shift(1), index=state.index)
    previous_aum.iloc[0] = float(initial_aum if initial_aum is not None else state.loc[0, "aum"] - state.loc[0, "net_pnl"])
    net_returns = pd.to_numeric(state["net_pnl"], errors="coerce") / previous_aum.replace(0.0, np.nan)
    net_returns = net_returns.fillna(0.0)
    sharpe = np.nan
    if len(net_returns) >= 2 and net_returns.std(ddof=0) != 0:
        sharpe = float(net_returns.mean() / net_returns.std(ddof=0) * np.sqrt(252.0))
    equity_curve = (1.0 + net_returns).cumprod()
    running_peak = equity_curve.cummax()
    drawdown = equity_curve / running_peak - 1.0
    max_drawdown = float(drawdown.min()) if not drawdown.empty else np.nan
    return pd.DataFrame([{"metric": "net_sharpe", "value": sharpe}, {"metric": "max_drawdown", "value": max_drawdown}])


def compute_regime_breakdown(frame: pd.DataFrame, *, prediction_column: str, label_column: str, regime_column: str) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for regime, group in frame.groupby(regime_column, dropna=False, sort=False):
        subset = group[[prediction_column, label_column]].dropna()
        metric = float(subset[prediction_column].corr(subset[label_column])) if len(subset) >= 2 else np.nan
        rows.append({"regime": regime, "row_count": int(len(group)), "ic": metric})
    return pd.DataFrame(rows)


def _parse_horizon(label_name: str) -> int:
    match = re.search(r"_(\d+)d_", label_name)
    if not match:
        raise ValueError(f"Unable to parse horizon from label column: {label_name}")
    return int(match.group(1))


def build_decay_response_curve(
    frame: pd.DataFrame,
    *,
    prediction_column: str,
    label_columns: list[str],
    bucket_count: int = 5,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    scored = frame.copy()
    scored["prediction_bucket"] = scored.groupby("date", dropna=False)[prediction_column].transform(
        lambda values: pd.qcut(values.rank(method="first"), q=bucket_count, labels=False, duplicates="drop") if values.notna().sum() >= bucket_count else pd.Series(pd.NA, index=values.index)
    )
    for label_column in label_columns:
        horizon = _parse_horizon(label_column)
        for bucket, group in scored.groupby("prediction_bucket", dropna=False):
            if pd.isna(bucket):
                continue
            rows.append(
                {
                    "horizon_days": horizon,
                    "prediction_bucket": int(bucket),
                    "mean_response": float(pd.to_numeric(group[label_column], errors="coerce").mean()),
                }
            )
    if not rows:
        return pd.DataFrame(columns=["horizon_days", "prediction_bucket", "mean_response"])
    return pd.DataFrame(rows).sort_values(["horizon_days", "prediction_bucket"], kind="stable").reset_index(drop=True)
