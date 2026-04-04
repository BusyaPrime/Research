from __future__ import annotations

import pandas as pd

from alpha_research.pit.asof_join import asof_lookup, build_pit_diagnostics, pit_join_fundamentals
from alpha_research.pit.builders import build_silver_fundamentals_pit, build_silver_market
from alpha_research.pit.timestamp_guards import assert_no_future_available_from


def _bronze_fundamentals() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "security_id": "SEC_AAPL",
                "source_company_id": "COMP_AAPL",
                "form_type": "10-Q",
                "filing_date": "2024-05-01",
                "acceptance_datetime": "2024-05-01T20:00:00Z",
                "fiscal_period_end": "2024-03-31",
                "metric_name_raw": "BookEquity",
                "metric_name_canonical": "book_equity",
                "metric_value": 100.0,
                "metric_unit": "USD",
                "statement_type": "balance_sheet",
                "available_from": "2024-05-01T20:00:00Z",
                "is_restatement": False,
                "data_version": "v1",
            },
            {
                "security_id": "SEC_AAPL",
                "source_company_id": "COMP_AAPL",
                "form_type": "10-Q/A",
                "filing_date": "2024-05-10",
                "acceptance_datetime": "2024-05-10T21:00:00Z",
                "fiscal_period_end": "2024-03-31",
                "metric_name_raw": "BookEquity",
                "metric_name_canonical": "book_equity",
                "metric_value": 120.0,
                "metric_unit": "USD",
                "statement_type": "balance_sheet",
                "available_from": "2024-05-10T21:00:00Z",
                "is_restatement": True,
                "data_version": "v1",
            },
            {
                "security_id": "SEC_AAPL",
                "source_company_id": "COMP_AAPL",
                "form_type": "10-Q",
                "filing_date": "2024-05-05",
                "acceptance_datetime": "2024-05-05T20:00:00Z",
                "fiscal_period_end": "2024-03-31",
                "metric_name_raw": "Revenue",
                "metric_name_canonical": "revenue_ttm",
                "metric_value": 300.0,
                "metric_unit": "USD",
                "statement_type": "income_statement",
                "available_from": "2024-05-05T20:00:00Z",
                "is_restatement": False,
                "data_version": "v1",
            },
        ]
    )


def test_asof_join_does_not_choose_future_row() -> None:
    silver = build_silver_fundamentals_pit(_bronze_fundamentals())
    result = asof_lookup(silver, "SEC_AAPL", "book_equity", "2024-05-03T12:00:00Z")
    assert result is not None
    assert result["metric_value"] == 100.0


def test_asof_join_returns_null_when_no_fact_available() -> None:
    silver = build_silver_fundamentals_pit(_bronze_fundamentals())
    result = asof_lookup(silver, "SEC_AAPL", "book_equity", "2024-04-01T12:00:00Z")
    assert result is None


def test_asof_join_uses_latest_available_from_before_date() -> None:
    silver = build_silver_fundamentals_pit(_bronze_fundamentals())
    result = asof_lookup(silver, "SEC_AAPL", "book_equity", "2024-05-20T12:00:00Z")
    assert result is not None
    assert result["metric_value"] == 120.0


def test_restated_fact_does_not_leak_into_past() -> None:
    silver = build_silver_fundamentals_pit(_bronze_fundamentals())
    pre_restatement = asof_lookup(silver, "SEC_AAPL", "book_equity", "2024-05-09T12:00:00Z")
    post_restatement = asof_lookup(silver, "SEC_AAPL", "book_equity", "2024-05-11T12:00:00Z")
    assert pre_restatement["metric_value"] == 100.0
    assert post_restatement["metric_value"] == 120.0


def test_pit_join_preserves_source_timestamp() -> None:
    silver = build_silver_fundamentals_pit(_bronze_fundamentals())
    panel = pd.DataFrame(
        [
            {"security_id": "SEC_AAPL", "as_of_timestamp": "2024-05-11T12:00:00Z"},
        ]
    )
    joined = pit_join_fundamentals(panel, silver, ["book_equity"])
    assert joined.loc[0, "book_equity"] == 120.0
    assert pd.Timestamp(joined.loc[0, "source_available_from__book_equity"]).isoformat() == "2024-05-10T21:00:00+00:00"
    assert_no_future_available_from(joined, ["book_equity"])


def test_pit_diagnostics_report_coverage_and_null_ratios() -> None:
    silver = build_silver_fundamentals_pit(_bronze_fundamentals())
    panel = pd.DataFrame(
        [
            {"security_id": "SEC_AAPL", "as_of_timestamp": "2024-05-11T12:00:00Z"},
            {"security_id": "SEC_AAPL", "as_of_timestamp": "2024-04-01T12:00:00Z"},
        ]
    )
    joined = pit_join_fundamentals(panel, silver, ["book_equity", "revenue_ttm"])
    diagnostics = build_pit_diagnostics(joined, ["book_equity", "revenue_ttm"])
    assert set(diagnostics.coverage_by_metric["metric_name_canonical"]) == {"book_equity", "revenue_ttm"}
    assert diagnostics.null_ratio_by_metric["null_ratio"].between(0, 1).all()

