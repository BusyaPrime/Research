from __future__ import annotations

from pathlib import Path

from alpha_research.tracking.runtime import capture_runtime_metadata


def test_capture_runtime_metadata(repo_root: Path) -> None:
    metadata = capture_runtime_metadata(repo_root)
    assert metadata.python_version
    assert metadata.environment_fingerprint_hash
    assert isinstance(metadata.git_commit_hash, str | None)
