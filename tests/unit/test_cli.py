from __future__ import annotations

from pathlib import Path

from alpha_research.cli.main import main


def test_run_full_pipeline_dry_run_has_no_side_effects(repo_copy: Path) -> None:
    before = sorted(path.relative_to(repo_copy).as_posix() for path in repo_copy.rglob("*") if path.is_file())
    code = main(["run-full-pipeline", "--root", str(repo_copy), "--dry-run"])
    after = sorted(path.relative_to(repo_copy).as_posix() for path in repo_copy.rglob("*") if path.is_file())

    assert code == 0
    assert before == after


def test_bootstrap_writes_manifest(repo_copy: Path) -> None:
    code = main(["bootstrap", "--root", str(repo_copy)])
    manifests = list((repo_copy / "artifacts" / "bootstrap").rglob("bootstrap_manifest.json"))

    assert code == 0
    assert manifests
