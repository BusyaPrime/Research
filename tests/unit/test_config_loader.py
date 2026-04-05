from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from alpha_research.config.loader import (
    ConfigValidationError,
    build_config_snapshot,
    load_resolved_config_bundle,
)


def test_load_resolved_config_bundle(repo_root: Path) -> None:
    loaded = load_resolved_config_bundle(repo_root)
    assert loaded.bundle.project.project_code == "ARP-US-Daily-CS-01"
    assert len(loaded.bundle.experiments) == 4
    assert loaded.bundle.runtime.operational_experiment_key == "exp_gbm_ranker"
    assert loaded.bundle.runtime.policy.strict_operational is True


def test_config_hash_changes_when_config_changes(repo_copy: Path) -> None:
    original = load_resolved_config_bundle(repo_copy)

    project_path = repo_copy / "configs" / "project.yaml"
    payload = yaml.safe_load(project_path.read_text(encoding="utf-8"))
    payload["default_random_seed"] = 777
    project_path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")

    mutated = load_resolved_config_bundle(repo_copy)
    assert original.config_hash != mutated.config_hash


def test_missing_mandatory_field_fails_fast(repo_copy: Path) -> None:
    project_path = repo_copy / "configs" / "project.yaml"
    payload = yaml.safe_load(project_path.read_text(encoding="utf-8"))
    payload.pop("project_name")
    project_path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")

    with pytest.raises(ConfigValidationError):
        load_resolved_config_bundle(repo_copy)


def test_unknown_extra_field_warn_or_fail_by_policy(repo_copy: Path) -> None:
    project_path = repo_copy / "configs" / "project.yaml"
    payload = yaml.safe_load(project_path.read_text(encoding="utf-8"))
    payload["unexpected_field"] = "boom"
    project_path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")

    with pytest.raises(ConfigValidationError):
        load_resolved_config_bundle(repo_copy, extra_policy="forbid")

    warned = load_resolved_config_bundle(repo_copy, extra_policy="warn")
    assert "project.yaml: unexpected_field" in warned.warnings


def test_config_snapshot_preserves_all_files(repo_root: Path) -> None:
    snapshot = build_config_snapshot(repo_root / "configs")
    assert snapshot.config_hash
    assert len(snapshot.entries) == 18
