from __future__ import annotations

import pandas as pd
import pytest

from alpha_research.preprocessing.transforms import FoldSafePreprocessor, PreprocessingSpec
from alpha_research.testing.leakage import (
    FutureFeatureLeakageError,
    PreprocessingLeakageError,
    SameBarExecutionLeakageError,
    assert_no_future_feature_timestamps,
    assert_no_same_bar_execution,
    assert_preprocessor_fit_matches_train,
)
from alpha_research.time.calendar import ExchangeCalendarAdapter


def test_leakage_guard_catches_future_feature_timestamp() -> None:
    frame = pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2024-01-05"),
                "security_id": "SEC_A",
                "as_of_timestamp": pd.Timestamp("2024-01-05T21:00:00Z"),
                "source_available_from__book_equity": pd.Timestamp("2024-01-06T01:00:00Z"),
            }
        ]
    )
    with pytest.raises(FutureFeatureLeakageError):
        assert_no_future_feature_timestamps(frame)


def test_leakage_guard_catches_scaler_on_all_data_misuse() -> None:
    train = pd.DataFrame(
        {
            "date": [pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-03")],
            "feature_a": [1.0, 2.0],
            "feature_b": [10.0, 20.0],
        }
    )
    test = pd.DataFrame(
        {
            "date": [pd.Timestamp("2024-01-04")],
            "feature_a": [999.0],
            "feature_b": [5000.0],
        }
    )
    contaminated = pd.concat([train, test], ignore_index=True)
    preprocessor = FoldSafePreprocessor(
        PreprocessingSpec(winsor_lower=0.5, winsor_upper=99.5, scaler="zscore_by_date"),
        ["feature_a", "feature_b"],
    ).fit(contaminated)
    with pytest.raises(PreprocessingLeakageError):
        assert_preprocessor_fit_matches_train(preprocessor, train)


def test_leakage_guard_catches_same_bar_execution_misuse() -> None:
    calendar = ExchangeCalendarAdapter("XNYS")
    decision_timestamp = calendar.decision_timestamp("2024-01-05")
    execution_timestamp = decision_timestamp + pd.Timedelta(minutes=1)
    with pytest.raises(SameBarExecutionLeakageError):
        assert_no_same_bar_execution(
            calendar,
            decision_timestamp=decision_timestamp,
            execution_timestamp=execution_timestamp,
        )
