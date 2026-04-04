from __future__ import annotations

from dataclasses import dataclass

import exchange_calendars as xcals
import pandas as pd


class SameBarExecutionError(ValueError):
    """Raised when a baseline strategy attempts same-bar execution."""


def _session_label(value: str | pd.Timestamp) -> pd.Timestamp:
    return pd.Timestamp(value).normalize().tz_localize(None)


@dataclass(frozen=True)
class LabelWindow:
    decision_date: pd.Timestamp
    execution_date: pd.Timestamp
    end_date: pd.Timestamp


class ExchangeCalendarAdapter:
    def __init__(self, exchange: str = "XNYS", timezone: str = "America/New_York") -> None:
        self.exchange = exchange
        self.timezone = timezone
        self.calendar = xcals.get_calendar(exchange)

    def is_trading_day(self, session: str | pd.Timestamp) -> bool:
        return bool(self.calendar.is_session(_session_label(session)))

    def next_trading_day(self, session: str | pd.Timestamp, steps: int = 1) -> pd.Timestamp:
        current = _session_label(session)
        for _ in range(steps):
            current = self.calendar.next_session(current)
        return current.tz_localize(None)

    def previous_trading_day(self, session: str | pd.Timestamp, steps: int = 1) -> pd.Timestamp:
        current = _session_label(session)
        for _ in range(steps):
            current = self.calendar.previous_session(current)
        return current.tz_localize(None)

    def trading_day_distance(self, start: str | pd.Timestamp, end: str | pd.Timestamp) -> int:
        start_session = _session_label(start)
        end_session = _session_label(end)
        if start_session == end_session:
            return 0
        sessions = self.calendar.sessions_in_range(min(start_session, end_session), max(start_session, end_session))
        distance = len(sessions) - 1
        return distance if end_session >= start_session else -distance

    def window_by_trading_days(self, end_session: str | pd.Timestamp, lookback_days: int, include_end: bool = True) -> pd.DatetimeIndex:
        end_label = _session_label(end_session)
        start = self.previous_trading_day(end_label, lookback_days - (1 if include_end else 0))
        if not include_end:
            end_label = self.previous_trading_day(end_label, 1)
        return self.calendar.sessions_in_range(start, end_label).tz_localize(None)

    def decision_timestamp(self, trade_date: str | pd.Timestamp) -> pd.Timestamp:
        session = _session_label(trade_date)
        return self.calendar.session_close(session).tz_convert(self.timezone)

    def execution_timestamp(self, trade_date: str | pd.Timestamp) -> pd.Timestamp:
        next_session = self.next_trading_day(trade_date, 1)
        return self.calendar.session_open(next_session).tz_convert(self.timezone)

    def ensure_decision_before_execution(self, trade_date: str | pd.Timestamp) -> None:
        decision = self.decision_timestamp(trade_date)
        execution = self.execution_timestamp(trade_date)
        if decision >= execution:
            raise SameBarExecutionError("Decision timestamp must be earlier than execution timestamp.")

    def guard_no_same_bar_execution(self, decision_timestamp: pd.Timestamp, execution_timestamp: pd.Timestamp) -> None:
        if execution_timestamp <= decision_timestamp or decision_timestamp.normalize() == execution_timestamp.normalize():
            raise SameBarExecutionError("Baseline execution on the same bar is forbidden.")

    def label_window(self, trade_date: str | pd.Timestamp, horizon_days: int) -> LabelWindow:
        execution_date = self.next_trading_day(trade_date, 1)
        end_date = self.next_trading_day(execution_date, horizon_days)
        return LabelWindow(
            decision_date=_session_label(trade_date),
            execution_date=execution_date,
            end_date=end_date,
        )

    def validate_label_start(self, trade_date: str | pd.Timestamp, proposed_start_date: str | pd.Timestamp) -> None:
        expected_start = self.next_trading_day(trade_date, 1)
        proposed = _session_label(proposed_start_date)
        if proposed != expected_start:
            raise ValueError(
                f"Label start must equal next trading day after decision date. Expected {expected_start.date()}, got {proposed.date()}."
            )
