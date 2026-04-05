from __future__ import annotations

import json
from pathlib import Path

from alpha_research.pipeline.runtime import OperationalRunResult
from alpha_research.release.smoke import run_release_smoke
from alpha_research.release.verification import ReleaseVerificationResult


def test_release_smoke_runs_operational_path_and_writes_summary(minimal_repo, monkeypatch) -> None:
    def _fake_stage(command_name: str, root: Path, loaded) -> dict[str, object]:
        return {
            "command": command_name,
            "status": "completed",
            "manifest_path": f"data/raw/{command_name}.json",
            "primary_artifact_path": f"data/bronze/{command_name}.parquet",
        }

    def _fake_execute(command_name, paths, loaded, **kwargs) -> OperationalRunResult:
        run_root = paths.artifacts_dir / "runs" / "run-report-smoke"
        manifests_dir = run_root / "manifests"
        reports_dir = paths.reports_dir / "run-report-smoke"
        manifests_dir.mkdir(parents=True, exist_ok=True)
        reports_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = manifests_dir / "pipeline_run_manifest.json"
        review_bundle_path = manifests_dir / "review_bundle.json"
        report_path = reports_dir / "final_report.md"
        primary_artifact_path = reports_dir / "final_report.md"
        for path in (manifest_path, review_bundle_path, report_path):
            path.write_text("{}", encoding="utf-8")
        return OperationalRunResult(
            run_id="run-report-smoke",
            manifest_path=manifest_path,
            report_path=report_path,
            review_bundle_path=review_bundle_path,
            primary_artifact_path=primary_artifact_path,
            command=command_name,
            dataset_version="gold_latest",
            capability_class="release_candidate",
            release_eligible=True,
            notes=["smoke"],
        )

    def _fake_verify(root: Path, review_bundle_path: Path) -> ReleaseVerificationResult:
        return ReleaseVerificationResult(
            ok=True,
            review_bundle_path=review_bundle_path,
            manifest_count=5,
            report_count=5,
            section_count=14,
            figure_count=12,
            pending_output_count=0,
            notes=["generated_formats=markdown,html"],
        )

    monkeypatch.setattr("alpha_research.release.smoke.run_stage_command", _fake_stage)
    monkeypatch.setattr("alpha_research.release.smoke.execute_operational_command", _fake_execute)
    monkeypatch.setattr("alpha_research.release.smoke.verify_release_bundle", _fake_verify)

    result = run_release_smoke(minimal_repo)
    assert result.summary_path.exists()
    assert result.verification.ok is True
    assert result.ingest_commands_run == (
        "build-reference",
        "ingest-market",
        "ingest-fundamentals",
        "ingest-corporate-actions",
    )

    payload = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert payload["status"] == "completed"
    assert payload["verification"]["ok"] is True
    assert payload["verification"]["figure_count"] >= 1
    assert payload["operational_run"]["dataset_version"] == "gold_latest"


def test_release_smoke_runs_real_configured_local_fixture_path(minimal_repo) -> None:
    result = run_release_smoke(minimal_repo)
    assert result.summary_path.exists()
    assert result.verification.ok is True
    assert result.ingest_commands_run == (
        "build-reference",
        "ingest-market",
        "ingest-fundamentals",
        "ingest-corporate-actions",
    )

    payload = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert payload["prepared_fixture_dir"]
    assert payload["verification"]["pending_output_count"] == 0
    assert payload["verification"]["figure_count"] >= 1
