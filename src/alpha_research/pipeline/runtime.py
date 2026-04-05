from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from alpha_research.backtest.engine import run_backtest
from alpha_research.capacity.engine import run_capacity_analysis
from alpha_research.common.io import read_json, write_json, write_parquet
from alpha_research.common.manifests import (
    PipelineRunManifest,
    ReportBundle,
    ReportFigureArtifact,
    ReportSectionArtifact,
    ReviewBundle,
    StageArtifact,
    write_model_document,
)
from alpha_research.common.paths import RepositoryPaths
from alpha_research.config.loader import LoadedConfigBundle
from alpha_research.config.models import CapacityConfig, ExperimentConfig, SplitsConfig, UniverseConfig
from alpha_research.dataset.assembly import build_gold_panel
from alpha_research.evaluation.ablation import run_ablation_suite
from alpha_research.evaluation.figures import render_mandatory_figures
from alpha_research.evaluation.metrics import (
    build_decay_response_curve,
    compute_portfolio_metrics,
    compute_predictive_metrics,
    compute_regime_breakdown,
)
from alpha_research.evaluation.reporting import render_final_report, render_final_report_html, render_report_sections
from alpha_research.features.engine import FeatureBuildResult, build_feature_panel
from alpha_research.features.registry import feature_names_by_family, load_feature_registry
from alpha_research.labels.engine import build_label_panel
from alpha_research.pipeline.bundle_loader import resolve_operational_bundle
from alpha_research.pipeline.fixture_data import SyntheticResearchBundle
from alpha_research.pipeline.policy import (
    IncompleteOperationalOutputs,
    RuntimeCapability,
    TemporarySimplificationViolation,
    UnsupportedExperimentForOperationalRun,
    resolve_runtime_capability,
)
from alpha_research.preprocessing.transforms import PreprocessingSpec
from alpha_research.splits.engine import generate_walk_forward_splits, persist_fold_metadata
from alpha_research.testing.leakage import assert_no_future_feature_timestamps
from alpha_research.tracking.runtime import capture_runtime_metadata
from alpha_research.training.oof import ModelRunSpec, generate_oof_predictions
from alpha_research.universe.builder import build_universe_snapshots


OPERATIONAL_COMMANDS = {
    "build-reference",
    "build-silver",
    "build-universe",
    "build-features",
    "build-labels",
    "build-gold",
    "run-train",
    "run-predict-oof",
    "run-backtest",
    "run-capacity",
    "run-report",
    "run-full-pipeline",
}

PRIMARY_ARTIFACT_BY_COMMAND = {
    "build-reference": "security_master",
    "build-silver": "silver_market",
    "build-universe": "universe_snapshot",
    "build-features": "feature_panel",
    "build-labels": "label_panel",
    "build-gold": "gold_panel",
    "run-train": "fold_metadata",
    "run-predict-oof": "oof_predictions",
    "run-backtest": "portfolio_daily_state",
    "run-capacity": "capacity_results",
    "run-report": "final_report",
    "run-full-pipeline": "final_report",
}

SUPPORTED_MODEL_NAMES = {
    "random_score",
    "heuristic_reversal_score",
    "heuristic_momentum_score",
    "heuristic_blend_score",
    "ridge_regression",
    "lasso_regression",
    "gradient_boosting_regressor",
    "gradient_boosting_ranker",
}


@dataclass(frozen=True)
class OperationalRunResult:
    run_id: str
    manifest_path: Path
    report_path: Path
    review_bundle_path: Path
    primary_artifact_path: Path
    command: str
    dataset_version: str
    capability_class: str
    release_eligible: bool
    notes: list[str]


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(value: datetime) -> str:
    return value.isoformat()


def _persist_frame(
    root: Path,
    path: Path,
    name: str,
    frame: pd.DataFrame,
    *,
    notes: list[str] | None = None,
) -> StageArtifact:
    write_parquet(frame, path)
    return StageArtifact(
        name=name,
        path=str(path.relative_to(root)),
        row_count=int(len(frame)),
        format="parquet",
        notes=list(notes or []),
    )


def _persist_json_artifact(
    root: Path,
    path: Path,
    name: str,
    payload: object,
    *,
    notes: list[str] | None = None,
) -> StageArtifact:
    write_json(payload, path)
    row_count = len(payload) if isinstance(payload, list) else None
    return StageArtifact(
        name=name,
        path=str(path.relative_to(root)),
        row_count=row_count,
        format="json",
        notes=list(notes or []),
    )


def _select_experiment(loaded: LoadedConfigBundle) -> ExperimentConfig:
    experiment_key = loaded.bundle.runtime.operational_experiment_key
    if experiment_key not in loaded.bundle.experiments:
        raise KeyError(f"В runtime config указан неизвестный operational_experiment_key: {experiment_key}")
    experiment = loaded.bundle.experiments[experiment_key]
    if (
        loaded.bundle.runtime.policy.enforce_supported_operational_experiment
        and experiment.model.name not in SUPPORTED_MODEL_NAMES
    ):
        raise UnsupportedExperimentForOperationalRun(
            "Operational run не будет молча деградировать до baseline: "
            f"experiment `{experiment_key}` использует неподдерживаемую модель `{experiment.model.name}`."
        )
    return experiment


