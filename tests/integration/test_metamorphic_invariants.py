from __future__ import annotations

import pandas as pd

from alpha_research.config.models import SplitsConfig
from alpha_research.splits.engine import generate_walk_forward_splits
from alpha_research.training.oof import ModelRunSpec, generate_oof_predictions
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
        allow_small_fixture_splits=True,
    )


def test_split_generation_is_invariant_to_row_order() -> None:
    bundle = build_model_research_bundle()
    original = generate_walk_forward_splits(bundle.panel, _split_config(), bundle.calendar, primary_horizon_days=5)
    shuffled = generate_walk_forward_splits(
        bundle.panel.sample(frac=1.0, random_state=17).reset_index(drop=True),
        _split_config(),
        bundle.calendar,
        primary_horizon_days=5,
    )
    assert [fold.to_dict() for fold in original.folds] == [fold.to_dict() for fold in shuffled.folds]
    pd.testing.assert_frame_equal(original.role_matrix, shuffled.role_matrix)


def test_oof_predictions_are_deterministic_for_same_seed() -> None:
    bundle = build_model_research_bundle()
    folds = generate_walk_forward_splits(bundle.panel, _split_config(), bundle.calendar, primary_horizon_days=5).folds[:2]
    first = generate_oof_predictions(
        bundle.panel,
        folds,
        model_specs=[ModelRunSpec(name="gradient_boosting_ranker", n_trials=4, seed=11)],
        feature_columns=bundle.feature_columns,
        label_column=bundle.label_column,
        dataset_version="ds_same_seed",
        prediction_timestamp="2026-01-01T00:00:00Z",
    )
    second = generate_oof_predictions(
        bundle.panel,
        folds,
        model_specs=[ModelRunSpec(name="gradient_boosting_ranker", n_trials=4, seed=11)],
        feature_columns=bundle.feature_columns,
        label_column=bundle.label_column,
        dataset_version="ds_same_seed",
        prediction_timestamp="2026-01-01T00:00:00Z",
    )
    pd.testing.assert_frame_equal(
        first.predictions.sort_values(["date", "security_id", "model_name"], kind="stable").reset_index(drop=True),
        second.predictions.sort_values(["date", "security_id", "model_name"], kind="stable").reset_index(drop=True),
    )


def test_irrelevant_columns_do_not_change_predictions_when_feature_list_is_fixed() -> None:
    bundle = build_model_research_bundle()
    folds = generate_walk_forward_splits(bundle.panel, _split_config(), bundle.calendar, primary_horizon_days=5).folds[:1]
    baseline = generate_oof_predictions(
        bundle.panel,
        folds,
        model_specs=[ModelRunSpec(name="ridge_regression", alpha_grid=(0.1, 1.0), seed=5)],
        feature_columns=bundle.feature_columns,
        label_column=bundle.label_column,
        dataset_version="ds_irrelevant",
        prediction_timestamp="2026-01-01T00:00:00Z",
    )
    mutated = bundle.panel.copy()
    mutated["totally_irrelevant_noise"] = range(len(mutated))
    mutated = mutated[[*reversed(mutated.columns)]]
    candidate_columns = [column for column in bundle.feature_columns if column in mutated.columns]
    rerun = generate_oof_predictions(
        mutated,
        folds,
        model_specs=[ModelRunSpec(name="ridge_regression", alpha_grid=(0.1, 1.0), seed=5)],
        feature_columns=candidate_columns,
        label_column=bundle.label_column,
        dataset_version="ds_irrelevant",
        prediction_timestamp="2026-01-01T00:00:00Z",
    )
    pd.testing.assert_frame_equal(
        baseline.predictions.sort_values(["date", "security_id", "model_name"], kind="stable").reset_index(drop=True),
        rerun.predictions.sort_values(["date", "security_id", "model_name"], kind="stable").reset_index(drop=True),
    )
