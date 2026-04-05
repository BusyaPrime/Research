from __future__ import annotations

from dataclasses import replace
import json
from types import SimpleNamespace

import pandas as pd

from alpha_research.common.paths import RepositoryPaths
from alpha_research.config.loader import load_resolved_config_bundle
from alpha_research.config.models import CapacityConfig, CapacityParticipationLimits, SplitsConfig
from alpha_research.pipeline.fixture_data import build_synthetic_research_bundle
from alpha_research.pipeline.runtime import execute_operational_command
from alpha_research.splits.engine import FoldDefinition
from alpha_research.training.oof import ModelRunSpec


def test_run_report_builds_release_bundle_and_stable_regression_fixture(workspace_repo_copy, monkeypatch) -> None:
    loaded = load_resolved_config_bundle(workspace_repo_copy)
    gbm_experiment = loaded.bundle.experiments["exp_gbm_ranker"].model_copy(
        update={
            "featureset": "technical_liquidity_only",
            "model": loaded.bundle.experiments["exp_gbm_ranker"].model.model_copy(update={"n_trials": 2}),
        }
    )
    loaded = replace(
        loaded,
        bundle=loaded.bundle.model_copy(update={"experiments": {"exp_gbm_ranker": gbm_experiment}}),
    )

    dates = pd.date_range("2024-01-02", periods=6, freq="B")
    security_ids = ["SEC_000", "SEC_001", "SEC_002"]
    universe_snapshot = pd.DataFrame(
        [
            {
                "date": date,
                "security_id": security_id,
                "is_in_universe": True,
                "exclusion_reason_code": pd.NA,
                "price_t": 20.0 + idx,
                "adv20_usd_t": 2_500_000.0 + idx * 100_000.0,
                "feature_coverage_ratio": 1.0,
                "data_quality_score": 0.99,
                "liquidity_bucket": "high" if idx == 0 else "medium",
            }
            for date in dates
            for idx, security_id in enumerate(security_ids)
        ]
    )
    feature_panel = pd.DataFrame(
        [
            {
                "date": date,
                "security_id": security_id,
                "symbol": security_id.replace("SEC_", "S"),
                "sector": "Technology" if idx % 2 == 0 else "Financials",
                "industry": "Software" if idx % 2 == 0 else "Banks",
                "is_in_universe": True,
                "liquidity_bucket": "high" if idx == 0 else "medium",
                "beta_estimate": 0.9 + idx * 0.05,
                "feature_coverage_ratio": 1.0,
                "as_of_timestamp": pd.Timestamp(date).tz_localize("UTC") + pd.Timedelta(hours=21),
                "adv20": 2_500_000.0 + idx * 100_000.0,
                "borrow_status": "medium",
                "ret_1": 0.01 * (idx + 1),
                "rev_1": -0.01 * (idx + 1),
                "mom_21_ex1": 0.02 * (idx + 1),
                "book_to_price": 0.3 + idx * 0.05,
                "vol_21": 0.15 + idx * 0.01,
            }
            for date in dates
            for idx, security_id in enumerate(security_ids)
        ]
    )
    label_panel = feature_panel[["date", "security_id", "sector", "beta_estimate"]].copy()
    label_panel["label_excess_5d_oo"] = [0.01, 0.015, 0.02] * len(dates)
    gold_panel = feature_panel.merge(label_panel[["date", "security_id", "label_excess_5d_oo"]], on=["date", "security_id"], how="left")
    gold_panel["row_valid_flag"] = True
    gold_panel["row_drop_reason"] = pd.NA
    gold_panel["liquidity_bucket"] = gold_panel["liquidity_bucket"].astype("string")
    fold = FoldDefinition(
        fold_id="fold_000",
        train_dates=tuple(pd.Timestamp(value) for value in dates[:2]),
        valid_dates=tuple(pd.Timestamp(value) for value in dates[2:4]),
        test_dates=tuple(pd.Timestamp(value) for value in dates[4:]),
        train_start=pd.Timestamp(dates[0]),
        train_end=pd.Timestamp(dates[1]),
        valid_start=pd.Timestamp(dates[2]),
        valid_end=pd.Timestamp(dates[3]),
        test_start=pd.Timestamp(dates[4]),
        test_end=pd.Timestamp(dates[5]),
        primary_horizon_days=5,
        purge_days_applied=5,
        embargo_days_applied=5,
        expanding_train=False,
    )
    fold_metadata = pd.DataFrame([{"fold_id": "fold_000", "train_rows": 2, "valid_rows": 2, "test_rows": 2}])
    predictions = pd.DataFrame(
        [
            {
                "date": date,
                "security_id": security_id,
                "fold_id": "fold_000",
                "model_name": "gradient_boosting_ranker",
                "raw_prediction": 0.1 + idx * 0.05,
                "rank_prediction": 0.33 + idx * 0.33,
                "bucket_prediction": idx,
                "prediction_timestamp": pd.Timestamp("2026-01-01T00:00:00Z"),
                "dataset_version": "gold_latest",
                "config_hash": loaded.config_hash,
            }
            for date in dates[4:]
            for idx, security_id in enumerate(security_ids)
        ]
    )
    daily_state = pd.DataFrame(
        [
            {
                "date": dates[4],
                "gross_exposure": 1.0,
                "net_exposure": 0.0,
                "turnover": 0.25,
                "gross_pnl": 150.0,
                "net_pnl": 120.0,
                "commission_cost": 5.0,
                "spread_cost": 7.0,
                "slippage_cost": 8.0,
                "impact_cost": 6.0,
                "borrow_cost": 4.0,
                "active_positions": 3,
                "aum": 1_000_120.0,
            },
            {
                "date": dates[5],
                "gross_exposure": 0.95,
                "net_exposure": 0.02,
                "turnover": 0.18,
                "gross_pnl": 90.0,
                "net_pnl": 70.0,
                "commission_cost": 4.0,
                "spread_cost": 5.0,
                "slippage_cost": 6.0,
                "impact_cost": 5.0,
                "borrow_cost": 3.0,
                "active_positions": 3,
                "aum": 1_000_190.0,
            },
        ]
    )
    holdings_snapshots = pd.DataFrame(
        [{"date": date, "security_id": security_id, "weight": 0.1, "sector": "Technology", "beta_estimate": 1.0, "liquidity_bucket": "high", "borrow_status": "medium", "aum": 1_000_000.0} for date in dates[4:] for security_id in security_ids]
    )
    trades = pd.DataFrame(
        [{"date": dates[4], "security_id": security_id, "executed_trade_weight": 0.05, "participation_ratio": 0.01, "clipped_flag": False, "untradable_flag": False} for security_id in security_ids]
    )
    daily_returns = pd.DataFrame(
        [{"date": dates[4], "gross_return": 0.00015, "net_return": 0.00012}, {"date": dates[5], "gross_return": 0.00009, "net_return": 0.00007}]
    )

    monkeypatch.setattr(
        "alpha_research.pipeline.runtime._build_model_specs",
        lambda experiment, seed, paths: [
            ModelRunSpec(
                name="gradient_boosting_ranker",
                params={"n_estimators": 12, "learning_rate": 0.1, "max_bins": 8, "min_leaf_size": 12},
                seed=seed,
            ),
            ModelRunSpec(name="heuristic_blend_score", seed=seed),
        ],
    )
    monkeypatch.setattr(
        "alpha_research.pipeline.runtime.run_ablation_suite",
        lambda **kwargs: type(
            "AblationStub",
            (),
            {
                "results": pd.DataFrame(
                    [
                        {"scenario_group": "feature_family", "scenario_name": "baseline_all_features", "rank_ic_mean": 0.1, "net_sharpe": 0.2},
                        {"scenario_group": "preprocessing", "scenario_name": "baseline_current", "rank_ic_mean": 0.09, "net_sharpe": 0.15},
                    ]
                )
            },
        )(),
    )
    monkeypatch.setattr(
        "alpha_research.pipeline.runtime.build_universe_snapshots",
        lambda *args, **kwargs: type("UniverseStub", (), {"snapshot": universe_snapshot.copy(), "diagnostics": pd.DataFrame()})(),
    )
    monkeypatch.setattr(
        "alpha_research.pipeline.runtime.build_feature_panel",
        lambda *args, **kwargs: type(
            "FeatureStub",
            (),
            {
                "panel": feature_panel.copy(),
                "feature_columns": ["ret_1", "rev_1", "mom_21_ex1", "book_to_price", "vol_21"],
                "feature_coverage": universe_snapshot[["date", "security_id", "feature_coverage_ratio"]].copy(),
            },
        )(),
    )
    monkeypatch.setattr(
        "alpha_research.pipeline.runtime.build_label_panel",
        lambda *args, **kwargs: type(
            "LabelStub",
            (),
            {
                "panel": label_panel.copy(),
                "overlap_report": {"allow_overlap": False, "purge_days": 5, "embargo_days": 5},
                "sanity_report": pd.DataFrame([{"label_name": "label_excess_5d_oo", "rows": len(label_panel)}]),
            },
        )(),
    )
    monkeypatch.setattr(
        "alpha_research.pipeline.runtime.build_gold_panel",
        lambda *args, **kwargs: SimpleNamespace(
            panel=gold_panel.copy(),
            manifest=SimpleNamespace(
                dataset_version="gold_latest",
                row_count=len(gold_panel),
                feature_count=5,
                primary_label="label_excess_5d_oo",
                parquet_path="artifacts/tmp/gold_panel.parquet",
            ),
            manifest_path=workspace_repo_copy / "artifacts" / "tmp" / "gold_panel.manifest.json",
            parquet_path=workspace_repo_copy / "artifacts" / "tmp" / "gold_panel.parquet",
        ),
    )
    monkeypatch.setattr(
        "alpha_research.pipeline.runtime.generate_walk_forward_splits",
        lambda *args, **kwargs: type(
            "SplitStub",
            (),
            {
                "folds": [fold],
                "metadata": fold_metadata.copy(),
                "timeline_plot": "fold_timeline\nfold_000: stub",
                "protocol": type(
                    "ProtocolStub",
                    (),
                    {"to_dict": lambda self: {"fold_count": 1, "checks": {"no_overlap": True}}},
                )(),
                "role_matrix": pd.DataFrame(
                    [
                        {"fold_id": "fold_000", "date": dates[0], "role": "train"},
                        {"fold_id": "fold_000", "date": dates[2], "role": "valid"},
                        {"fold_id": "fold_000", "date": dates[4], "role": "test"},
                    ]
                ),
            },
        )(),
    )
    monkeypatch.setattr(
        "alpha_research.pipeline.runtime.generate_oof_predictions",
        lambda *args, **kwargs: type(
            "OofStub",
            (),
            {
                "predictions": predictions.copy(),
                "coverage_by_fold": pd.DataFrame([{"fold_id": "fold_000", "model_name": "gradient_boosting_ranker", "row_count": len(predictions), "unique_dates": 2}]),
                "tuning_diagnostics": pd.DataFrame([{"model_name": "gradient_boosting_ranker", "n_estimators": 12, "learning_rate": 0.1, "max_bins": 8, "min_leaf_size": 12, "validation_rank_ic_mean": 0.2}]),
                "data_usage_trace": pd.DataFrame(
                    [
                        {
                            "fold_id": "fold_000",
                            "model_name": "gradient_boosting_ranker",
                            "protocol": "train_valid_refit_then_test",
                            "preprocessing_fit_scope": "train_only",
                            "final_fit_scope": "train_plus_valid",
                            "predict_scope": "test_only",
                        }
                    ]
                ),
                "manifest": {
                    "dataset_version": "gold_latest",
                    "row_count": len(predictions),
                    "models": ["gradient_boosting_ranker"],
                    "oof_purity_checks": {"unique_prediction_rows": True, "test_only_predictions": True},
                },
            },
        )(),
    )
    monkeypatch.setattr(
        "alpha_research.pipeline.runtime.run_backtest",
        lambda *args, **kwargs: type(
            "BacktestStub",
            (),
            {
                "daily_state": daily_state.copy(),
                "holdings_snapshots": holdings_snapshots.copy(),
                "trades": trades.copy(),
                "daily_returns": daily_returns.copy(),
            },
        )(),
    )
    monkeypatch.setattr(
        "alpha_research.pipeline.runtime.run_capacity_analysis",
        lambda *args, **kwargs: type(
            "CapacityStub",
            (),
            {
                "results": pd.DataFrame([{"aum_level": 1_000_000.0, "scenario": "base", "net_sharpe": 0.3, "median_participation": 0.01, "p95_participation": 0.02, "fraction_trades_clipped": 0.0, "fraction_names_untradable": 0.0}]),
                "diagnostics": pd.DataFrame([{"aum_level": 1_000_000.0, "scenario": "base", "max_participation": 0.02, "daily_state_rows": 2, "trade_rows": 3}]),
            },
        )(),
    )
    result = execute_operational_command(
        "run-report",
        RepositoryPaths.from_root(workspace_repo_copy),
        loaded,
        synthetic_bundle=build_synthetic_research_bundle(
            start_date="2023-01-03",
            end_date="2024-06-28",
            n_securities=3,
            seed=7,
        ),
        split_config=SplitsConfig(
            train_years=1,
            validation_months=2,
            test_months=2,
            step_months=4,
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
    assert review_bundle["temporary_simplifications"] == []
    assert review_bundle["capability_class"] == "fixture_only"
    assert review_bundle["release_eligible"] is False

    for relative_path in review_bundle["required_manifests"].values():
        assert (workspace_repo_copy / relative_path).exists()
    for relative_path in review_bundle["required_reports"].values():
        if relative_path is not None:
            assert (workspace_repo_copy / relative_path).exists()
    for relative_path in review_bundle["report_section_paths"].values():
        assert (workspace_repo_copy / relative_path).exists()

    assert manifest["dataset_version"] == "gold_latest"
    assert manifest["status"] == "completed_fixture_only"
    assert manifest["capability_class"] == "fixture_only"
    assert manifest["release_eligible"] is False
    assert review_bundle["report_html_path"]
    assert review_bundle["report_bundle_path"]
    assert review_bundle["key_metrics"]["primary_model_name"] == "gradient_boosting_ranker"
    assert review_bundle["key_metrics"]["feature_count"] == 4
    assert review_bundle["key_metrics"]["fold_count"] >= 1
    assert review_bundle["key_metrics"]["dataset_row_count"] > 0
    assert review_bundle["key_metrics"]["ablation_rows"] == 2
    assert review_bundle["key_metrics"]["approval_status"] == "not_release_eligible"
    assert sorted(report_bundle["generated_formats"]) == ["html", "markdown"]
    assert report_bundle["section_artifacts"]
    assert report_bundle["figure_artifacts"]
    assert all(item["status"] == "generated" for item in report_bundle["figure_artifacts"])
    assert any(artifact["name"] == "ablation_results" for artifact in manifest["artifacts"])
    assert any(artifact["name"] == "predictive_uncertainty" for artifact in manifest["artifacts"])
    assert any(artifact["name"] == "approval_summary" for artifact in manifest["artifacts"])


def test_ci_workflow_runs_unit_integration_and_leakage_suites(repo_root) -> None:
    workflow = (repo_root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "python -m pytest tests/unit" in workflow
    assert "python -m pytest tests/integration" in workflow
    assert "python -m pytest tests/leakage" in workflow
