from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from alpha_research.data.schemas import schema_field_names, validate_dataframe


def build_silver_market(annotated_market: pd.DataFrame, root: Path | None = None) -> pd.DataFrame:
    """Build the silver market PIT layer from QA-annotated market data."""

    frame = annotated_market.copy()
    if "dollar_volume" not in frame.columns:
        frame["dollar_volume"] = frame["close"] * frame["volume"]
    if "is_price_valid" not in frame.columns:
        frame["is_price_valid"] = True
    if "is_volume_valid" not in frame.columns:
        frame["is_volume_valid"] = True
    if "tradable_flag_prelim" not in frame.columns:
        frame["tradable_flag_prelim"] = frame["is_price_valid"] & frame["is_volume_valid"]
    if "data_quality_score" not in frame.columns:
        frame["data_quality_score"] = 1.0

    fields = schema_field_names("silver_market_pit", root=root)
    silver = validate_dataframe(frame[fields], "silver_market_pit", root=root)
    return silver.sort_values(["security_id", "trade_date"], kind="stable").reset_index(drop=True)


def build_silver_fundamentals_pit(bronze_fundamentals: pd.DataFrame, root: Path | None = None) -> pd.DataFrame:
    """Intervalize fundamentals facts by `available_from` for PIT-safe joins."""

    frame = bronze_fundamentals.copy()
    frame["available_from"] = pd.to_datetime(frame["available_from"], errors="coerce", utc=True)
    frame = frame.sort_values(["security_id", "metric_name_canonical", "available_from"], kind="stable").reset_index(drop=True)
    next_available = frame.groupby(["security_id", "metric_name_canonical"], dropna=False)["available_from"].shift(-1)
    frame["available_to"] = next_available
    frame["is_latest_known_as_of_date"] = frame["available_to"].isna()
    frame["staleness_days"] = pd.Series(pd.NA, index=frame.index, dtype="Int32")

    fields = schema_field_names("silver_fundamentals_pit", root=root)
    silver = validate_dataframe(frame[fields], "silver_fundamentals_pit", root=root)
    return silver.sort_values(["security_id", "metric_name_canonical", "available_from"], kind="stable").reset_index(drop=True)


@dataclass(frozen=True)
class PitBuildDiagnostics:
    silver_market_rows: int
    silver_fundamentals_rows: int
    fundamentals_metrics: list[str]
