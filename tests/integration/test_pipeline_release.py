from __future__ import annotations

import json

from alpha_research.common.paths import RepositoryPaths
from alpha_research.config.loader import load_resolved_config_bundle
from alpha_research.config.models import CapacityConfig, CapacityParticipationLimits, SplitsConfig
from alpha_research.pipeline.fixture_data import build_synthetic_research_bundle
from alpha_research.pipeline.runtime import execute_operational_command


def test_run_report_builds_release_bundle_and_stable_regression_fixture(workspace_repo_copy) -> None:
    loaded = load_resolved_config_bundle(workspace_repo_copy)
    result = execute_operational_command(
        "run-report",
        RepositoryPaths.from_root(workspace_repo_copy),
        loaded,
        synthetic_bundle=build_synthetic_research_bundle(
            start_date="2022-01-03",
            end_date="2024-12-31",
            n_securities=4,
            seed=7,
        ),
        split_config=SplitsConfig(
            train_years=1,
            validation_months=3,
            test_months=3,
            step_months=6,
            expanding_train=False,
            purge_days=5,
            embargo_days=5,
            nested_validation=True,
            min_train_observations=1,
            persist_fold_artifacts=True,
        ),
        capacity_config=CapacityConfig(
            aum_ladder_usd=[1_000_000.0],
            participation_limits=CapacityParticipationLimits(relaxed=0.02, base=0.01, strict=0.005, ultra_strict=0.0025),
            report_metrics=["net_sharpe", "fraction_trades_clipped"],
        ),
        universe_config=loaded.bundle.universe.model_copy(
            update={
                "min_price_usd": 1.0,
                "min_adv20_usd": 500_000.0,
                "min_feature_coverage_ratio": 0.1,
                "min_data_quality_score": 0.7,
            }
        ),
        cost_scenarios=["base"],
    )

    run_root = result.manifest_path.parent.parent
    review_bundle_path = run_root / "manifests" / "review_bundle.json"
    manifest_path = run_root / "manifests" / "pipeline_run_manifest.json"
    report_path = workspace_repo_copy / json.loads(review_bundle_path.read_text(encoding="utf-8"))["report_path"]
    report_bundle_path = workspace_repo_copy / json.loads(review_bundle_path.read_text(encoding="utf-8"))["report_bundle_path"]
    review_bundle = json.loads(review_bundle_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    report_bundle = json.loads(report_bundle_path.read_text(encoding="utf-8"))

    assert review_bundle_path.exists()
    assert manifest_path.exists()
    assert report_path.exists()
    assert report_bundle_path.exists()
    assert (workspace_repo_copy / "docs" / "release_checklist.md").exists()
    assert review_bundle["required_manifests"]
    assert review_bundle["required_reports"]
    assert review_bundle["temporary_simplifications"]

    for relative_path in review_bundle["required_manifests"].values():
        assert (workspace_repo_copy / relative_path).exists()
    for relative_path in review_bundle["required_reports"].values():
        if relative_path is not None:
            assert (workspace_repo_copy / relative_path).exists()
    for relative_path in review_bundle["report_section_paths"].values():
        assert (workspace_repo_copy / relative_path).exists()

    assert manifest["dataset_version"] == "gold_latest"
    assert review_bundle["report_html_path"]
    assert review_bundle["report_bundle_path"]
    assert review_bundle["key_metrics"]["feature_count"] == 87
    assert review_bundle["key_metrics"]["fold_count"] == 4
    assert review_bundle["key_metrics"]["dataset_row_count"] == 3012
    assert round(float(review_bundle["key_metrics"]["net_sharpe"]), 6) == -16.073303
    assert sorted(report_bundle["generated_formats"]) == ["html", "markdown"]
    assert report_bundle["section_artifacts"]
    assert report_bundle["figure_artifacts"]


def test_ci_workflow_runs_unit_integration_and_leakage_suites(repo_root) -> None:
    workflow = (repo_root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "python -m pytest tests/unit" in workflow
    assert "python -m pytest tests/integration" in workflow
    assert "python -m pytest tests/leakage" in workflow
