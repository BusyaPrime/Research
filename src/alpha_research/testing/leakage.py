from __future__ import annotations

from dataclasses import asdict

import pandas as pd

from alpha_research.preprocessing.transforms import FoldSafePreprocessor
from alpha_research.time.calendar import ExchangeCalendarAdapter, SameBarExecutionError


class FutureFeatureLeakageError(ValueError):
    """Raised when a feature row references source data from the future."""


class PreprocessingLeakageError(ValueError):
    """Raised when preprocessing state does not match the training fold only."""


class SameBarExecutionLeakageError(ValueError):
    """Raised when execution semantics violate next-bar baseline assumptions."""


def assert_no_future_feature_timestamps(
    frame: pd.DataFrame,
    *,
    decision_column: str = "as_of_timestamp",
    source_prefix: str = "source_available_from__",
) -> None:
    working = frame.copy()
    if decision_column not in working.columns:
        raise FutureFeatureLeakageError(f"Missing decision timestamp column: {decision_column}")

    decision_ts = pd.to_datetime(working[decision_column], errors="coerce", utc=True)
    source_columns = [column for column in working.columns if column.startswith(source_prefix)]
    for column in source_columns:
        source_ts = pd.to_datetime(working[column], errors="coerce", utc=True)
        invalid = source_ts.notna() & decision_ts.notna() & (source_ts > decision_ts)
        if invalid.any():
            sample = working.loc[invalid, ["date", "security_id", decision_column, column]].head(3).to_dict(orient="records")
            raise FutureFeatureLeakageError(
                f"Detected future feature availability in {column}. Sample offending rows: {sample}"
            )


def assert_preprocessor_fit_matches_train(
    preprocessor: FoldSafePreprocessor,
    train_frame: pd.DataFrame,
) -> None:
    if preprocessor.fit_metadata_ is None:
        raise PreprocessingLeakageError("Preprocessor has not been fitted.")
    expected = preprocessor._build_fit_metadata(train_frame)
    actual = preprocessor.fit_metadata_
    if asdict(actual) != asdict(expected):
        raise PreprocessingLeakageError(
            f"Preprocessor fit metadata mismatch. Expected train-only metadata {asdict(expected)}, got {asdict(actual)}."
        )


def assert_no_same_bar_execution(
    calendar: ExchangeCalendarAdapter,
    *,
    decision_timestamp: pd.Timestamp,
    execution_timestamp: pd.Timestamp,
) -> None:
    try:
        calendar.guard_no_same_bar_execution(decision_timestamp, execution_timestamp)
    except SameBarExecutionError as exc:
        raise SameBarExecutionLeakageError(str(exc)) from exc
