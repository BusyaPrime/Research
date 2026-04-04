from __future__ import annotations

import pandas as pd
import pytest

from alpha_research.time.calendar import ExchangeCalendarAdapter, SameBarExecutionError


def test_next_trading_day_skips_weekends_and_holidays() -> None:
    calendar = ExchangeCalendarAdapter()
    assert calendar.next_trading_day("2024-07-03").date().isoformat() == "2024-07-05"


def test_trading_day_distance_handles_holidays() -> None:
    calendar = ExchangeCalendarAdapter()
    assert calendar.trading_day_distance("2024-07-03", "2024-07-08") == 2


def test_label_window_uses_trading_day_horizon() -> None:
    calendar = ExchangeCalendarAdapter()
    window = calendar.label_window("2024-07-03", horizon_days=1)
    assert window.execution_date.date().isoformat() == "2024-07-05"
    assert window.end_date.date().isoformat() == "2024-07-08"


def test_decision_timestamp_is_before_execution_timestamp() -> None:
    calendar = ExchangeCalendarAdapter()
    assert calendar.decision_timestamp("2024-07-03") < calendar.execution_timestamp("2024-07-03")


def test_same_bar_execution_guard_raises() -> None:
    calendar = ExchangeCalendarAdapter()
    decision = calendar.decision_timestamp("2024-07-03")
    with pytest.raises(SameBarExecutionError):
        calendar.guard_no_same_bar_execution(decision, decision)


def test_validate_label_start_catches_wrong_alignment() -> None:
    calendar = ExchangeCalendarAdapter()
    with pytest.raises(ValueError):
        calendar.validate_label_start("2024-07-03", pd.Timestamp("2024-07-04"))
