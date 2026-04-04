from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd
import yaml

from alpha_research.common.paths import RepositoryPaths


TYPE_MAP = {
    "string": "string",
    "float64": "float64",
    "int64": "Int64",
    "int32": "Int32",
    "bool": "boolean",
}


@dataclass(frozen=True)
class FieldSpec:
    field_name: str
    dtype: str
    nullable: bool
    description: str


@lru_cache(maxsize=1)
def load_table_schemas(root: str | None = None) -> dict[str, list[FieldSpec]]:
    paths = RepositoryPaths.from_root(Path(root) if root else None)
    raw = yaml.safe_load((paths.schema_dir / "table_schemas.yaml").read_text(encoding="utf-8"))
    schemas: dict[str, list[FieldSpec]] = {}
    for table_name, fields in raw.items():
        schemas[table_name] = [FieldSpec(**field) for field in fields]
    return schemas


def schema_field_names(table_name: str, root: Path | None = None) -> list[str]:
    schemas = load_table_schemas(str(root) if root else None)
    return [field.field_name for field in schemas[table_name]]


def _coerce_series(series: pd.Series, dtype: str) -> pd.Series:
    if dtype == "date":
        return pd.to_datetime(series, errors="coerce").dt.normalize()
    if dtype == "timestamp":
        return pd.to_datetime(series, errors="coerce", utc=True)
    if dtype == "array<string>":
        return series.map(lambda value: value if isinstance(value, list) else ([] if value is None else list(value)))
    if dtype in TYPE_MAP:
        mapped = TYPE_MAP[dtype]
        if mapped.startswith("Int") or mapped == "float64":
            return pd.to_numeric(series, errors="coerce").astype(mapped)
        if mapped == "boolean":
            return series.astype(mapped)
        return series.astype(mapped)
    raise KeyError(f"Unsupported schema dtype: {dtype}")


def coerce_to_schema(frame: pd.DataFrame, table_name: str, root: Path | None = None) -> pd.DataFrame:
    schemas = load_table_schemas(str(root) if root else None)
    spec = schemas[table_name]
    output = frame.copy()
    for field in spec:
        if field.field_name not in output.columns:
            output[field.field_name] = pd.NA
        output[field.field_name] = _coerce_series(output[field.field_name], field.dtype)
    ordered_columns = [field.field_name for field in spec] + [col for col in output.columns if col not in {f.field_name for f in spec}]
    return output[ordered_columns]


def validate_dataframe(frame: pd.DataFrame, table_name: str, root: Path | None = None, allow_extra: bool = False) -> pd.DataFrame:
    schemas = load_table_schemas(str(root) if root else None)
    spec = schemas[table_name]
    schema_fields = [field.field_name for field in spec]
    missing = [field for field in schema_fields if field not in frame.columns]
    if missing:
        raise ValueError(f"{table_name} missing required schema columns: {missing}")
    if not allow_extra:
        extra = [column for column in frame.columns if column not in schema_fields]
        if extra:
            raise ValueError(f"{table_name} contains unexpected columns: {extra}")

    output = coerce_to_schema(frame[schema_fields], table_name, root=root)
    for field in spec:
        if not field.nullable and output[field.field_name].isna().any():
            raise ValueError(f"{table_name}.{field.field_name} contains null values but is non-nullable")
    return output
