from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from alpha_research.release.verification import ReleaseVerificationError, verify_release_bundle


def _write_json(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _build_release_fixture(root: Path) -> Path:
    run_root = root / "artifacts" / "runs" / "run_001"
    manifests_dir = run_root / "manifests"
    reports_dir = run_root / "reports"
    figures_dir = reports_dir / "figures"
    sections_dir = reports_dir / "sections"
    docs_dir = root / "docs"

    docs_dir.mkdir(parents=True, exist_ok=True)
    sections_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "release_checklist.md").write_text("# release\n", encoding="utf-8")
    (reports_dir / "final_report.md").parent.mkdir(parents=True, exist_ok=True)
    (reports_dir / "final_report.md").write_text("# report\n", encoding="utf-8")
    (reports_dir / "final_report.html").write_text("<html></html>\n", encoding="utf-8")
    (sections_dir / "01_executive_summary.md").write_text("## summary\n", encoding="utf-8")
    (figures_dir / "equity_curve.svg").write_text("<svg></svg>\n", encoding="utf-8")

    dataset_manifest = _write_json(manifests_dir / "dataset_manifest.json", {"status": "ok"})
    oof_manifest = _write_json(manifests_dir / "oof_manifest.json", {"status": "ok"})
    evaluation_manifest = _write_json(manifests_dir / "evaluation_manifest.json", {"status": "ok"})
    backtest_manifest = _write_json(manifests_dir / "backtest_manifest.json", {"status": "ok"})
    capacity_manifest = _write_json(manifests_dir / "capacity_manifest.json", {"status": "ok"})

    pipeline_manifest = _write_json(
        manifests_dir / "pipeline_run_manifest.json",
        {
            "run_id": "run_001",
            "dataset_version": "gold_latest",
            "config_hash": "abc123",
            "runtime_metadata": {"git_commit_hash": "deadbeef"},
            "artifacts": [{"name": "final_report", "path": "artifacts/runs/run_001/reports/final_report.md"}],
        },
    )
    report_bundle = _write_json(
        manifests_dir / "report_bundle.json",
        {
            "generated_formats": ["markdown", "html"],
            "figure_artifacts": [
                {
                    "figure_name": "equity_curve",
                    "status": "generated",
                    "path": "artifacts/runs/run_001/reports/figures/equity_curve.svg",
                }
            ],
        },
    )
    review_bundle = _write_json(
        manifests_dir / "review_bundle.json",
        {
            "run_id": "run_001",
            "manifest_path": str(pipeline_manifest.relative_to(root)),
            "report_path": "artifacts/runs/run_001/reports/final_report.md",
            "report_html_path": "artifacts/runs/run_001/reports/final_report.html",
            "report_bundle_path": str(report_bundle.relative_to(root)),
            "release_checklist_path": "docs/release_checklist.md",
            "required_manifests": {
                "dataset_manifest": str(dataset_manifest.relative_to(root)),
                "oof_manifest": str(oof_manifest.relative_to(root)),
                "evaluation_manifest": str(evaluation_manifest.relative_to(root)),
                "backtest_manifest": str(backtest_manifest.relative_to(root)),
                "capacity_manifest": str(capacity_manifest.relative_to(root)),
                "pipeline_run_manifest": str(pipeline_manifest.relative_to(root)),
            },
            "required_reports": {
                "final_report": "artifacts/runs/run_001/reports/final_report.md",
                "final_report_html": "artifacts/runs/run_001/reports/final_report.html",
            },
            "report_section_paths": {
                "executive_summary": "artifacts/runs/run_001/reports/sections/01_executive_summary.md",
            },
            "key_metrics": {"primary_model_name": "gradient_boosting_ranker"},
            "pending_outputs": [],
            "temporary_simplifications": [],
            "runtime_class": "ReleaseCandidateRuntime",
            "capability_class": "release_candidate",
            "release_eligible": True,
        },
    )
    return review_bundle


def test_verify_release_bundle_accepts_complete_bundle(tmp_path: Path) -> None:
    review_bundle_path = _build_release_fixture(tmp_path)
    result = verify_release_bundle(tmp_path, review_bundle_path)
    assert result.ok is True
    assert result.manifest_count == 6
    assert result.report_count == 2
    assert result.section_count == 1
    assert result.figure_count == 1
    assert result.pending_output_count == 0


def test_verify_release_bundle_fails_when_required_figure_missing(tmp_path: Path) -> None:
    review_bundle_path = _build_release_fixture(tmp_path)
    figure_path = tmp_path / "artifacts" / "runs" / "run_001" / "reports" / "figures" / "equity_curve.svg"
    figure_path.unlink()
    with pytest.raises(ReleaseVerificationError):
        verify_release_bundle(tmp_path, review_bundle_path)


def test_release_verifier_script_reports_success(repo_root: Path, tmp_path: Path) -> None:
    review_bundle_path = _build_release_fixture(tmp_path)
    completed = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "verify_release_bundle.py"),
            "--root",
            str(tmp_path),
            "--review-bundle",
            str(review_bundle_path),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["status"] == "ok"
    assert payload["figure_count"] == 1


def test_verify_release_bundle_rejects_non_release_eligible_review_bundle(tmp_path: Path) -> None:
    review_bundle_path = _build_release_fixture(tmp_path)
    payload = json.loads(review_bundle_path.read_text(encoding="utf-8"))
    payload["release_eligible"] = False
    payload["capability_class"] = "fixture_only"
    payload["runtime_class"] = "FixtureResearchRuntime"
    review_bundle_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseVerificationError, match="non-release-eligible"):
        verify_release_bundle(tmp_path, review_bundle_path)
