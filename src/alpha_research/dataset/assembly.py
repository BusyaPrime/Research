from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from alpha_research.common.io import write_json, write_parquet
from alpha_research.common.lineage import (
    content_addressed_dataset_id,
    file_sha256_or_none,
    hash_dataframe_contents,
    hash_dataframe_profile,
    hash_dataframe_schema,
)


@dataclass(frozen=True)
class DatasetManifest:
    dataset_id: str
    dataset_version: str
    row_count: int
    feature_count: int
    primary_label: str
    parquet_path: str
    content_sha256: str
    schema_sha256: str
    profile_digest: str
    file_sha256: str | None


@dataclass(frozen=True)
class GoldAssemblyResult:
    panel: pd.DataFrame
    manifest: DatasetManifest
    manifest_path: Path
    parquet_path: Path


def build_dataset_manifest(
    panel: pd.DataFrame,
    *,
    dataset_version: str,
    primary_label: str,
    parquet_path: Path,
    feature_columns: list[str],
) -> DatasetManifest:
    content_sha256 = hash_dataframe_contents(panel)
    schema_sha256 = hash_dataframe_schema(panel)
    profile_digest = hash_dataframe_profile(panel)
    dataset_id = content_addressed_dataset_id(
        layer="gold",
        dataset_version=dataset_version,
        content_sha256=content_sha256,
        schema_sha256=schema_sha256,
    )
    return DatasetManifest(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        row_count=int(len(panel)),
        feature_count=int(len(feature_columns)),
        primary_label=primary_label,
        parquet_path=str(parquet_path),
        content_sha256=content_sha256,
        schema_sha256=schema_sha256,
        profile_digest=profile_digest,
        file_sha256=file_sha256_or_none(parquet_path),
    )


def build_gold_panel(
    feature_panel: pd.DataFrame,
    label_panel: pd.DataFrame,
    *,
    dataset_version: str,
    primary_label: str,
    root: Path | None = None,
    parquet_path: Path | None = None,
    persist: bool = True,
    feature_vector_version: str = "v1",
    label_family_version: str = "v1",
) -> GoldAssemblyResult:
    base_columns = ["date", "security_id", "symbol", "is_in_universe", "sector", "industry", "liquidity_bucket", "beta_estimate", "feature_coverage_ratio"]
    excluded_non_feature_columns = {
        "feature_vector_version",
        "label_family_version",
        "row_valid_flag",
        "row_drop_reason",
        "as_of_timestamp",
        "latest_filing_available_from",
        "exclusion_reason_code",
        "price_t",
        "adv20_usd_t",
        "data_quality_score",
        "open",
        "high",
        "low",
        "close",
        "adj_close",
        "volume",
        "dollar_volume",
        "benchmark_close",
        "benchmark_open",
        "benchmark_return_current",
    }
    features = feature_panel.copy()
    labels = label_panel.copy()

    merged = features.merge(
        labels[[col for col in labels.columns if col.startswith("label_")] + ["date", "security_id"]],
        on=["date", "security_id"],
        how="left",
    )
    merged["feature_vector_version"] = feature_vector_version
    merged["label_family_version"] = label_family_version
    merged["row_valid_flag"] = merged["is_in_universe"].fillna(False) & merged[primary_label].notna()
    merged["row_drop_reason"] = pd.Series(pd.NA, index=merged.index, dtype="string")
    merged.loc[~merged["is_in_universe"].fillna(False), "row_drop_reason"] = "not_in_universe"
    merged.loc[merged["is_in_universe"].fillna(False) & merged[primary_label].isna(), "row_drop_reason"] = "missing_primary_label"

    output_path = parquet_path or (root or Path.cwd()) / "data" / "gold" / f"gold_model_panel__{dataset_version}.parquet"
    if persist:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        write_parquet(merged, output_path)

    feature_columns = [
        col
        for col in merged.columns
        if col not in base_columns
        and not col.startswith("label_")
        and col not in excluded_non_feature_columns
        and not col.startswith("source_available_from__")
        and not col.startswith("staleness_days__")
    ]
    manifest = build_dataset_manifest(
        merged,
        dataset_version=dataset_version,
        primary_label=primary_label,
        parquet_path=output_path,
        feature_columns=feature_columns,
    )
    manifest_path = output_path.with_suffix(".manifest.json")
    write_json(manifest.__dict__, manifest_path)
    return GoldAssemblyResult(panel=merged, manifest=manifest, manifest_path=manifest_path, parquet_path=output_path)
