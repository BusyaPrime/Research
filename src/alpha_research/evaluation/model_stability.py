from __future__ import annotations

import pandas as pd


def _safe_rank_corr(left: pd.Series, right: pd.Series) -> float:
    ranked = pd.concat(
        [
            pd.to_numeric(left, errors="coerce").rank(method="average").rename("left"),
            pd.to_numeric(right, errors="coerce").rank(method="average").rename("right"),
        ],
        axis=1,
    ).dropna()
    if len(ranked) < 2:
        return float("nan")
    if ranked["left"].std(ddof=0) <= 1e-12 or ranked["right"].std(ddof=0) <= 1e-12:
        return float("nan")
    return float(ranked["left"].corr(ranked["right"]))


def compute_model_stability_report(
    predictions: pd.DataFrame,
    labels: pd.DataFrame,
    tuning_diagnostics: pd.DataFrame,
    *,
    label_column: str,
) -> pd.DataFrame:
    merged = predictions.merge(labels[["date", "security_id", label_column]], on=["date", "security_id"], how="left")
    fold_rows: list[dict[str, object]] = []
    for (model_name, fold_id), group in merged.groupby(["model_name", "fold_id"], sort=False):
        subset = group[["raw_prediction", label_column]].dropna()
        rank_ic = _safe_rank_corr(subset["raw_prediction"], subset[label_column]) if len(subset) >= 2 else float("nan")
        fold_rows.append(
            {
                "model_name": model_name,
                "fold_id": fold_id,
                "rank_ic": rank_ic,
                "row_count": int(len(group)),
                "prediction_std": float(pd.to_numeric(group["raw_prediction"], errors="coerce").std(ddof=0)),
            }
        )
    fold_frame = pd.DataFrame(fold_rows)
    if fold_frame.empty:
        return pd.DataFrame(columns=["model_name", "fold_count", "rank_ic_mean", "rank_ic_std", "prediction_std_mean", "tuning_candidate_count", "best_minus_median_validation"])

    tuning_summary = compute_hyperparameter_sensitivity(tuning_diagnostics)
    if not tuning_summary.empty:
        tuning_summary = tuning_summary.set_index("model_name")

    rows: list[dict[str, object]] = []
    for model_name, group in fold_frame.groupby("model_name", sort=False):
        row = {
            "model_name": model_name,
            "fold_count": int(group["fold_id"].nunique()),
            "rank_ic_mean": float(pd.to_numeric(group["rank_ic"], errors="coerce").mean()),
            "rank_ic_std": float(pd.to_numeric(group["rank_ic"], errors="coerce").std(ddof=0)),
            "prediction_std_mean": float(pd.to_numeric(group["prediction_std"], errors="coerce").mean()),
            "mean_row_count_per_fold": float(pd.to_numeric(group["row_count"], errors="coerce").mean()),
            "tuning_candidate_count": float("nan"),
            "best_minus_median_validation": float("nan"),
            "top2_gap_validation": float("nan"),
        }
        if not tuning_summary.empty and model_name in tuning_summary.index:
            tuning_row = tuning_summary.loc[model_name]
            row["tuning_candidate_count"] = tuning_row["candidate_count"]
            row["best_minus_median_validation"] = tuning_row["best_minus_median_validation"]
            row["top2_gap_validation"] = tuning_row["top2_gap_validation"]
        rows.append(row)
    return pd.DataFrame(rows).sort_values("model_name", kind="stable").reset_index(drop=True)


def compute_hyperparameter_sensitivity(tuning_diagnostics: pd.DataFrame) -> pd.DataFrame:
    if tuning_diagnostics.empty:
        return pd.DataFrame(columns=["model_name", "candidate_count", "best_validation", "median_validation", "best_minus_median_validation", "top2_gap_validation"])
    rows: list[dict[str, object]] = []
    metric_column = "validation_rank_ic_mean"
    frame = tuning_diagnostics.copy()
    frame[metric_column] = pd.to_numeric(frame[metric_column], errors="coerce")
    for model_name, group in frame.groupby("model_name", sort=False):
        ranked = group.sort_values(metric_column, ascending=False, kind="stable").reset_index(drop=True)
        values = pd.to_numeric(ranked[metric_column], errors="coerce").dropna()
        if values.empty:
            best = float("nan")
            median = float("nan")
            best_minus_median = float("nan")
            top2_gap = float("nan")
        else:
            best = float(values.iloc[0])
            median = float(values.median())
            best_minus_median = best - median
            top2_gap = best - float(values.iloc[1]) if len(values) > 1 else float("nan")
        rows.append(
            {
                "model_name": model_name,
                "candidate_count": int(len(group)),
                "best_validation": best,
                "median_validation": median,
                "best_minus_median_validation": best_minus_median,
                "top2_gap_validation": top2_gap,
            }
        )
    return pd.DataFrame(rows).sort_values("model_name", kind="stable").reset_index(drop=True)
