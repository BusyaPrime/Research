from __future__ import annotations

import pandas as pd

from alpha_research.data.qa.market import run_market_qa
from alpha_research.time.calendar import ExchangeCalendarAdapter


def _market_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"security_id": "SEC_BAD", "symbol": "BAD", "trade_date": "2024-07-01", "open": 10, "high": 9, "low": 10, "close": 10, "adj_close": 10, "volume": 100, "currency": "USD", "provider_name": "x", "data_version": "v1"},
            {"security_id": "SEC_NEG", "symbol": "NEG", "trade_date": "2024-07-01", "open": 10, "high": 11, "low": 9, "close": 10, "adj_close": 10, "volume": -5, "currency": "USD", "provider_name": "x", "data_version": "v1"},
            {"security_id": "SEC_DUP", "symbol": "DUP", "trade_date": "2024-07-01", "open": 10, "high": 11, "low": 9, "close": 10, "adj_close": 10, "volume": 50, "currency": "USD", "provider_name": "x", "data_version": "v1"},
            {"security_id": "SEC_DUP", "symbol": "DUP", "trade_date": "2024-07-01", "open": 10, "high": 11, "low": 9, "close": 10, "adj_close": 10, "volume": 50, "currency": "USD", "provider_name": "x", "data_version": "v1"},
            {"security_id": "SEC_MISS", "symbol": "MISS", "trade_date": "2024-07-01", "open": 10, "high": 11, "low": 9, "close": 10, "adj_close": 10, "volume": 40, "currency": "USD", "provider_name": "x", "data_version": "v1"},
            {"security_id": "SEC_MISS", "symbol": "MISS", "trade_date": "2024-07-03", "open": 11, "high": 12, "low": 10, "close": 11, "adj_close": 11, "volume": 40, "currency": "USD", "provider_name": "x", "data_version": "v1"},
            {"security_id": "SEC_SPLIT", "symbol": "SPLT", "trade_date": "2024-07-01", "open": 10, "high": 10, "low": 10, "close": 10, "adj_close": 10, "volume": 100, "currency": "USD", "provider_name": "x", "data_version": "v1"},
            {"security_id": "SEC_SPLIT", "symbol": "SPLT", "trade_date": "2024-07-02", "open": 20, "high": 20, "low": 20, "close": 20, "adj_close": 20, "volume": 100, "currency": "USD", "provider_name": "x", "data_version": "v1"},
            {"security_id": "SEC_JUMP", "symbol": "JUMP", "trade_date": "2024-07-01", "open": 10, "high": 10, "low": 10, "close": 10, "adj_close": 10, "volume": 100, "currency": "USD", "provider_name": "x", "data_version": "v1"},
            {"security_id": "SEC_JUMP", "symbol": "JUMP", "trade_date": "2024-07-02", "open": 20, "high": 20, "low": 20, "close": 20, "adj_close": 20, "volume": 100, "currency": "USD", "provider_name": "x", "data_version": "v1"},
        ]
    )


def _ca_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"security_id": "SEC_SPLIT", "event_type": "split", "event_date": "2024-07-02", "effective_date": "2024-07-02", "split_ratio": 2.0, "dividend_amount": None, "delisting_code": None, "old_symbol": None, "new_symbol": None, "data_version": "v1"}
        ]
    )


def test_market_qa_catches_ohlc_inconsistency() -> None:
    outputs = run_market_qa(_market_frame(), ExchangeCalendarAdapter(), _ca_frame())
    assert "invalid_ohlc" in set(outputs.issue_rows["issue_type"])


def test_market_qa_detects_negative_volume() -> None:
    outputs = run_market_qa(_market_frame(), ExchangeCalendarAdapter(), _ca_frame())
    assert "invalid_volume" in set(outputs.issue_rows["issue_type"])


def test_market_qa_detects_duplicate_rows() -> None:
    outputs = run_market_qa(_market_frame(), ExchangeCalendarAdapter(), _ca_frame())
    assert "duplicate_key" in set(outputs.issue_rows["issue_type"])


def test_market_qa_flags_missing_trading_days() -> None:
    outputs = run_market_qa(_market_frame(), ExchangeCalendarAdapter(), _ca_frame())
    assert "missing_trading_day" in set(outputs.issue_rows["issue_type"])


def test_market_qa_extreme_jump_requires_action_explanation() -> None:
    outputs = run_market_qa(_market_frame(), ExchangeCalendarAdapter(), _ca_frame())
    jump_issues = outputs.issue_rows.loc[outputs.issue_rows["issue_type"] == "extreme_jump_unexplained", "security_id"].tolist()
    assert "SEC_JUMP" in jump_issues
    assert "SEC_SPLIT" not in jump_issues


def test_market_qa_computes_data_quality_score() -> None:
    outputs = run_market_qa(_market_frame(), ExchangeCalendarAdapter(), _ca_frame())
    assert "data_quality_score" in outputs.annotated_frame.columns
    assert outputs.summary["mean_data_quality_score"] < 1.0