def _resolve_preprocessing_spec(loaded: LoadedConfigBundle, experiment: ExperimentConfig) -> PreprocessingSpec:
    option_lookup = {option.name: option for option in loaded.bundle.preprocessing.winsorization_options}
    winsor_option = option_lookup.get(experiment.preprocessing.winsor)
    winsor_lower = None
    winsor_upper = None
    if winsor_option is not None and winsor_option.enabled:
        winsor_lower = winsor_option.lower_pct
        winsor_upper = winsor_option.upper_pct
    neutralizer = None if experiment.preprocessing.neutralizer == "none" else experiment.preprocessing.neutralizer
    scaler = None if experiment.preprocessing.scaler == "none" else experiment.preprocessing.scaler
    return PreprocessingSpec(
        winsor_lower=winsor_lower,
        winsor_upper=winsor_upper,
        scaler=scaler,
        neutralizer=neutralizer,
    )


def _resolve_feature_columns(feature_result: FeatureBuildResult, experiment: ExperimentConfig, root: Path) -> list[str]:
    registry = load_feature_registry(str(root))
    available = [column for column in feature_result.feature_columns if column in registry]
    if experiment.featureset == "all_features_v1":
        return available
    if experiment.featureset == "all_minus_interactions":
        interactions = set(feature_names_by_family("interactions", str(root)))
        return [column for column in available if column not in interactions]
    if experiment.featureset == "technical_liquidity_only":
        families = {"returns", "relative_returns", "volatility", "liquidity", "trend_state", "cross_sectional_context"}
        return [column for column in available if registry[column].family in families]
    return available


def _model_params_registry_path(paths: RepositoryPaths, model_name: str) -> Path:
    return paths.artifacts_dir / "model_registry" / f"{model_name}_best_params.json"


def _load_cached_model_params(paths: RepositoryPaths, model_name: str) -> dict[str, object]:
    path = _model_params_registry_path(paths, model_name)
    if not path.exists():
        return {}
    payload = read_json(path)
    if not isinstance(payload, dict):
        return {}
    best_params = payload.get("best_params", {})
    return best_params if isinstance(best_params, dict) else {}


def _build_model_specs(experiment: ExperimentConfig, seed: int, paths: RepositoryPaths) -> list[ModelRunSpec]:
    primary_params: dict[str, object] = {}
    if experiment.model.use_best_previous_params:
        primary_params = _load_cached_model_params(paths, experiment.model.name)
    primary = ModelRunSpec(
        name=experiment.model.name,
        alpha_grid=tuple(experiment.model.alpha_grid or ()),
        n_trials=experiment.model.n_trials,
        params=primary_params,
        seed=seed,
    )
    secondary = [
        ModelRunSpec(name="heuristic_blend_score", seed=seed),
        ModelRunSpec(name="ridge_regression", alpha_grid=(0.1, 1.0, 10.0), seed=seed),
        ModelRunSpec(name="random_score", seed=seed),
    ]
    seen = set()
    ordered: list[ModelRunSpec] = []
    for spec in [primary, *secondary]:
        if spec.name in seen:
            continue
        ordered.append(spec)
        seen.add(spec.name)
    return ordered


def _regime_frame(predictions: pd.DataFrame, labels: pd.DataFrame, benchmark_market: pd.DataFrame, label_column: str) -> pd.DataFrame:
    benchmark = benchmark_market.copy()
    benchmark["date"] = pd.to_datetime(benchmark["trade_date"], errors="coerce").dt.normalize()
    benchmark = benchmark.sort_values("date", kind="stable").reset_index(drop=True)
    benchmark["benchmark_regime"] = benchmark["close"].pct_change(63).fillna(0.0).ge(0.0).map({True: "risk_on", False: "risk_off"})
    merged = predictions.merge(labels[["date", "security_id", label_column]], on=["date", "security_id"], how="left")
    return merged.merge(benchmark[["date", "benchmark_regime"]], on="date", how="left")


def _summary_lines_from_metrics(frame: pd.DataFrame, value_column: str = "value") -> list[str]:
    rows = []
    for row in frame.to_dict(orient="records"):
        metric = row.get("metric", row.get("scenario", row.get("regime", "metric")))
        value = row.get(value_column)
        rows.append(f"- {metric}: {value}")
    return rows


def _ablation_summary_lines(frame: pd.DataFrame) -> list[str]:
    rows: list[str] = []
    if frame.empty:
        return ["- ablation_rows: 0"]
    for scenario_group, group in frame.groupby("scenario_group", sort=False):
        best_rank_row = group.sort_values("rank_ic_mean", ascending=False, kind="stable").iloc[0]
        best_sharpe_row = group.sort_values("net_sharpe", ascending=False, kind="stable").iloc[0]
        rows.append(f"- {scenario_group}.rows: {len(group)}")
        rows.append(f"- {scenario_group}.best_rank_ic: {best_rank_row['scenario_name']} => {best_rank_row['rank_ic_mean']}")
        rows.append(f"- {scenario_group}.best_net_sharpe: {best_sharpe_row['scenario_name']} => {best_sharpe_row['net_sharpe']}")
    return rows


