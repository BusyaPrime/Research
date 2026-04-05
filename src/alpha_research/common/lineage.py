from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from alpha_research.common.hashing import hash_file, hash_mapping


def _normalize_scalar(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        if value.tzinfo is not None:
            return value.isoformat()
        return value.isoformat()
    if pd.isna(value):
        return None
    return value


def dataframe_schema_descriptor(frame: pd.DataFrame) -> list[dict[str, str]]:
    return [{"name": str(column), "dtype": str(dtype)} for column, dtype in zip(frame.columns, frame.dtypes, strict=False)]


def hash_dataframe_schema(frame: pd.DataFrame) -> str:
    return hash_mapping(dataframe_schema_descriptor(frame))


def dataframe_profile_descriptor(frame: pd.DataFrame) -> dict[str, Any]:
    null_counts = {str(column): int(frame[column].isna().sum()) for column in frame.columns}
    return {
        "row_count": int(len(frame)),
        "column_count": int(len(frame.columns)),
        "columns": [str(column) for column in frame.columns],
        "null_counts": null_counts,
    }


def hash_dataframe_profile(frame: pd.DataFrame) -> str:
    return hash_mapping(dataframe_profile_descriptor(frame))


def hash_dataframe_contents(frame: pd.DataFrame) -> str:
    normalized = frame.copy()
    for column in normalized.columns:
        series = normalized[column]
        if pd.api.types.is_datetime64_any_dtype(series):
            normalized[column] = pd.to_datetime(series, errors="coerce").map(_normalize_scalar)
        else:
            normalized[column] = series.map(_normalize_scalar)
    payload = normalized.to_dict(orient="records")
    return hash_mapping(payload)


def content_addressed_dataset_id(*, layer: str, dataset_version: str, content_sha256: str, schema_sha256: str) -> str:
    short_content = content_sha256[:12]
    short_schema = schema_sha256[:12]
    return f"{layer}__{dataset_version}__{short_content}__{short_schema}"


def file_sha256_or_none(path: Path) -> str | None:
    return hash_file(path) if path.exists() else None
