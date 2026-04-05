from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from alpha_research.backtest.engine import run_backtest
from alpha_research.config.models import CostsConfig, PortfolioConfig
from alpha_research.evaluation.metrics import compute_portfolio_metrics, compute_predictive_metrics
from alpha_research.features.registry import load_feature_registry
from alpha_research.preprocessing.transforms import PreprocessingSpec
from alpha_research.time.calendar import ExchangeCalendarAdapter
from alpha_research.training.oof import ModelRunSpec, generate_oof_predictions
from alpha_research.splits.engine import FoldDefinition


@dataclass(frozen=True)
class AblationRunResult:
    results: pd.DataFrame


def _summary_metric_map(metrics: pd.DataFrame) -> dict[str, float | None]:
    summary = metrics.loc[metrics["metric"].notna(), ["metric", "value"]].copy()
    return summary.set_index("metric")["value"].to_dict()


def _feature_family_scenarios(feature_columns: list[str], root: str) -> list[tuple[str, list[str]]]:
    registry = load_feature_registry(root)
    family_map: dict[str, list[str]] = {}
    for column in feature_columns:
        if column not in registry:
            continue
        family_map.setdefault(registry[column].family, []).append(column)

    scenarios: list[tuple[str, list[str]]] = [("baseline_all_features", list(feature_columns))]
    for family_name, family_columns in sorted(family_map.items()):
        active = [column for column in feature_columns if column not in set(family_columns)]
        if active:
            scenarios.append((f"drop_family::{family_name}", active))
    return scenarios


def _preprocessing_scenarios(base: PreprocessingSpec) -> list[tuple[str, PreprocessingSpec]]:
    scenarios = [
        ("baseline_current", base),
        (
            "no_winsor",
            PreprocessingSpec(
                winsor_lower=None,
                winsor_upper=None,
                scaler=base.scaler,
                neutralizer=base.neutralizer,
            ),
        ),
        (
            "neutralizer_none",
            PreprocessingSpec(
                winsor_lower=base.winsor_lower,
                winsor_upper=base.winsor_upper,
                scaler=base.scaler,
                neutralizer=None,
            ),
        ),
        (
            "scaler_zscore_by_date",
            PreprocessingSpec(
                winsor_lower=base.winsor_lower,
                winsor_upper=base.winsor_upper,
                scaler="zscore_by_date",
                neutralizer=base.neutralizer,
            ),
        ),
        (
            "scaler_robust_zscore_by_date",
            PreprocessingSpec(
                winsor_lower=base.winsor_lower,
                winsor_upper=base.winsor_upper,
                scaler="robust_zscore_by_date",
                neutralizer=base.neutralizer,
            ),
        ),
        (
            "scaler_percentile_rank_by_date",
            PreprocessingSpec(
                winsor_lower=base.winsor_lower,
                winsor_upper=base.winsor_upper,
                scaler="percentile_rank_by_date",
                neutralizer=base.neutralizer,
            ),
        ),
    ]

    deduplicated: list[tuple[str, PreprocessingSpec]] = []
    seen: set[tuple[float | None, float | None, str | None, str | None]] = set()
    for scenario_name, spec in scenarios:
        key = (spec.winsor_lower, spec.winsor_upper, spec.scaler, spec.neutralizer)
        if key in seen:
            continue
        deduplicated.append((scenario_name, spec))
        seen.add(key)
    return deduplicated


def _evaluate_scenario(
    *,
    scenario_group: str,
    scenario_name: str,
    panel: pd.DataFrame,
    folds: list[FoldDefinition],
    model_spec: ModelRunSpec,
    feature_columns: list[str],
    label_column: str,
    dataset_version: str,
    config_hash: str,
    preprocessing_spec: PreprocessingSpec,
    universe_snapshot: pd.DataFrame,
    feature_panel: pd.DataFrame,
    silver_market: pd.DataFrame,
    portfolio_config: PortfolioConfig,
    costs_config: CostsConfig,
    calendar: ExchangeCalendarAdapter,
    scenario: str,
) -> dict[str, object]:
    oof = generate_oof_predictions(
        panel,
        folds,
        model_specs=[model_spec],
        feature_columns=feature_columns,
        label_column=label_column,
        dataset_version=dataset_version,
        config_hash=config_hash,
        preprocessing_spec=preprocessing_spec,
    )
    predictions = oof.predictions.loc[oof.predictions["model_name"] == model_spec.name].copy()
    predictive_summary = _summary_metric_map(
        compute_predictive_metrics(
            predictions,
            panel[["date", "security_id", label_column]],
            label_column=label_column,
        )
    )
    backtest = run_backtest(
        predictions,
        universe_snapshot,
        feature_panel,
        silver_market,
        portfolio_config,
        costs_config,
        calendar,
        model_name=model_spec.name,
        scenario=scenario,
    )
    portfolio_summary = _summary_metric_map(compute_portfolio_metrics(backtest.daily_state))
    return {
        "scenario_group": scenario_group,
        "scenario_name": scenario_name,
        "model_name": model_spec.name,
        "feature_count": int(len(feature_columns)),
        "row_count_oof": int(len(predictions)),
        "rank_ic_mean": predictive_summary.get("rank_ic_mean"),
        "ic_mean": predictive_summary.get("ic_mean"),
        "net_sharpe": portfolio_summary.get("net_sharpe"),
        "max_drawdown": portfolio_summary.get("max_drawdown"),
        "winsor_lower": preprocessing_spec.winsor_lower,
        "winsor_upper": preprocessing_spec.winsor_upper,
        "scaler": preprocessing_spec.scaler or "none",
        "neutralizer": preprocessing_spec.neutralizer or "none",
    }