def _best_tuned_params(tuning_diagnostics: pd.DataFrame, model_name: str) -> dict[str, object]:
    if tuning_diagnostics.empty:
        return {}
    frame = tuning_diagnostics.loc[tuning_diagnostics["model_name"] == model_name].copy()
    if frame.empty:
        return {}
    candidate_columns = [column for column in ("n_estimators", "learning_rate", "max_bins", "min_leaf_size") if column in frame.columns]
    if not candidate_columns:
        return {}
    best_row = frame.sort_values("validation_rank_ic_mean", ascending=False, kind="stable").iloc[0]
    return {column: best_row[column] for column in candidate_columns}


def _feature_catalog_summary(feature_columns: list[str], root: Path) -> str:
    registry = load_feature_registry(str(root))
    family_counts: dict[str, int] = {}
    for column in feature_columns:
        family = registry[column].family
        family_counts[family] = family_counts.get(family, 0) + 1
    lines = [f"- feature_count: {len(feature_columns)}"]
    lines.extend(f"- {family}: {count}" for family, count in sorted(family_counts.items()))
    return "\n".join(lines)


def _source_mode_label(loaded: LoadedConfigBundle, synthetic_bundle: SyntheticResearchBundle | None) -> str:
    if synthetic_bundle is not None:
        return "explicit_synthetic_bundle_override"
    return loaded.bundle.runtime.ingest.provider_mode


def _next_steps_for_source_mode(source_mode: str) -> list[str]:
    if source_mode == "configured_adapters":
        return [
            "Проверить live adapter path против реального поставщика на rate limits, schema drift и secrets rotation.",
            "Дожать clean-room reproducible handoff на живом external data path без ручных оговорок.",
            "Расширить adapter layer вокруг benchmark/index feed и vendor-specific operational diagnostics.",
        ]
    return [
        "Заменить synthetic provider stub на реальные vendor adapters и нормальный secrets flow.",
        "Проверить operational ingest path против живого поставщика с rate limits и schema drift.",
        "Дожать release-hardening до clean-room reproducible handoff без ручных оговорок.",
    ]


def _release_eligibility(
    capability: RuntimeCapability,
    *,
    pending_formats: list[str],
    temporary_simplifications: list[str],
) -> bool:
    return capability.allows_release_bundle and not pending_formats and not temporary_simplifications


