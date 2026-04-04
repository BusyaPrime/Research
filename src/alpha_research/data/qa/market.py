from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from alpha_research.time.calendar import ExchangeCalendarAdapter


@dataclass(frozen=True)
class MarketQaOutputs:
    annotated_frame: pd.DataFrame
    issue_rows: pd.DataFrame
    summary: dict[str, float | int]


def run_market_qa(bronze_market: pd.DataFrame, calendar: ExchangeCalendarAdapter, corporate_actions: pd.DataFrame | None = None) -> MarketQaOutputs:
    frame = bronze_market.copy().sort_values(["security_id", "trade_date"], kind="stable").reset_index(drop=True)
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.normalize()

    frame["invalid_ohlc"] = (
        (frame["high"] < frame["low"])
        | ((frame["open"] > frame["high"]) | (frame["open"] < frame["low"]))
        | ((frame["close"] > frame["high"]) | (frame["close"] < frame["low"]))
    )
    frame["invalid_price_nonpositive"] = (frame[["open", "high", "low", "close"]].min(axis=1) <= 0)
    frame["invalid_volume"] = frame["volume"] < 0
    frame["duplicate_key"] = frame.duplicated(["security_id", "trade_date"], keep=False)

    previous_close = frame.groupby("security_id")["close"].shift(1)
    frame["close_return"] = frame["close"] / previous_close - 1.0
    frame["extreme_jump"] = frame["close_return"].abs() > 0.5
    if corporate_actions is not None and not corporate_actions.empty:
        actions = corporate_actions.copy()
        actions["effective_date"] = pd.to_datetime(actions["effective_date"], errors="coerce").dt.normalize()
        split_keys = set(
            actions.loc[actions["event_type"] == "split", ["security_id", "effective_date"]]
            .dropna()
            .itertuples(index=False, name=None)
        )
        frame["jump_explained_by_action"] = [
            (security_id, trade_date) in split_keys for security_id, trade_date in zip(frame["security_id"], frame["trade_date"], strict=True)
        ]
    else:
        frame["jump_explained_by_action"] = False
    frame["extreme_jump_unexplained"] = frame["extreme_jump"] & ~frame["jump_explained_by_action"]

    gap_rows: list[dict[str, object]] = []
    for security_id, group in frame.groupby("security_id"):
        sessions = pd.DatetimeIndex(group["trade_date"].sort_values().unique())
        if sessions.empty:
            continue
        expected = pd.DatetimeIndex(calendar.calendar.sessions_in_range(sessions.min(), sessions.max())).tz_localize(None)
        missing = expected.difference(sessions)
        for missing_session in missing:
            gap_rows.append({"security_id": security_id, "missing_trade_date": missing_session, "issue_type": "missing_trading_day"})

    issue_rows = pd.concat(
        [
            frame.loc[frame["invalid_ohlc"], ["security_id", "trade_date"]].assign(issue_type="invalid_ohlc"),
            frame.loc[frame["invalid_price_nonpositive"], ["security_id", "trade_date"]].assign(issue_type="invalid_price_nonpositive"),
            frame.loc[frame["invalid_volume"], ["security_id", "trade_date"]].assign(issue_type="invalid_volume"),
            frame.loc[frame["duplicate_key"], ["security_id", "trade_date"]].assign(issue_type="duplicate_key"),
            frame.loc[frame["extreme_jump_unexplained"], ["security_id", "trade_date"]].assign(issue_type="extreme_jump_unexplained"),
            pd.DataFrame(gap_rows),
        ],
        ignore_index=True,
    )

    issue_weight = (
        frame["invalid_ohlc"].astype(int)
        + frame["invalid_price_nonpositive"].astype(int)
        + frame["invalid_volume"].astype(int)
        + frame["duplicate_key"].astype(int)
        + frame["extreme_jump_unexplained"].astype(int)
    )
    frame["is_price_valid"] = ~(frame["invalid_ohlc"] | frame["invalid_price_nonpositive"])
    frame["is_volume_valid"] = ~frame["invalid_volume"]
    frame["tradable_flag_prelim"] = frame["is_price_valid"] & frame["is_volume_valid"] & ~frame["duplicate_key"]
    frame["data_quality_score"] = (1.0 - 0.2 * issue_weight).clip(lower=0.0, upper=1.0)
    frame["dollar_volume"] = frame["close"] * frame["volume"]

    summary = {
        "rows_total": int(len(frame)),
        "invalid_ohlc_rows": int(frame["invalid_ohlc"].sum()),
        "invalid_volume_rows": int(frame["invalid_volume"].sum()),
        "duplicate_rows": int(frame["duplicate_key"].sum()),
        "missing_trading_days": int(len(gap_rows)),
        "extreme_jump_unexplained_rows": int(frame["extreme_jump_unexplained"].sum()),
        "mean_data_quality_score": float(frame["data_quality_score"].replace([np.inf, -np.inf], np.nan).fillna(0).mean()),
    }
    return MarketQaOutputs(annotated_frame=frame, issue_rows=issue_rows, summary=summary)
