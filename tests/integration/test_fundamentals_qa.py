from __future__ import annotations

import pandas as pd

from alpha_research.data.qa.fundamentals import run_fundamentals_qa


def _fundamentals_frame() -> pd.DataFrame:
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
                "metric_value": "bad",
                "metric_unit": "USD",
                "statement_type": "balance_sheet",
                "available_from": "2024-05-02T03:59:59Z",
                "is_restatement": False,
                "data_version": "v1",
            },
            {
                "security_id": "SEC_MSFT",
                "source_company_id": "COMP_MSFT",
                "form_type": "10-Q",
                "filing_date": "2024-05-01",
                "acceptance_datetime": "2024-05-01T20:00:00Z",
                "fiscal_period_end": "2024-03-31",
                "metric_name_raw": "BookEquity",
                "metric_name_canonical": "book_equity",
                "metric_value": "100",
                "metric_unit": "shares",
                "statement_type": "balance_sheet",
                "available_from": "2024-05-02T03:59:59Z",
                "is_restatement": False,
                "data_version": "v1",
            },
            {
                "security_id": "SEC_GOOG",
                "source_company_id": "COMP_GOOG",
                "form_type": "10-Q",
                "filing_date": "2024-05-10",
                "acceptance_datetime": "2024-05-09T20:00:00Z",
                "fiscal_period_end": "2024-03-31",
                "metric_name_raw": "Revenue",
                "metric_name_canonical": "revenue_ttm",
                "metric_value": "250",
                "metric_unit": "USD",
                "statement_type": "income_statement",
                "available_from": "2024-05-10T23:59:59Z",
                "is_restatement": False,
                "data_version": "v1",
            },
        ]
    )


def test_fundamentals_qa_flags_unparseable_metric_value() -> None:
    outputs = run_fundamentals_qa(_fundamentals_frame(), as_of_date="2024-08-01")
    assert "metric_value_parseability" in set(outputs.issue_rows["issue_type"])


def test_fundamentals_qa_flags_inconsistent_units() -> None:
    outputs = run_fundamentals_qa(_fundamentals_frame(), as_of_date="2024-08-01")
    assert "metric_unit_inconsistent" in set(outputs.issue_rows["issue_type"])


def test_fundamentals_qa_flags_impossible_timestamps() -> None:
    outputs = run_fundamentals_qa(_fundamentals_frame(), as_of_date="2024-08-01")
    assert "impossible_timestamp" in set(outputs.issue_rows["issue_type"])


def test_fundamentals_qa_computes_completeness_by_metric_year() -> None:
    outputs = run_fundamentals_qa(_fundamentals_frame(), as_of_date="2024-08-01")
    assert set(outputs.completeness_by_metric_year["metric_name_canonical"]) == {"book_equity", "revenue_ttm"}


def test_fundamentals_qa_computes_staleness() -> None:
    outputs = run_fundamentals_qa(_fundamentals_frame(), as_of_date="2024-08-01")
    assert "staleness_days" in outputs.staleness_by_security.columns
    assert outputs.staleness_by_security["staleness_days"].max() >= 80


def test_fundamentals_qa_report_has_all_required_sections() -> None:
    outputs = run_fundamentals_qa(_fundamentals_frame(), as_of_date="2024-08-01")
    assert set(outputs.report_sections) == {"parseability", "units", "timestamps", "completeness", "staleness"}
