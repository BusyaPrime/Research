from __future__ import annotations

from pathlib import Path

import yaml


def test_lego_progress_artifacts_exist(repo_root: Path) -> None:
    assert (repo_root / "docs" / "status" / "lego_progress.yaml").exists()
    assert (repo_root / "docs" / "status" / "lego_progress.md").exists()


def test_lego_progress_lists_all_epics(repo_root: Path) -> None:
    payload = yaml.safe_load((repo_root / "docs" / "status" / "lego_progress.yaml").read_text(encoding="utf-8"))
    epics = payload["epics"]
    assert len(epics) == 27
    assert epics[0]["epic_id"] == "E00"
    assert epics[-1]["epic_id"] == "E26"


def test_lego_progress_marks_known_tail_epics_as_not_fully_done(repo_root: Path) -> None:
    payload = yaml.safe_load((repo_root / "docs" / "status" / "lego_progress.yaml").read_text(encoding="utf-8"))
    status_by_epic = {item["epic_id"]: item["status"] for item in payload["epics"]}
    assert status_by_epic["E20"] == "partially_completed"
    assert status_by_epic["E22"] == "completed"
    assert status_by_epic["E25"] == "completed"
    assert status_by_epic["E26"] == "mostly_completed"
