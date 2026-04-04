from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class FundamentalsQaOutputs:
    issue_rows: pd.DataFrame
    completeness_by_metric_year: pd.DataFrame
    staleness_by_security: pd.DataFrame
    report_sections: dict[str, dict[str, int | float]]


def run_fundamentals_qa(bronze_fundamentals: pd.DataFrame, as_of_date: str | pd.Timestamp | None = None) -> FundamentalsQaOutputs:
    frame = bronze_fundamentals.copy()
    frame["filing_date"] = pd.to_datetime(frame["filing_date"], errors="coerce").dt.normalize()
    frame["filing_date_utc"] = frame["filing_date"].dt.tz_localize("UTC")
    frame["acceptance_datetime"] = pd.to_datetime(frame["acceptance_datetime"], errors="coerce", utc=True)
    frame["available_from"] = pd.to_datetime(frame["available_from"], errors="coerce", utc=True)
    frame["metric_value_numeric"] = pd.to_numeric(frame["metric_value"], errors="coerce")

    issue_frames = [
        frame.loc[frame["metric_value_numeric"].isna(), ["security_id", "metric_name_canonical"]].assign(issue_type="metric_value_parseability"),
        frame.loc[frame["available_from"].isna(), ["security_id", "metric_name_canonical"]].assign(issue_type="missing_available_from"),
        frame.loc[
            (frame["acceptance_datetime"].notna())
            & (frame["filing_date_utc"].notna())
            & (frame["acceptance_datetime"].dt.normalize() < frame["filing_date_utc"]),
            ["security_id", "metric_name_canonical"],
        ].assign(issue_type="impossible_timestamp"),
    ]

    unit_counts = frame.dropna(subset=["metric_unit"]).groupby("metric_name_canonical")["metric_unit"].nunique()
    invalid_unit_metrics = unit_counts[unit_counts > 1].index.tolist()
    issue_frames.append(
        frame.loc[frame["metric_name_canonical"].isin(invalid_unit_metrics), ["security_id", "metric_name_canonical"]].assign(issue_type="metric_unit_inconsistent")
    )

    issue_rows = pd.concat(issue_frames, ignore_index=True)

    completeness = frame.copy()
    completeness["year"] = completeness["filing_date"].dt.year
    completeness_by_metric_year = (
        completeness.groupby(["metric_name_canonical", "year"], dropna=False)
        .agg(rows=("security_id", "size"), non_null_values=("metric_value_numeric", lambda values: values.notna().sum()))
        .reset_index()
    )

    as_of_ts = pd.Timestamp(as_of_date).tz_localize("UTC") if as_of_date is not None else frame["available_from"].max()
    latest = (
        frame.groupby("security_id", dropna=False)["available_from"]
        .max()
        .rename("latest_available_from")
        .reset_index()
    )
    latest["staleness_days"] = (as_of_ts - latest["latest_available_from"]).dt.days

    report_sections = {
        "parseability": {"issue_count": int((issue_rows["issue_type"] == "metric_value_parseability").sum())},
        "units": {"issue_count": int((issue_rows["issue_type"] == "metric_unit_inconsistent").sum())},
        "timestamps": {"issue_count": int((issue_rows["issue_type"] == "impossible_timestamp").sum())},
        "completeness": {"rows": int(len(completeness_by_metric_year))},
        "staleness": {"rows": int(len(latest))},
    }
    return FundamentalsQaOutputs(
        issue_rows=issue_rows,
        completeness_by_metric_year=completeness_by_metric_year,
        staleness_by_security=latest,
        report_sections=report_sections,
    )
