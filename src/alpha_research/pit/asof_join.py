from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


def asof_lookup(
    silver_fundamentals: pd.DataFrame,
    security_id: str,
    metric_name: str,
    as_of_timestamp: str | pd.Timestamp,
) -> dict[str, object] | None:
    """Return the latest fact available at or before the as-of timestamp."""

    as_of_ts = pd.Timestamp(as_of_timestamp)
    if as_of_ts.tzinfo is None:
        as_of_ts = as_of_ts.tz_localize("UTC")
    else:
        as_of_ts = as_of_ts.tz_convert("UTC")

    facts = silver_fundamentals[
        (silver_fundamentals["security_id"] == security_id)
        & (silver_fundamentals["metric_name_canonical"] == metric_name)
        & (silver_fundamentals["available_from"] <= as_of_ts)
    ].copy()
    if facts.empty:
        return None

    if "available_to" in facts.columns:
        facts = facts[facts["available_to"].isna() | (as_of_ts < facts["available_to"])]
    if facts.empty:
        return None

    row = facts.sort_values("available_from", kind="stable").iloc[-1]
    staleness_days = int((as_of_ts.normalize() - pd.Timestamp(row["available_from"]).tz_convert("UTC").normalize()).days)
    return {
        "security_id": row["security_id"],
        "metric_name_canonical": row["metric_name_canonical"],
        "metric_value": row["metric_value"],
        "source_available_from": row["available_from"],
        "source_available_to": row.get("available_to"),
        "is_restatement": row["is_restatement"],
        "staleness_days": staleness_days,
    }


def pit_join_fundamentals(
    panel: pd.DataFrame,
    silver_fundamentals: pd.DataFrame,
    metrics: list[str],
    *,
    as_of_column: str = "as_of_timestamp",
) -> pd.DataFrame:
    """Join selected fundamentals point-in-time and preserve source timestamps."""

    if panel.empty:
        return panel.copy()

    output = panel.copy()
    output["security_id"] = output["security_id"].astype("string")
    output[as_of_column] = pd.to_datetime(output[as_of_column], errors="coerce", utc=True)
    output["_row_id"] = range(len(output))

    right = silver_fundamentals.copy()
    right["security_id"] = right["security_id"].astype("string")
    right["metric_name_canonical"] = right["metric_name_canonical"].astype("string")
    right["available_from"] = pd.to_datetime(right["available_from"], errors="coerce", utc=True)
    right["available_to"] = pd.to_datetime(right["available_to"], errors="coerce", utc=True)

    for metric in metrics:
        metric_facts = right[right["metric_name_canonical"] == metric].copy()
        metric_results: list[pd.DataFrame] = []
        for security_id, left_group in output[["_row_id", "security_id", as_of_column]].groupby("security_id", sort=False):
            left_sorted = left_group.sort_values(as_of_column, kind="stable")
            facts_sorted = metric_facts.loc[metric_facts["security_id"] == security_id].sort_values("available_from", kind="stable")

            if facts_sorted.empty:
                empty = left_sorted.copy()
                empty["metric_value"] = pd.NA
                empty["available_from"] = pd.NaT
                empty["available_to"] = pd.NaT
                empty["staleness_days"] = pd.Series(pd.NA, index=empty.index, dtype="Int32")
                metric_results.append(empty)
                continue

            merged = pd.merge_asof(
                left_sorted,
                facts_sorted[["available_from", "available_to", "metric_value"]],
                left_on=as_of_column,
                right_on="available_from",
                direction="backward",
                allow_exact_matches=True,
            )

            invalid = merged["available_to"].notna() & (merged[as_of_column] >= merged["available_to"])
            merged.loc[invalid, ["metric_value", "available_from", "available_to"]] = [pd.NA, pd.NaT, pd.NaT]
            merged["staleness_days"] = (
                merged[as_of_column].dt.normalize() - pd.to_datetime(merged["available_from"], errors="coerce", utc=True).dt.normalize()
            ).dt.days.astype("Int32")
            metric_results.append(merged)

        metric_frame = pd.concat(metric_results, ignore_index=True).set_index("_row_id").sort_index()
        output[metric] = metric_frame["metric_value"].reindex(output["_row_id"]).values
        output[f"source_available_from__{metric}"] = metric_frame["available_from"].reindex(output["_row_id"]).reset_index(drop=True)
        output[f"staleness_days__{metric}"] = metric_frame["staleness_days"].reindex(output["_row_id"]).reset_index(drop=True)

    return output.drop(columns="_row_id").reset_index(drop=True)


@dataclass(frozen=True)
class PitDiagnostics:
    coverage_by_metric: pd.DataFrame
    null_ratio_by_metric: pd.DataFrame


def build_pit_diagnostics(joined_panel: pd.DataFrame, metrics: list[str]) -> PitDiagnostics:
    """Compute PIT coverage and null-ratio diagnostics for joined metrics."""

    rows = []
    total_rows = max(len(joined_panel), 1)
    for metric in metrics:
        non_null = int(joined_panel[metric].notna().sum()) if metric in joined_panel.columns else 0
        coverage = non_null / total_rows
        null_ratio = 1.0 - coverage
        rows.append(
            {
                "metric_name_canonical": metric,
                "rows_total": total_rows,
                "rows_non_null": non_null,
                "coverage_ratio": coverage,
                "null_ratio": null_ratio,
            }
        )
    frame = pd.DataFrame(rows)
    return PitDiagnostics(
        coverage_by_metric=frame[["metric_name_canonical", "rows_total", "rows_non_null", "coverage_ratio"]],
        null_ratio_by_metric=frame[["metric_name_canonical", "null_ratio"]],
    )
