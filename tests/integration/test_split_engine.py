from __future__ import annotations

import pandas as pd
import pytest

from alpha_research.common.io import read_json
from alpha_research.config.models import SplitsConfig
from alpha_research.splits.engine import generate_walk_forward_splits, persist_fold_metadata
from tests.helpers.model_data import build_model_research_bundle


def _split_config(*, expanding_train: bool = False) -> SplitsConfig:
    return SplitsConfig(
        train_years=1,
        validation_months=2,
        test_months=1,
        step_months=1,
        expanding_train=expanding_train,
        purge_days=5,
        embargo_days=5,
        nested_validation=True,
        min_train_observations=1,
        persist_fold_artifacts=True,
    )


def test_rolling_split_generator_creates_non_overlapping_train_valid_test() -> None:
    bundle = build_model_research_bundle()
    artifacts = generate_walk_forward_splits(bundle.panel, _split_config(), bundle.calendar, primary_horizon_days=5)
    assert artifacts.folds
    for fold in artifacts.folds:
        assert set(fold.train_dates).isdisjoint(fold.valid_dates)
        assert set(fold.train_dates).isdisjoint(fold.test_dates)
        assert set(fold.valid_dates).isdisjoint(fold.test_dates)


def test_expanding_split_option_increases_train_window() -> None:
    bundle = build_model_research_bundle()
    rolling = generate_walk_forward_splits(bundle.panel, _split_config(expanding_train=False), bundle.calendar, primary_horizon_days=5)
    expanding = generate_walk_forward_splits(bundle.panel, _split_config(expanding_train=True), bundle.calendar, primary_horizon_days=5)
    assert len(expanding.folds[1].train_dates) > len(rolling.folds[1].train_dates)


def test_purge_logic_removes_overlapping_label_windows() -> None:
    bundle = build_model_research_bundle()
    artifacts = generate_walk_forward_splits(bundle.panel, _split_config(), bundle.calendar, primary_horizon_days=5)
    for fold in artifacts.folds:
        for train_date in fold.train_dates[-5:]:
            label_window = bundle.calendar.label_window(train_date, 5)
            assert label_window.end_date < fold.valid_start


def test_embargo_logic_removes_close_boundary_observations() -> None:
    bundle = build_model_research_bundle()
    artifacts = generate_walk_forward_splits(bundle.panel, _split_config(), bundle.calendar, primary_horizon_days=5)
    for fold in artifacts.folds:
        if fold.train_dates:
            assert bundle.calendar.trading_day_distance(fold.train_dates[-1], fold.valid_start) > 5
        if fold.valid_dates:
            assert bundle.calendar.trading_day_distance(fold.valid_dates[-1], fold.test_start) > 5


def test_fold_metadata_is_persisted_as_artifact(tmp_path) -> None:
    bundle = build_model_research_bundle()
    artifacts = generate_walk_forward_splits(bundle.panel, _split_config(), bundle.calendar, primary_horizon_days=5)
    path = persist_fold_metadata(artifacts, tmp_path / "folds" / "metadata.json")
    payload = read_json(path)
    assert path.exists()
    assert payload["folds"]
    assert payload["metadata"]


def test_validation_protocol_report_contains_timeline_plot() -> None:
    bundle = build_model_research_bundle()
    artifacts = generate_walk_forward_splits(bundle.panel, _split_config(), bundle.calendar, primary_horizon_days=5)
    assert "fold_timeline" in artifacts.timeline_plot
    assert artifacts.folds[0].fold_id in artifacts.timeline_plot


def test_split_artifacts_persist_protocol_and_role_matrix(tmp_path) -> None:
    bundle = build_model_research_bundle()
    artifacts = generate_walk_forward_splits(bundle.panel, _split_config(), bundle.calendar, primary_horizon_days=5)
    payload = read_json(persist_fold_metadata(artifacts, tmp_path / "folds" / "metadata.json"))
    assert payload["protocol"]["checks"]["no_overlap"] is True
    assert payload["role_matrix"]


def test_strict_split_policy_rejects_too_small_fold() -> None:
    bundle = build_model_research_bundle()
    config = _split_config()
    config = config.model_copy(update={"min_train_observations": 10_000, "allow_small_fixture_splits": False})
    with pytest.raises(ValueError, match="Strict split policy"):
        generate_walk_forward_splits(bundle.panel, config, bundle.calendar, primary_horizon_days=5)


def test_fixture_split_override_allows_small_fold_only_when_explicit() -> None:
    bundle = build_model_research_bundle()
    config = _split_config()
    config = config.model_copy(update={"min_train_observations": 10_000, "allow_small_fixture_splits": True})
    artifacts = generate_walk_forward_splits(bundle.panel, config, bundle.calendar, primary_horizon_days=5)
    assert artifacts.protocol.allow_small_fixture_splits is True
