from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd
import pytest

from alpha_research.models.baselines import (
    LassoRegressionModel,
    ModelArtifact,
    RidgeRegressionModel,
    deserialize_model,
)
from alpha_research.training.oof import ModelRunSpec, generate_oof_predictions
from alpha_research.splits.engine import generate_walk_forward_splits
from alpha_research.config.models import SplitsConfig
from tests.helpers.model_data import build_model_research_bundle


def _split_config() -> SplitsConfig:
    return SplitsConfig(
        train_years=1,
        validation_months=2,
        test_months=1,
        step_months=1,
        expanding_train=False,
        purge_days=5,
        embargo_days=5,
        nested_validation=True,
        min_train_observations=1,
        persist_fold_artifacts=True,
    )


@lru_cache(maxsize=1)
def _cached_bundle():
    return build_model_research_bundle()


@lru_cache(maxsize=1)
def _cached_folds():
    bundle = _cached_bundle()
    return generate_walk_forward_splits(bundle.panel, _split_config(), bundle.calendar, primary_horizon_days=5).folds


def _rank_ic_mean(predictions: pd.DataFrame, panel: pd.DataFrame, label_column: str) -> float:
    merged = predictions.merge(panel[["date", "security_id", label_column]], on=["date", "security_id"], how="left")
    scores = []
    for _, group in merged.groupby("date", sort=False):
        subset = group[["raw_prediction", label_column]].dropna()
        if len(subset) < 2:
            continue
        corr = subset["raw_prediction"].rank(method="average").corr(subset[label_column].rank(method="average"))
        if pd.notna(corr):
            scores.append(float(corr))
    return float(np.mean(scores)) if scores else float("nan")


def test_random_baseline_has_near_zero_predictive_skill_on_sanity_fixture() -> None:
    bundle = _cached_bundle()
    folds = _cached_folds()
    result = generate_oof_predictions(
        bundle.panel,
        folds,
        model_specs=[ModelRunSpec(name="random_score", seed=7)],
        feature_columns=bundle.feature_columns,
        label_column=bundle.label_column,
        dataset_version="ds_random",
    )
    metric = _rank_ic_mean(result.predictions, bundle.panel, bundle.label_column)
    assert abs(metric) < 0.15


def test_heuristic_baseline_runs_end_to_end() -> None:
    bundle = _cached_bundle()
    folds = _cached_folds()
    result = generate_oof_predictions(
        bundle.panel,
        folds,
        model_specs=[ModelRunSpec(name="heuristic_blend_score")],
        feature_columns=bundle.feature_columns,
        label_column=bundle.label_column,
        dataset_version="ds_heuristic",
    )
    assert not result.predictions.empty
    assert set(result.predictions["model_name"]) == {"heuristic_blend_score"}


def test_ridge_and_lasso_wrappers_are_serializable() -> None:
    bundle = _cached_bundle()
    train = bundle.panel.iloc[:200].copy()
    ridge = RidgeRegressionModel(alpha=0.5).fit(train, bundle.feature_columns, bundle.label_column)
    lasso = LassoRegressionModel(alpha=0.01).fit(train, bundle.feature_columns, bundle.label_column)

    ridge_loaded = deserialize_model(ridge.to_artifact())
    lasso_loaded = deserialize_model(lasso.to_artifact())
    sample = train.iloc[:20].copy()
    np.testing.assert_allclose(ridge.predict(sample), ridge_loaded.predict(sample))
    np.testing.assert_allclose(lasso.predict(sample), lasso_loaded.predict(sample))


def test_tuning_engine_does_not_touch_test_fold() -> None:
    bundle = _cached_bundle()
    folds = _cached_folds()
    original = generate_oof_predictions(
        bundle.panel,
        folds[:1],
        model_specs=[ModelRunSpec(name="ridge_regression", alpha_grid=(0.01, 0.1, 1.0))],
        feature_columns=bundle.feature_columns,
        label_column=bundle.label_column,
        dataset_version="ds_tune",
        prediction_timestamp="2026-01-01T00:00:00Z",
    )

    mutated_panel = bundle.panel.copy()
    test_dates = list(folds[0].test_dates)
    mutated_panel.loc[mutated_panel["date"].isin(test_dates), bundle.label_column] = 999.0
    mutated = generate_oof_predictions(
        mutated_panel,
        folds[:1],
        model_specs=[ModelRunSpec(name="ridge_regression", alpha_grid=(0.01, 0.1, 1.0))],
        feature_columns=bundle.feature_columns,
        label_column=bundle.label_column,
        dataset_version="ds_tune",
        prediction_timestamp="2026-01-01T00:00:00Z",
    )
    pd.testing.assert_frame_equal(original.predictions, mutated.predictions)


def test_oof_prediction_store_is_unique_by_date_security_model() -> None:
    bundle = _cached_bundle()
    folds = _cached_folds()
    result = generate_oof_predictions(
        bundle.panel,
        folds[:2],
        model_specs=[ModelRunSpec(name="random_score", seed=11), ModelRunSpec(name="heuristic_momentum_score")],
        feature_columns=bundle.feature_columns,
        label_column=bundle.label_column,
        dataset_version="ds_oof",
    )
    assert not result.predictions.duplicated(subset=["date", "security_id", "model_name"]).any()


def test_prediction_manifests_contain_coverage_by_fold() -> None:
    bundle = _cached_bundle()
    folds = _cached_folds()
    result = generate_oof_predictions(
        bundle.panel,
        folds[:2],
        model_specs=[ModelRunSpec(name="heuristic_reversal_score")],
        feature_columns=bundle.feature_columns,
        label_column=bundle.label_column,
        dataset_version="ds_manifest",
    )
    assert result.manifest["coverage_by_fold"]
    assert set(result.coverage_by_fold.columns) >= {"fold_id", "model_name", "row_count", "unique_dates"}
    assert result.manifest["evaluation_protocol"] == "train_valid_refit_then_test"
    assert result.manifest["oof_purity_checks"]["unique_prediction_rows"] is True
    assert not result.data_usage_trace.empty
    assert set(result.data_usage_trace.columns) >= {"fold_id", "model_name", "preprocessing_fit_scope", "final_fit_scope", "predict_scope"}


def test_gradient_boosting_ranker_runs_in_oof_path_with_tuning() -> None:
    bundle = _cached_bundle()
    folds = _cached_folds()
    result = generate_oof_predictions(
        bundle.panel,
        folds[:2],
        model_specs=[ModelRunSpec(name="gradient_boosting_ranker", n_trials=8, seed=17)],
        feature_columns=bundle.feature_columns,
        label_column=bundle.label_column,
        dataset_version="ds_gbm_ranker",
    )
    metric = _rank_ic_mean(result.predictions, bundle.panel, bundle.label_column)
    assert not result.predictions.empty
    assert set(result.predictions["model_name"]) == {"gradient_boosting_ranker"}
    assert not result.tuning_diagnostics.empty
    assert metric > 0.15


def test_pure_train_only_protocol_is_explicit_in_data_usage_trace() -> None:
    bundle = _cached_bundle()
    folds = _cached_folds()
    result = generate_oof_predictions(
        bundle.panel,
        folds[:1],
        model_specs=[ModelRunSpec(name="ridge_regression", alpha_grid=(0.1, 1.0))],
        feature_columns=bundle.feature_columns,
        label_column=bundle.label_column,
        dataset_version="ds_protocol",
        evaluation_protocol="pure_train_only_then_test",
    )
    assert result.manifest["evaluation_protocol"] == "pure_train_only_then_test"
    assert set(result.data_usage_trace["final_fit_scope"]) == {"train_only"}
