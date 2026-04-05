from __future__ import annotations

import numpy as np
import pandas as pd

from alpha_research.config.models import SplitsConfig
from alpha_research.splits.engine import generate_walk_forward_splits
from tests.helpers.model_data import build_model_research_bundle


def _randomized_panel(seed: int) -> tuple[pd.DataFrame, object]:
    bundle = build_model_research_bundle()
    panel = bundle.panel.copy()
    panel["date"] = pd.to_datetime(panel["date"], errors="coerce").dt.normalize()
    unique_dates = pd.Index(sorted(panel["date"].dropna().unique()))
    rng = np.random.default_rng(seed)
    keep_mask = rng.random(len(unique_dates)) > 0.12
    kept_dates = pd.DatetimeIndex(unique_dates[keep_mask])
    randomized = panel.loc[panel["date"].isin(kept_dates)].copy()
    return randomized, bundle.calendar


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
        allow_small_fixture_splits=False,
    )


def test_randomized_split_protocol_keeps_invariants_and_stays_deterministic() -> None:
    for seed in (3, 11, 29):
        panel, calendar = _randomized_panel(seed)
        first = generate_walk_forward_splits(panel, _split_config(), calendar, primary_horizon_days=5)
        second = generate_walk_forward_splits(panel, _split_config(), calendar, primary_horizon_days=5)

        first.protocol.assert_all(calendar)
        second.protocol.assert_all(calendar)
        pd.testing.assert_frame_equal(first.metadata, second.metadata)
        pd.testing.assert_frame_equal(first.role_matrix, second.role_matrix)

        for fold in first.folds:
            assert tuple(sorted(fold.train_dates)) == fold.train_dates
            assert tuple(sorted(fold.valid_dates)) == fold.valid_dates
            assert tuple(sorted(fold.test_dates)) == fold.test_dates
            assert set(fold.train_dates).isdisjoint(fold.valid_dates)
            assert set(fold.train_dates).isdisjoint(fold.test_dates)
            assert set(fold.valid_dates).isdisjoint(fold.test_dates)
