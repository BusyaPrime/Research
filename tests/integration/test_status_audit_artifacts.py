from __future__ import annotations

from pathlib import Path

import yaml


def test_status_audit_files_exist(repo_root: Path) -> None:
    assert (repo_root / "docs" / "status" / "README.md").exists()
    assert (repo_root / "docs" / "status" / "implementation_status.yaml").exists()
    assert (repo_root / "docs" / "status" / "spec_gap_audit.md").exists()


def test_machine_readable_status_lists_operational_gaps_and_simplifications(repo_root: Path) -> None:
    payload = yaml.safe_load((repo_root / "docs" / "status" / "implementation_status.yaml").read_text(encoding="utf-8"))
    assert payload["overall_status"]["end_to_end_pipeline_present"] is True
    assert payload["overall_status"]["release_ready"] is False
    assert payload["operational_commands"]["run-full-pipeline"] == "operational"
    assert payload["operational_commands"]["ingest-market"] == "stub"
    assert payload["temporary_simplifications"]
    assert payload["open_gaps"]


def test_spec_gap_audit_explicitly_states_not_fully_done(repo_root: Path) -> None:
    content = (repo_root / "docs" / "status" / "spec_gap_audit.md").read_text(encoding="utf-8")
    assert "примерно в зоне `85-87%`" in content
    assert "еще не тот момент" in content