def execute_operational_command(
    command_name: str,
    paths: RepositoryPaths,
    loaded: LoadedConfigBundle,
    *,
    synthetic_bundle: SyntheticResearchBundle | None = None,
    split_config: SplitsConfig | None = None,
    capacity_config: CapacityConfig | None = None,
    universe_config: UniverseConfig | None = None,
    cost_scenarios: list[str] | None = None,
    bundle_start_date: str | None = None,
    bundle_end_date: str | None = None,
    bundle_n_securities: int | None = None,
    ablation_max_feature_family_scenarios: int | None = None,
    ablation_max_preprocessing_scenarios: int | None = None,
) -> OperationalRunResult:
    if command_name not in OPERATIONAL_COMMANDS:
        raise KeyError(f"Unsupported operational command: {command_name}")

    started_at = _now_utc()
    run_id = f"{command_name}-{started_at.strftime('%Y%m%dT%H%M%SZ')}"
    run_dir = paths.artifacts_dir / "runs" / run_id
    dataset_dir = run_dir / "datasets"
    diagnostics_dir = run_dir / "diagnostics"
    manifests_dir = run_dir / "manifests"
    report_dir = paths.reports_dir / run_id
    report_sections_dir = report_dir / "sections"
    for directory in (dataset_dir, diagnostics_dir, manifests_dir, report_dir):
        directory.mkdir(parents=True, exist_ok=True)
    report_sections_dir.mkdir(parents=True, exist_ok=True)

    experiment = _select_experiment(loaded)
    bundle = resolve_operational_bundle(
        paths,
        loaded,
        synthetic_bundle=synthetic_bundle,
        start_date=bundle_start_date,
        end_date=bundle_end_date,
        n_securities=bundle_n_securities,
    )
    runtime_metadata = capture_runtime_metadata(paths.root)
    capability = resolve_runtime_capability(
        loaded,
        synthetic_bundle_active=synthetic_bundle is not None or loaded.bundle.runtime.ingest.provider_mode == "synthetic_vendor_stub",
        command_name=command_name,
    )
    source_mode = _source_mode_label(loaded, synthetic_bundle)
    notes = [*bundle.notes]
    temporary_simplifications: list[str] = []
    next_steps = _next_steps_for_source_mode(source_mode)
    active_split_config = split_config or loaded.bundle.splits
    active_capacity_config = capacity_config or loaded.bundle.capacity
    active_universe_config = universe_config or loaded.bundle.universe
    active_cost_scenarios = cost_scenarios or loaded.bundle.costs.scenarios

    artifacts: list[StageArtifact] = []
    artifacts.append(
        _persist_frame(paths.root, dataset_dir / "security_master.parquet", "security_master", bundle.security_master)
    )
    artifacts.append(
        _persist_frame(paths.root, dataset_dir / "silver_market_pit.parquet", "silver_market", bundle.silver_market)
    )
    artifacts.append(
        _persist_frame(paths.root, dataset_dir / "silver_fundamentals_pit.parquet", "silver_fundamentals", bundle.silver_fundamentals)
    )

    preliminary_universe = build_universe_snapshots(
        bundle.security_master,
        bundle.silver_market,
        active_universe_config,
    )
    feature_first = build_feature_panel(
        bundle.silver_market,
        bundle.silver_fundamentals,
        bundle.security_master,
        preliminary_universe.snapshot,
        bundle.benchmark_market,
        bundle.calendar,
        interaction_cap=loaded.bundle.features.interaction_cap,
        root=str(paths.root),
    )
    universe = build_universe_snapshots(
        bundle.security_master,
        bundle.silver_market,
        active_universe_config,
        feature_coverage=feature_first.feature_coverage,
    )
    features = build_feature_panel(
        bundle.silver_market,
        bundle.silver_fundamentals,
        bundle.security_master,
        universe.snapshot,
        bundle.benchmark_market,
        bundle.calendar,
        interaction_cap=loaded.bundle.features.interaction_cap,
        root=str(paths.root),
    )
    assert_no_future_feature_timestamps(features.panel)
    labels = build_label_panel(
        features.panel[["date", "security_id", "sector", "beta_estimate"]].copy(),
        bundle.silver_market,
        bundle.benchmark_market,
        bundle.calendar,
        loaded.bundle.labels,
    )
    gold = build_gold_panel(
        features.panel,
        labels.panel,
        dataset_version=experiment.dataset_version,
        primary_label=experiment.label,
        root=paths.root,
        parquet_path=dataset_dir / "gold_panel.parquet",
        persist=False,
        feature_vector_version=loaded.bundle.features.feature_registry_version,
        label_family_version="v1",
    )

    feature_panel_artifact = features.panel[
        [
            "date",
            "security_id",
            "symbol",
            "sector",
            "industry",
            "is_in_universe",
            "liquidity_bucket",
            "beta_estimate",
            "feature_coverage_ratio",
            *features.feature_columns,
        ]
    ].copy()
    label_columns = [column for column in labels.panel.columns if column.startswith("label_")]
    label_panel_artifact = labels.panel[["date", "security_id", "sector", "beta_estimate", *label_columns]].copy()

    artifacts.append(
        _persist_frame(paths.root, dataset_dir / "universe_snapshot.parquet", "universe_snapshot", universe.snapshot)
    )
    artifacts.append(
        _persist_frame(paths.root, dataset_dir / "feature_panel.parquet", "feature_panel", feature_panel_artifact)
    )
    artifacts.append(
        _persist_frame(paths.root, dataset_dir / "label_panel.parquet", "label_panel", label_panel_artifact)
    )
    artifacts.append(
        _persist_json_artifact(paths.root, manifests_dir / "dataset_manifest.json", "dataset_manifest", gold.manifest.__dict__)
    )
    artifacts.append(
        _persist_json_artifact(paths.root, diagnostics_dir / "label_overlap_report.json", "label_overlap_report", labels.overlap_report)
    )
    artifacts.append(
        _persist_frame(paths.root, diagnostics_dir / "label_sanity_report.parquet", "label_sanity_report", labels.sanity_report)
    )

    primary_horizon_days = int(experiment.label.split("_")[2].replace("d", ""))
    splits = generate_walk_forward_splits(
        gold.panel,
        active_split_config,
        bundle.calendar,
        primary_horizon_days=primary_horizon_days,
    )
    fold_metadata_path = persist_fold_metadata(splits, manifests_dir / "fold_metadata.json")
    artifacts.append(
        StageArtifact(
            name="fold_metadata",
            path=str(fold_metadata_path.relative_to(paths.root)),
            row_count=int(len(splits.metadata)),
            format="json",
        )
    )

    feature_columns = _resolve_feature_columns(features, experiment, paths.root)
    gold_artifact_columns = [
        "date",
        "security_id",
        "symbol",
        "sector",
        "industry",
        "liquidity_bucket",
        "beta_estimate",
        "is_in_universe",
        "feature_coverage_ratio",
        "row_valid_flag",
        "row_drop_reason",
        experiment.label,
        *feature_columns,
    ]
    gold_artifact = gold.panel.loc[:, list(dict.fromkeys(column for column in gold_artifact_columns if column in gold.panel.columns))].copy()
    write_parquet(gold_artifact, gold.parquet_path)
    artifacts.append(
        StageArtifact(
            name="gold_panel",
            path=str(gold.parquet_path.relative_to(paths.root)),
            row_count=int(len(gold_artifact)),
            format="parquet",
        )
    )
    model_specs = _build_model_specs(experiment, loaded.bundle.project.default_random_seed, paths)
    preprocessing_spec = _resolve_preprocessing_spec(loaded, experiment)
    oof = generate_oof_predictions(
        gold.panel,
        splits.folds,
        model_specs=model_specs,
        feature_columns=feature_columns,
        label_column=experiment.label,
        dataset_version=experiment.dataset_version,
        config_hash=loaded.config_hash,
        preprocessing_spec=preprocessing_spec,
        evaluation_protocol=loaded.bundle.runtime.evaluation_protocol,
    )
    artifacts.append(
        _persist_frame(paths.root, dataset_dir / "oof_predictions.parquet", "oof_predictions", oof.predictions)
    )
    artifacts.append(
        _persist_frame(paths.root, diagnostics_dir / "oof_coverage_by_fold.parquet", "oof_coverage_by_fold", oof.coverage_by_fold)
    )
    artifacts.append(
        _persist_frame(paths.root, diagnostics_dir / "tuning_diagnostics.parquet", "tuning_diagnostics", oof.tuning_diagnostics)
    )
    artifacts.append(
        _persist_frame(paths.root, diagnostics_dir / "evaluation_data_usage_trace.parquet", "evaluation_data_usage_trace", oof.data_usage_trace)
    )
    artifacts.append(
        _persist_json_artifact(paths.root, manifests_dir / "oof_manifest.json", "oof_manifest", oof.manifest)
    )
    evaluation_manifest = {
        "evaluation_protocol": loaded.bundle.runtime.evaluation_protocol,
        "fold_count": int(len(splits.folds)),
        "data_usage_trace_path": str((diagnostics_dir / "evaluation_data_usage_trace.parquet").relative_to(paths.root)),
        "oof_manifest_path": str((manifests_dir / "oof_manifest.json").relative_to(paths.root)),
        "split_protocol": splits.protocol.to_dict(),
        "oof_purity_checks": oof.manifest["oof_purity_checks"],
    }
    artifacts.append(
        _persist_json_artifact(paths.root, manifests_dir / "evaluation_manifest.json", "evaluation_manifest", evaluation_manifest)
    )
    if not oof.tuning_diagnostics.empty:
        for model_name, tuning_frame in oof.tuning_diagnostics.groupby("model_name", sort=False):
            candidate_columns = [column for column in ("n_estimators", "learning_rate", "max_bins", "min_leaf_size") if column in tuning_frame.columns]
            if not candidate_columns:
                continue
            ranked = tuning_frame.sort_values("validation_rank_ic_mean", ascending=False, kind="stable").reset_index(drop=True)
            if ranked.empty:
                continue
            best_row = ranked.iloc[0]
            best_params = {column: best_row[column] for column in candidate_columns}
            registry_payload = {
                "model_name": model_name,
                "best_params": best_params,
                "best_validation_rank_ic_mean": best_row.get("validation_rank_ic_mean"),
                "updated_from_run_id": run_id,
            }
            registry_path = write_json(registry_payload, _model_params_registry_path(paths, str(model_name)))
            artifacts.append(
                StageArtifact(
                    name=f"{model_name}_best_params",
                    path=str(registry_path.relative_to(paths.root)),
                    format="json",
                )
            )

    primary_model_name = model_specs[0].name
    primary_predictions = oof.predictions.loc[oof.predictions["model_name"] == primary_model_name].copy()
    backtest = run_backtest(
        primary_predictions,
        universe.snapshot,
        features.panel,
        bundle.silver_market,
        loaded.bundle.portfolio,
        loaded.bundle.costs,
        bundle.calendar,
        model_name=primary_model_name,
        scenario=experiment.cost_scenario,
    )
    artifacts.append(
        _persist_frame(paths.root, dataset_dir / "portfolio_daily_state.parquet", "portfolio_daily_state", backtest.daily_state)
    )
    artifacts.append(
        _persist_frame(paths.root, dataset_dir / "holdings_snapshots.parquet", "holdings_snapshots", backtest.holdings_snapshots)
    )
    artifacts.append(
        _persist_frame(paths.root, dataset_dir / "trades.parquet", "trades", backtest.trades)
    )
    artifacts.append(
        _persist_frame(paths.root, dataset_dir / "daily_returns.parquet", "daily_returns", backtest.daily_returns)
    )
    backtest_manifest = {
        "row_count_daily_state": int(len(backtest.daily_state)),
        "row_count_trades": int(len(backtest.trades)),
        "row_count_holdings": int(len(backtest.holdings_snapshots)),
        "primary_model_name": primary_model_name,
        "scenario": experiment.cost_scenario,
    }
    artifacts.append(
        _persist_json_artifact(paths.root, manifests_dir / "backtest_manifest.json", "backtest_manifest", backtest_manifest)
    )

    cost_sensitivity_rows: list[dict[str, object]] = []
    for scenario in active_cost_scenarios:
        scenario_backtest = run_backtest(
            primary_predictions,
            universe.snapshot,
            features.panel,
            bundle.silver_market,
            loaded.bundle.portfolio,
            loaded.bundle.costs,
            bundle.calendar,
            model_name=primary_model_name,
            scenario=scenario,
        )
        summary = compute_portfolio_metrics(scenario_backtest.daily_state).set_index("metric")["value"].to_dict()
        final_aum = float(scenario_backtest.daily_state["aum"].iloc[-1]) if not scenario_backtest.daily_state.empty else None
        cost_sensitivity_rows.append(
            {
                "scenario": scenario,
                "net_sharpe": summary.get("net_sharpe"),
                "max_drawdown": summary.get("max_drawdown"),
                "final_aum": final_aum,
            }
        )
    cost_sensitivity = pd.DataFrame(cost_sensitivity_rows)
    artifacts.append(
        _persist_frame(paths.root, diagnostics_dir / "cost_sensitivity.parquet", "cost_sensitivity", cost_sensitivity)
    )

    capacity = run_capacity_analysis(
        primary_predictions,
        universe.snapshot,
        features.panel,
        bundle.silver_market,
        loaded.bundle.portfolio,
        loaded.bundle.costs,
        active_capacity_config,
        bundle.calendar,
        model_name=primary_model_name,
    )
    artifacts.append(
        _persist_frame(paths.root, dataset_dir / "capacity_results.parquet", "capacity_results", capacity.results)
    )
    artifacts.append(
        _persist_frame(paths.root, diagnostics_dir / "capacity_diagnostics.parquet", "capacity_diagnostics", capacity.diagnostics)
    )
    artifacts.append(
        _persist_json_artifact(
            paths.root,
            manifests_dir / "capacity_manifest.json",
            "capacity_manifest",
            {"row_count": int(len(capacity.results)), "scenarios": sorted(capacity.results["scenario"].dropna().unique().tolist())},
        )
    )

    predictive_by_model: list[dict[str, object]] = []
    for model_name in sorted(oof.predictions["model_name"].dropna().unique()):
        metrics = compute_predictive_metrics(
            oof.predictions.loc[oof.predictions["model_name"] == model_name],
            gold.panel[["date", "security_id", experiment.label]],
            label_column=experiment.label,
        )
        summary = metrics.loc[metrics["metric"].notna(), ["metric", "value"]].copy()
        summary["model_name"] = model_name
        predictive_by_model.extend(summary.to_dict(orient="records"))
    predictive_metrics = pd.DataFrame(predictive_by_model)
    portfolio_metrics = compute_portfolio_metrics(backtest.daily_state)
    regime_frame = _regime_frame(
        primary_predictions,
        gold.panel[["date", "security_id", experiment.label]],
        bundle.benchmark_market,
        experiment.label,
    )
    regime_metrics = compute_regime_breakdown(
        regime_frame,
        prediction_column="raw_prediction",
        label_column=experiment.label,
        regime_column="benchmark_regime",
    )
    decay_curve = build_decay_response_curve(
        gold.panel.merge(
            primary_predictions[["date", "security_id", "raw_prediction"]],
            on=["date", "security_id"],
            how="inner",
        ),
        prediction_column="raw_prediction",
        label_columns=[column for column in gold.panel.columns if column.startswith("label_excess_") and column.endswith("_oo")],
    )
    primary_model_spec = model_specs[0]
    ablation_model_spec = ModelRunSpec(
        name=primary_model_spec.name,
        alpha_grid=primary_model_spec.alpha_grid,
        n_trials=primary_model_spec.n_trials,
        params=_best_tuned_params(oof.tuning_diagnostics, primary_model_name) or dict(primary_model_spec.params),
        seed=primary_model_spec.seed,
    )
    ablation = run_ablation_suite(
        panel=gold.panel,
        folds=splits.folds,
        model_spec=ablation_model_spec,
        feature_columns=feature_columns,
        label_column=experiment.label,
        dataset_version=experiment.dataset_version,
        config_hash=loaded.config_hash,
        preprocessing_spec=preprocessing_spec,
        universe_snapshot=universe.snapshot,
        feature_panel=features.panel,
        silver_market=bundle.silver_market,
        portfolio_config=loaded.bundle.portfolio,
        costs_config=loaded.bundle.costs,
        calendar=bundle.calendar,
        scenario=experiment.cost_scenario,
        root=str(paths.root),
        max_feature_family_scenarios=ablation_max_feature_family_scenarios,
        max_preprocessing_scenarios=ablation_max_preprocessing_scenarios,
    )
    artifacts.append(
        _persist_frame(paths.root, diagnostics_dir / "predictive_metrics.parquet", "predictive_metrics", predictive_metrics)
    )
    artifacts.append(
        _persist_frame(paths.root, diagnostics_dir / "portfolio_metrics.parquet", "portfolio_metrics", portfolio_metrics)
    )
    artifacts.append(
        _persist_frame(paths.root, diagnostics_dir / "regime_metrics.parquet", "regime_metrics", regime_metrics)
    )
    artifacts.append(
        _persist_frame(paths.root, diagnostics_dir / "decay_curve.parquet", "decay_curve", decay_curve)
    )
    artifacts.append(
        _persist_frame(paths.root, diagnostics_dir / "ablation_results.parquet", "ablation_results", ablation.results)
    )

    model_comparison_rows = []
    for model_name, frame in predictive_metrics.groupby("model_name", sort=True):
        metrics_map = {row["metric"]: row["value"] for row in frame.to_dict(orient="records")}
        model_comparison_rows.append(
            {
                "metric": f"{model_name}.rank_ic_mean",
                "value": metrics_map.get("rank_ic_mean"),
            }
        )
    model_comparison = pd.DataFrame(model_comparison_rows)
    section_payloads = {
        "executive_summary": (
            f"Запуск `{run_id}` собрал датасет `{experiment.dataset_version}` на {len(gold.panel):,} строк, "
            f"с {len(feature_columns)} модельными фичами, {len(splits.folds)} purged walk-forward фолдами "
            f"и OOF-only бэктестом для `{primary_model_name}`."
        ),
        "time_semantics": "\n".join(
            [
                "- decision timestamp: после close_t",
                "- execution timestamp: open_{t+1}",
                "- labels выровнены относительно next-open execution semantics",
                "- PIT fundamentals джойнятся только при available_from <= decision timestamp",
            ]
        ),
        "data_lineage": "\n".join(
            [
                f"- run_id: {run_id}",
                f"- dataset_version: {experiment.dataset_version}",
                f"- config_hash: {loaded.config_hash}",
                f"- git_commit_hash: {capture_runtime_metadata(paths.root).git_commit_hash}",
                f"- source_mode: {source_mode}",
                f"- runtime_class: {capability.runtime_class}",
                f"- capability_class: {capability.capability_class}",
                f"- benchmark_mode: {'equal_weight_proxy_from_market_panel' if source_mode == 'configured_adapters' else 'synthetic_fixture_bundle'}",
            ]
        ),
        "feature_catalog": _feature_catalog_summary(feature_columns, paths.root),
        "validation_protocol": "\n".join([f"- fold_count: {len(splits.folds)}", f"- fold_metadata: {fold_metadata_path.relative_to(paths.root)}", splits.timeline_plot]),
        "evaluation_protocol": "\n".join(
            [
                f"- protocol: {loaded.bundle.runtime.evaluation_protocol}",
                "- preprocessing_fit_scope: train_only",
                "- tuning_scope: valid_only",
                f"- final_fit_scope: {'train_plus_valid' if loaded.bundle.runtime.evaluation_protocol == 'train_valid_refit_then_test' else 'train_only'}",
                "- predict_scope: test_only",
            ]
        ),
        "model_comparison": "\n".join(_summary_lines_from_metrics(model_comparison)),
        "backtest_results": "\n".join(
            [
                f"- primary_model: {primary_model_name}",
                *_summary_lines_from_metrics(portfolio_metrics),
                f"- final_aum: {float(backtest.daily_state['aum'].iloc[-1]) if not backtest.daily_state.empty else None}",
            ]
        ),
        "cost_sensitivity": "\n".join(_summary_lines_from_metrics(cost_sensitivity, value_column="net_sharpe")),
        "capacity_analysis": "\n".join(
            [
                f"- tested_aum_levels: {capacity.results['aum_level'].nunique()}",
                f"- capacity_rows: {len(capacity.results)}",
                f"- max_net_sharpe: {capacity.results['net_sharpe'].max()}",
            ]
        ),
        "regime_analysis": "\n".join(_summary_lines_from_metrics(regime_metrics, value_column="ic")),
        "decay_analysis": "\n".join(
            [
                f"- horizons: {sorted(decay_curve['horizon_days'].dropna().unique().tolist())}",
                f"- rows: {len(decay_curve)}",
            ]
        ),
        "ablation_analysis": "\n".join(_ablation_summary_lines(ablation.results)),
    }
    report_text = render_final_report(
        loaded.bundle.reporting,
        project_name=loaded.bundle.project.project_name,
        section_payloads=section_payloads,
        limitations=[
            *notes,
        ],
        next_steps=next_steps,
    )
    rendered_sections = render_report_sections(
        loaded.bundle.reporting,
        section_payloads=section_payloads,
        limitations=[
            *notes,
        ],
        next_steps=next_steps,
    )
    report_path = report_dir / "final_report.md"
    report_path.write_text(report_text, encoding="utf-8")
    artifacts.append(
        StageArtifact(name="final_report", path=str(report_path.relative_to(paths.root)), format="markdown")
    )
    section_artifacts: list[ReportSectionArtifact] = []
    section_index_payload: dict[str, dict[str, str | int]] = {}
    for index, section in enumerate(rendered_sections, start=1):
        section_path = report_sections_dir / f"{index:02d}_{section.key}.md"
        section_body = f"## {section.title}\n\n{section.body}\n"
        section_path.write_text(section_body, encoding="utf-8")
        relative_path = str(section_path.relative_to(paths.root))
        section_artifacts.append(
            ReportSectionArtifact(
                section_key=section.key,
                title=section.title,
                path=relative_path,
                line_count=len(section_body.splitlines()),
            )
        )
        section_index_payload[section.key] = {"title": section.title, "path": relative_path, "line_count": len(section_body.splitlines())}

    section_index_path = write_json(section_index_payload, manifests_dir / "report_sections.json")
    artifacts.append(
        StageArtifact(
            name="report_sections_index",
            path=str(section_index_path.relative_to(paths.root)),
            row_count=len(section_artifacts),
            format="json",
        )
    )

    generated_formats = ["markdown"]
    pending_formats: list[str] = []
    report_html_path: Path | None = None
    if "html" in loaded.bundle.reporting.formats:
        report_html = render_final_report_html(
            loaded.bundle.reporting,
            project_name=loaded.bundle.project.project_name,
            section_payloads=section_payloads,
            limitations=[
                *notes,
            ],
            next_steps=next_steps,
        )
        report_html_path = report_dir / "final_report.html"
        report_html_path.write_text(report_html, encoding="utf-8")
        generated_formats.append("html")
        artifacts.append(
            StageArtifact(name="final_report_html", path=str(report_html_path.relative_to(paths.root)), format="html")
        )
    for fmt in loaded.bundle.reporting.formats:
        if fmt not in generated_formats:
            pending_formats.append(fmt)
    if pending_formats and loaded.bundle.runtime.policy.release_requires_zero_pending_outputs:
        raise IncompleteOperationalOutputs(
            "Reporting path не собрал все requested formats: "
            f"{', '.join(pending_formats)}."
        )

    rendered_figures = render_mandatory_figures(
        report_dir / "figures",
        requested_figures=list(loaded.bundle.reporting.mandatory_figures),
        universe_snapshot=universe.snapshot,
        feature_panel=features.panel,
        predictions=primary_predictions,
        labels=gold.panel[["date", "security_id", experiment.label]],
        backtest_daily_state=backtest.daily_state,
        capacity_results=capacity.results,
        decay_curve=decay_curve,
    )
    figure_artifacts = [
        ReportFigureArtifact(
            figure_name=figure.figure_name,
            status="generated",
            path=str(figure.path.relative_to(paths.root)),
            notes=figure.notes,
        )
        for figure in rendered_figures
    ]
    for figure in figure_artifacts:
        artifacts.append(
            StageArtifact(name=f"figure::{figure.figure_name}", path=str(figure.path), format="svg")
        )
    report_bundle = ReportBundle(
        project_name=loaded.bundle.project.project_name,
        report_path=str(report_path.relative_to(paths.root)),
        report_html_path=None if report_html_path is None else str(report_html_path.relative_to(paths.root)),
        section_index_path=str(section_index_path.relative_to(paths.root)),
        section_artifacts=section_artifacts,
        figure_artifacts=figure_artifacts,
        requested_formats=list(loaded.bundle.reporting.formats),
        generated_formats=generated_formats,
        pending_formats=pending_formats,
    )
    report_bundle_path = write_model_document(report_bundle, manifests_dir / "report_bundle.json")
    artifacts.append(
        StageArtifact(name="report_bundle", path=str(report_bundle_path.relative_to(paths.root)), format="json")
    )

    if temporary_simplifications and not loaded.bundle.runtime.policy.allow_temporary_simplifications:
        raise TemporarySimplificationViolation(
            "Strict operational policy запрещает completed-run с временными упрощениями: "
            f"{temporary_simplifications}"
        )

    release_eligible = _release_eligibility(
        capability,
        pending_formats=pending_formats,
        temporary_simplifications=temporary_simplifications,
    )
    completed_at = _now_utc()
    manifest = PipelineRunManifest(
        run_id=run_id,
        command=command_name,
        status="completed" if release_eligible else "completed_fixture_only",
        dataset_version=experiment.dataset_version,
        config_hash=loaded.config_hash,
        runtime_metadata=runtime_metadata,
        started_at_utc=_isoformat(started_at),
        completed_at_utc=_isoformat(completed_at),
        artifacts=artifacts,
        notes=notes,
        runtime_class=capability.runtime_class,
        capability_class=capability.capability_class,
        release_eligible=release_eligible,
    )
    manifest_path = write_model_document(manifest, manifests_dir / "pipeline_run_manifest.json")

    review_bundle = ReviewBundle(
        run_id=run_id,
        manifest_path=str(manifest_path.relative_to(paths.root)),
        report_path=str(report_path.relative_to(paths.root)),
        report_html_path=None if report_html_path is None else str(report_html_path.relative_to(paths.root)),
        report_bundle_path=str(report_bundle_path.relative_to(paths.root)),
        release_checklist_path="docs/release_checklist.md",
        required_manifests={
            "dataset_manifest": str((manifests_dir / "dataset_manifest.json").relative_to(paths.root)),
            "oof_manifest": str((manifests_dir / "oof_manifest.json").relative_to(paths.root)),
            "evaluation_manifest": str((manifests_dir / "evaluation_manifest.json").relative_to(paths.root)),
            "backtest_manifest": str((manifests_dir / "backtest_manifest.json").relative_to(paths.root)),
            "capacity_manifest": str((manifests_dir / "capacity_manifest.json").relative_to(paths.root)),
            "pipeline_run_manifest": str(manifest_path.relative_to(paths.root)),
        },
        required_reports={
            "final_report": str(report_path.relative_to(paths.root)),
            "final_report_html": None if report_html_path is None else str(report_html_path.relative_to(paths.root)),
            "fold_metadata": str(fold_metadata_path.relative_to(paths.root)),
            "report_bundle": str(report_bundle_path.relative_to(paths.root)),
            "report_sections_index": str(section_index_path.relative_to(paths.root)),
        },
        report_section_paths={artifact.section_key: artifact.path for artifact in section_artifacts},
        key_metrics={
            "dataset_row_count": int(len(gold.panel)),
            "feature_count": int(len(feature_columns)),
            "fold_count": int(len(splits.folds)),
            "primary_model_name": primary_model_name,
            "net_sharpe": portfolio_metrics.set_index("metric")["value"].to_dict().get("net_sharpe"),
            "max_drawdown": portfolio_metrics.set_index("metric")["value"].to_dict().get("max_drawdown"),
            "ablation_rows": int(len(ablation.results)),
        },
        pending_outputs=pending_formats,
        temporary_simplifications=temporary_simplifications,
        runtime_class=capability.runtime_class,
        capability_class=capability.capability_class,
        release_eligible=release_eligible,
    )
    review_bundle_path = write_model_document(review_bundle, manifests_dir / "review_bundle.json")

    primary_artifact_name = PRIMARY_ARTIFACT_BY_COMMAND[command_name]
    primary_artifact_path = next(
        artifact.path for artifact in artifacts if artifact.name == primary_artifact_name
    )
    return OperationalRunResult(
        run_id=run_id,
        manifest_path=manifest_path,
        report_path=report_path,
        review_bundle_path=review_bundle_path,
        primary_artifact_path=paths.root / primary_artifact_path,
        command=command_name,
        dataset_version=experiment.dataset_version,
        capability_class=capability.capability_class,
        release_eligible=release_eligible,
        notes=notes,
    )
