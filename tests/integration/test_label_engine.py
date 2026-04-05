from __future__ import annotations

import numpy as np
import pytest

from alpha_research.labels.engine import build_label_panel
from tests.helpers.research_data import build_label_research_bundle


def test_open_to_open_1d_label_starts_after_execution_timestamp() -> None:
    bundle = build_label_research_bundle()
    result = build_label_panel(bundle.panel, bundle.silver_market, bundle.benchmark_market, bundle.calendar, bundle.labels_config)
    row = result.panel.loc[(result.panel["security_id"] == "SEC_A") & (result.panel["date"] == bundle.dates[0])].iloc[0]
    expected = 103.0 / 101.0 - 1.0
    same_bar_wrong = 101.0 / 100.0 - 1.0
    assert row["label_raw_1d_oo"] == pytest.approx(expected)
    assert row["label_raw_1d_oo"] != pytest.approx(same_bar_wrong)


def test_open_to_open_5d_label_uses_trading_day_offsets() -> None:
    bundle = build_label_research_bundle()
    result = build_label_panel(bundle.panel, bundle.silver_market, bundle.benchmark_market, bundle.calendar, bundle.labels_config)
    row = result.panel.loc[(result.panel["security_id"] == "SEC_A") & (result.panel["date"] == bundle.dates[0])].iloc[0]
    expected = 111.0 / 101.0 - 1.0
    assert row["label_raw_5d_oo"] == pytest.approx(expected)


def test_benchmark_excess_label_correctly_subtracts_benchmark_return() -> None:
    bundle = build_label_research_bundle()
    result = build_label_panel(bundle.panel, bundle.silver_market, bundle.benchmark_market, bundle.calendar, bundle.labels_config)
    row = result.panel.loc[(result.panel["security_id"] == "SEC_A") & (result.panel["date"] == bundle.dates[0])].iloc[0]
    stock_return = 111.0 / 101.0 - 1.0
    benchmark_return = 109.0 / 101.0 - 1.0
    assert row["label_excess_5d_oo"] == pytest.approx(stock_return - benchmark_return)


def test_residual_label_uses_only_current_date_controls() -> None:
    bundle = build_label_research_bundle()
    baseline = build_label_panel(bundle.panel, bundle.silver_market, bundle.benchmark_market, bundle.calendar, bundle.labels_config)

    mutated_panel = bundle.panel.copy()
    mutated_panel.loc[mutated_panel["date"] != bundle.dates[0], "beta_estimate"] = 999.0
    mutated_panel.loc[mutated_panel["date"] != bundle.dates[0], "sector"] = "Mutated"
    mutated = build_label_panel(mutated_panel, bundle.silver_market, bundle.benchmark_market, bundle.calendar, bundle.labels_config)

    baseline_slice = baseline.panel.loc[baseline.panel["date"] == bundle.dates[0], ["security_id", "label_resid_1d_oo"]].sort_values("security_id", kind="stable")
    mutated_slice = mutated.panel.loc[mutated.panel["date"] == bundle.dates[0], ["security_id", "label_resid_1d_oo"]].sort_values("security_id", kind="stable")
    np.testing.assert_allclose(
        baseline_slice["label_resid_1d_oo"].to_numpy(dtype=float),
        mutated_slice["label_resid_1d_oo"].to_numpy(dtype=float),
    )


def test_overlap_policy_signals_required_purge_horizon() -> None:
    bundle = build_label_research_bundle()
    result = build_label_panel(bundle.panel, bundle.silver_market, bundle.benchmark_market, bundle.calendar, bundle.labels_config)
    assert result.overlap_report["allow_overlap"] is True
    assert result.overlap_report["required_minimum_purge_days"] == 5
    assert result.overlap_report["required_minimum_embargo_days"] == 5


def test_label_sanity_report_covers_all_horizons() -> None:
    bundle = build_label_research_bundle()
    result = build_label_panel(bundle.panel, bundle.silver_market, bundle.benchmark_market, bundle.calendar, bundle.labels_config)
    expected_labels = {
        "label_raw_1d_oo",
        "label_excess_1d_oo",
        "label_resid_1d_oo",
        "label_raw_5d_oo",
        "label_excess_5d_oo",
        "label_resid_5d_oo",
    }
    assert set(result.sanity_report["label_name"]) == expected_labels
    assert (result.sanity_report["non_null"] > 0).all()
