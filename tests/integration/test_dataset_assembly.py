from __future__ import annotations

import pandas as pd
import pytest

from alpha_research.common.io import read_json, read_parquet
from alpha_research.config.models import LabelOverlapPolicy, LabelsConfig
from alpha_research.dataset.assembly import build_gold_panel
from alpha_research.features.engine import build_feature_panel
from alpha_research.labels.engine import build_label_panel
from tests.helpers.research_data import build_feature_research_bundle


def _labels_config() -> LabelsConfig:
    return LabelsConfig(
        primary_label="label_excess_5d_oo",
        secondary_labels=["label_excess_1d_oo", "label_resid_5d_oo", "label_raw_5d_oo"],
        execution_reference="open_t_plus_1",
        horizons_trading_days=[1, 5],
        families=["raw", "excess", "residual", "binary_quantile", "multiclass_quantile"],
        overlap_policy=LabelOverlapPolicy(allow_overlap=True, purge_days=5, embargo_days=5),
        benchmark="SPY_like_proxy_or_index_return",
        residualization_controls=["benchmark_return", "sector_dummies", "beta_estimate"],
    )


def _build_inputs():
    bundle = build_feature_research_bundle()
    feature_result = build_feature_panel(
        bundle.silver_market,
        bundle.silver_fundamentals,
        bundle.security_master,
        bundle.universe_snapshot,
        bundle.benchmark_market,
        bundle.calendar,
        interaction_cap=2,
    )
    label_result = build_label_panel(feature_result.panel, bundle.silver_market, bundle.benchmark_market, bundle.calendar, _labels_config())
    return bundle, feature_result, label_result


def test_gold_panel_combines_features_and_labels(tmp_path) -> None:
    _, feature_result, label_result = _build_inputs()
    assembled = build_gold_panel(feature_result.panel, label_result.panel, dataset_version="ds_v1", primary_label="label_excess_5d_oo", root=tmp_path)
    assert "ret_21" in assembled.panel.columns
    assert "label_excess_5d_oo" in assembled.panel.columns


def test_rows_without_universe_membership_are_marked_correctly(tmp_path) -> None:
    _, feature_result, label_result = _build_inputs()
    feature_panel = feature_result.panel.copy()
    target_idx = feature_panel.index[0]
    feature_panel.loc[target_idx, "is_in_universe"] = False
    assembled = build_gold_panel(feature_panel, label_result.panel, dataset_version="ds_v1", primary_label="label_excess_5d_oo", root=tmp_path)
    row = assembled.panel.loc[target_idx]
    assert bool(row["row_valid_flag"]) is False
    assert row["row_drop_reason"] == "not_in_universe"


def test_row_level_diagnostics_include_drop_reason(tmp_path) -> None:
    _, feature_result, label_result = _build_inputs()
    labels = label_result.panel.copy()
    target_idx = labels.index[1]
    labels.loc[target_idx, "label_excess_5d_oo"] = pd.NA
    assembled = build_gold_panel(feature_result.panel, labels, dataset_version="ds_v1", primary_label="label_excess_5d_oo", root=tmp_path)
    row = assembled.panel.loc[target_idx]
    assert bool(row["row_valid_flag"]) is False
    assert row["row_drop_reason"] == "missing_primary_label"


def test_dataset_manifest_contains_row_count_and_feature_count(tmp_path) -> None:
    _, feature_result, label_result = _build_inputs()
    assembled = build_gold_panel(feature_result.panel, label_result.panel, dataset_version="ds_v2", primary_label="label_excess_5d_oo", root=tmp_path)
    manifest = read_json(assembled.manifest_path)
    assert manifest["row_count"] == len(assembled.panel)
    assert manifest["feature_count"] == assembled.manifest.feature_count


def test_feature_coverage_ratio_is_deterministic(tmp_path) -> None:
    _, feature_result, label_result = _build_inputs()
    assembled = build_gold_panel(feature_result.panel, label_result.panel, dataset_version="ds_v3", primary_label="label_excess_5d_oo", root=tmp_path)
    expected = feature_result.panel[feature_result.feature_columns].notna().mean(axis=1)
    pd.testing.assert_series_equal(
        assembled.panel["feature_coverage_ratio"].reset_index(drop=True),
        expected.reset_index(drop=True),
        check_names=False,
    )


def test_gold_dataset_is_written_to_versioned_parquet(tmp_path) -> None:
    _, feature_result, label_result = _build_inputs()
    assembled = build_gold_panel(feature_result.panel, label_result.panel, dataset_version="ds_v4", primary_label="label_excess_5d_oo", root=tmp_path)
    assert assembled.parquet_path.exists()
    assert "ds_v4" in assembled.parquet_path.name
    reloaded = read_parquet(assembled.parquet_path)
    assert len(reloaded) == len(assembled.panel)
