from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from alpha_research.preprocessing.transforms import (
    FoldSafePreprocessor,
    PreprocessingSpec,
    Winsorizer,
    beta_neutralize,
    robust_zscore_by_date,
    sector_neutralize,
    zscore_by_date,
)


def test_winsorizer_does_not_use_test_fold_during_fit() -> None:
    train = pd.DataFrame({"feature": [1.0, 2.0, 3.0]})
    test = pd.DataFrame({"feature": [100.0]})
    winsorizer = Winsorizer(lower_pct=0.0, upper_pct=1.0).fit(train, ["feature"])
    transformed = winsorizer.transform(test)
    assert transformed.loc[0, "feature"] == pytest.approx(3.0)


def test_zscore_scaler_is_cross_sectional_by_date() -> None:
    frame = pd.DataFrame(
        {
            "date": [pd.Timestamp("2024-01-02")] * 3 + [pd.Timestamp("2024-01-03")] * 2,
            "feature": [1.0, 2.0, 3.0, 10.0, 20.0],
        }
    )
    transformed = zscore_by_date(frame, ["feature"])
    first_date = transformed.loc[transformed["date"] == pd.Timestamp("2024-01-02"), "feature"]
    assert first_date.mean() == pytest.approx(0.0)
    assert first_date.std(ddof=0) == pytest.approx(1.0)


def test_robust_zscore_is_resilient_to_outliers() -> None:
    frame = pd.DataFrame({"date": [pd.Timestamp("2024-01-02")] * 4, "feature": [1.0, 2.0, 3.0, 100.0]})
    transformed = robust_zscore_by_date(frame, ["feature"])
    values = transformed["feature"].to_numpy(dtype=float)
    assert values[1] == pytest.approx(-0.3372453797, rel=1e-6)
    assert values[2] == pytest.approx(0.3372453797, rel=1e-6)
    assert values[3] > 50.0


def test_sector_neutralization_does_not_break_row_index() -> None:
    frame = pd.DataFrame(
        {
            "date": [pd.Timestamp("2024-01-02")] * 3,
            "sector": ["Tech", "Tech", "Health"],
            "feature": [1.0, 3.0, 10.0],
        },
        index=[10, 20, 30],
    )
    transformed = sector_neutralize(frame, ["feature"])
    assert transformed.index.tolist() == [10, 20, 30]
    assert transformed.loc[10, "feature"] == pytest.approx(-1.0)
    assert transformed.loc[20, "feature"] == pytest.approx(1.0)


def test_beta_neutralization_uses_correct_beta_input() -> None:
    frame = pd.DataFrame(
        {
            "date": [pd.Timestamp("2024-01-02")] * 4,
            "beta_estimate": [0.5, 1.0, 1.5, 2.0],
            "feature": [2.0, 4.0, 6.0, 8.0],
        }
    )
    transformed = beta_neutralize(frame, ["feature"])
    assert np.allclose(transformed["feature"].to_numpy(dtype=float), 0.0, atol=1e-10)


def test_fold_safe_preprocessing_api_has_no_test_contamination() -> None:
    train = pd.DataFrame(
        {
            "date": [pd.Timestamp("2024-01-02")] * 3,
            "sector": ["Tech", "Tech", "Health"],
            "beta_estimate": [1.0, 1.1, 0.9],
            "feature": [1.0, 2.0, 3.0],
        }
    )
    test = pd.DataFrame(
        {
            "date": [pd.Timestamp("2024-01-03")] * 2,
            "sector": ["Tech", "Health"],
            "beta_estimate": [1.0, 1.2],
            "feature": [2.5, 100.0],
        }
    )
    spec = PreprocessingSpec(winsor_lower=0.0, winsor_upper=1.0, scaler="percentile_rank_by_date", neutralizer=None)
    preprocessor = FoldSafePreprocessor(spec, ["feature"]).fit(train)
    transformed = preprocessor.transform(test)
    assert transformed.loc[1, "feature"] == pytest.approx(1.0)
    assert transformed.loc[0, "feature"] == pytest.approx(0.5)
