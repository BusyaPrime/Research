from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from alpha_research.common.hashing import hash_mapping
from alpha_research.common.io import read_json, write_json, write_parquet
from alpha_research.common.lineage import (
    content_addressed_dataset_id,
    file_sha256_or_none,
    hash_dataframe_contents,
    hash_dataframe_profile,
    hash_dataframe_schema,
)
from alpha_research.common.paths import RepositoryPaths


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def build_request_key(provider_name: str, endpoint_name: str, identifiers: list[str], start_date: str, end_date: str) -> str:
    payload = {
        "provider_name": provider_name,
        "endpoint_name": endpoint_name,
        "identifiers": sorted(str(item).upper() for item in identifiers),
        "start_date": str(start_date),
        "end_date": str(end_date),
    }
    return hash_mapping(payload)


@dataclass(frozen=True)
class DatasetPaths:
    root: Path

    @classmethod
    def from_root(cls, root: Path | None = None) -> DatasetPaths:
        return cls(root=RepositoryPaths.from_root(root).root)

    def raw_payload_path(self, dataset: str, request_key: str) -> Path:
        return self.root / "data" / "raw" / dataset / f"{request_key}.json"

    def raw_manifest_path(self, dataset: str, request_key: str) -> Path:
        return self.root / "data" / "raw" / dataset / "manifests" / f"{request_key}.json"

    def bronze_path(self, dataset: str, request_key: str) -> Path:
        return self.root / "data" / "bronze" / dataset / f"{request_key}.parquet"

    def failed_extract_path(self, dataset: str, request_key: str) -> Path:
        return self.root / "data" / "bronze" / dataset / "failed" / f"{request_key}.parquet"


def maybe_load_manifest(path: Path) -> dict[str, Any] | None:
    return read_json(path) if path.exists() else None


def persist_payload(path: Path, payload: Any) -> Path:
    return write_json(payload, path)


def persist_manifest(path: Path, manifest: dict[str, Any]) -> Path:
    return write_json(manifest, path)


def persist_bronze_frame(path: Path, frame: pd.DataFrame) -> Path:
    return write_parquet(frame, path)


def payload_digest(payload: Any) -> str:
    return hash_mapping(payload)


def bronze_lineage_descriptor(frame: pd.DataFrame, *, dataset: str, data_version: str, path: Path) -> dict[str, Any]:
    content_sha256 = hash_dataframe_contents(frame)
    schema_sha256 = hash_dataframe_schema(frame)
    profile_digest = hash_dataframe_profile(frame)
    return {
        "dataset_id": content_addressed_dataset_id(
            layer=f"bronze_{dataset}",
            dataset_version=data_version,
            content_sha256=content_sha256,
            schema_sha256=schema_sha256,
        ),
        "content_sha256": content_sha256,
        "schema_sha256": schema_sha256,
        "profile_digest": profile_digest,
        "file_sha256": file_sha256_or_none(path),
    }
