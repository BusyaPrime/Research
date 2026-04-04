from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from alpha_research.tracking.runtime import RuntimeMetadata


class ConfigSnapshotEntry(BaseModel):
    relative_path: str
    sha256: str
    content: Any


class ConfigSnapshot(BaseModel):
    config_hash: str
    entries: list[ConfigSnapshotEntry]


class BootstrapManifest(BaseModel):
    run_id: str
    status: str = "bootstrap_ok"
    dataset_version: str = "unbuilt"
    config_hash: str
    config_snapshot_path: str
    schema_paths: list[str]
    spec_hashes: dict[str, str]
    runtime_metadata: RuntimeMetadata
    notes: list[str] = Field(default_factory=list)


class StageArtifact(BaseModel):
    name: str
    path: str
    row_count: int | None = None
    format: str | None = None
    notes: list[str] = Field(default_factory=list)


class PipelineRunManifest(BaseModel):
    run_id: str
    command: str
    status: str
    dataset_version: str
    config_hash: str
    runtime_metadata: RuntimeMetadata
    started_at_utc: str
    completed_at_utc: str
    artifacts: list[StageArtifact] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ReviewBundle(BaseModel):
    run_id: str
    manifest_path: str
    report_path: str
    release_checklist_path: str
    required_manifests: dict[str, str]
    required_reports: dict[str, str]
    key_metrics: dict[str, float | int | str | None]
    temporary_simplifications: list[str] = Field(default_factory=list)


def write_json_document(payload: Any, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return path


def write_model_document(model: BaseModel, path: Path) -> Path:
    return write_json_document(model.model_dump(mode="json"), path)