def _add_relative_deltas(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    output["delta_rank_ic_mean"] = pd.NA
    output["delta_net_sharpe"] = pd.NA
    for scenario_group, group in output.groupby("scenario_group", sort=False):
        baseline = group.iloc[0]
        baseline_rank_ic = pd.to_numeric(pd.Series([baseline.get("rank_ic_mean")]), errors="coerce").iloc[0]
        baseline_sharpe = pd.to_numeric(pd.Series([baseline.get("net_sharpe")]), errors="coerce").iloc[0]
        idx = output["scenario_group"] == scenario_group
        if pd.notna(baseline_rank_ic):
            output.loc[idx, "delta_rank_ic_mean"] = pd.to_numeric(output.loc[idx, "rank_ic_mean"], errors="coerce") - float(baseline_rank_ic)
        if pd.notna(baseline_sharpe):
            output.loc[idx, "delta_net_sharpe"] = pd.to_numeric(output.loc[idx, "net_sharpe"], errors="coerce") - float(baseline_sharpe)
    return output


def run_ablation_suite(
    *,
    panel: pd.DataFrame,
    folds: list[FoldDefinition],
    model_spec: ModelRunSpec,
    feature_columns: list[str],
    label_column: str,
    dataset_version: str,
    config_hash: str,
    preprocessing_spec: PreprocessingSpec,
    universe_snapshot: pd.DataFrame,
    feature_panel: pd.DataFrame,
    silver_market: pd.DataFrame,
    portfolio_config: PortfolioConfig,
    costs_config: CostsConfig,
    calendar: ExchangeCalendarAdapter,
    scenario: str,
    root: str,
    max_feature_family_scenarios: int | None = None,
    max_preprocessing_scenarios: int | None = None,
) -> AblationRunResult:
    rows: list[dict[str, object]] = []
    evaluation_cache: dict[tuple[tuple[str, ...], float | None, float | None, str | None, str | None], dict[str, object]] = {}

    feature_family_scenarios = _feature_family_scenarios(feature_columns, root)
    preprocessing_scenarios = _preprocessing_scenarios(preprocessing_spec)
    if max_feature_family_scenarios is not None:
        feature_family_scenarios = feature_family_scenarios[: max(max_feature_family_scenarios, 1)]
    if max_preprocessing_scenarios is not None:
        preprocessing_scenarios = preprocessing_scenarios[: max(max_preprocessing_scenarios, 1)]

    def _evaluate_cached(
        *,
        scenario_group: str,
        scenario_name: str,
        scenario_features: list[str],
        scenario_preprocessing: PreprocessingSpec,
    ) -> dict[str, object]:
        cache_key = (
            tuple(scenario_features),
            scenario_preprocessing.winsor_lower,
            scenario_preprocessing.winsor_upper,
            scenario_preprocessing.scaler,
            scenario_preprocessing.neutralizer,
        )
        if cache_key not in evaluation_cache:
            evaluation_cache[cache_key] = _evaluate_scenario(
                scenario_group=scenario_group,
                scenario_name=scenario_name,
                panel=panel,
                folds=folds,
                model_spec=model_spec,
                feature_columns=scenario_features,
                label_column=label_column,
                dataset_version=dataset_version,
                config_hash=config_hash,
                preprocessing_spec=scenario_preprocessing,
                universe_snapshot=universe_snapshot,
                feature_panel=feature_panel,
                silver_market=silver_market,
                portfolio_config=portfolio_config,
                costs_config=costs_config,
                calendar=calendar,
                scenario=scenario,
            )
        return {
            **evaluation_cache[cache_key],
            "scenario_group": scenario_group,
            "scenario_name": scenario_name,
        }

    for scenario_name, scenario_features in feature_family_scenarios:
        rows.append(
            _evaluate_cached(
                scenario_group="feature_family",
                scenario_name=scenario_name,
                scenario_features=scenario_features,
                scenario_preprocessing=preprocessing_spec,
            )
        )

    for scenario_name, scenario_preprocessing in preprocessing_scenarios:
        rows.append(
            _evaluate_cached(
                scenario_group="preprocessing",
                scenario_name=scenario_name,
                scenario_features=feature_columns,
                scenario_preprocessing=scenario_preprocessing,
            )
        )

    results = pd.DataFrame(rows).sort_values(["scenario_group", "scenario_name"], kind="stable").reset_index(drop=True)
    return AblationRunResult(results=_add_relative_deltas(results))
