from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from alpha_research.backtest.engine import run_backtest
from alpha_research.config.loader import load_resolved_config_bundle
from alpha_research.evaluation.ablation import run_ablation_suite
from alpha_research.evaluation.figures import render_mandatory_figures
from alpha_research.evaluation.metrics import build_decay_response_curve
from alpha_research.preprocessing.transforms import PreprocessingSpec
from alpha_research.splits.engine import FoldDefinition
from alpha_research.training.oof import ModelRunSpec, generate_oof_predictions
from tests.helpers.model_data import build_model_research_bundle


@lru_cache(maxsize=1)
def _build_context(repo_root: Path) -> dict[str, object]:
    loaded = load_resolved_config_bundle(repo_root)
    bundle = build_model_research_bundle()
    panel = bundle.panel.copy().sort_values(["security_id", "date"], kind="stable").reset_index(drop=True)
    security_order = {security_id: idx for idx, security_id in enumerate(sorted(panel["security_id"].unique()))}
    panel["sector"] = panel["security_id"].map(lambda security_id: "Technology" if security_order[security_id] % 2 == 0 else "Financials")
    panel["industry"] = panel["security_id"].map(lambda security_id: "Software" if security_order[security_id] % 2 == 0 else "Banks")
    panel["symbol"] = panel["security_id"].map(lambda security_id: security_id.replace("SEC_", "S"))
    panel["beta_estimate"] = panel["security_id"].map(lambda security_id: 0.8 + 0.03 * security_order[security_id])
    panel["adv20"] = panel["security_id"].map(lambda security_id: 1_500_000.0 + 150_000.0 * security_order[security_id])
    panel["feature_coverage_ratio"] = 1.0
    panel["is_in_universe"] = True
    panel["liquidity_bucket"] = panel["security_id"].map(lambda security_id: "high" if security_order[security_id] % 3 == 0 else "medium")
    panel["borrow_status"] = "medium"

    market_frames: list[pd.DataFrame] = []
    for security_id, group in panel.groupby("security_id", sort=False):
        sec_idx = security_order[security_id]
        base_price = 40.0 + sec_idx * 7.0
        driver = 0.001 + pd.to_numeric(group["ret_1"], errors="coerce").fillna(0.0) * 0.08
        open_px = base_price * np.exp(driver.cumsum())
        close_px = open_px * (1.0 + pd.to_numeric(group["ret_1"], errors="coerce").fillna(0.0) * 0.03)
        volume = 800_000 + sec_idx * 50_000
        market_frames.append(
            pd.DataFrame(
                {
                    "security_id": security_id,
                    "trade_date": group["date"].to_numpy(),
                    "open": open_px.to_numpy(dtype="float64"),
                    "high": np.maximum(open_px, close_px).to_numpy(dtype="float64"),
                    "low": np.minimum(open_px, close_px).to_numpy(dtype="float64"),
                    "close": close_px.to_numpy(dtype="float64"),
                    "adj_close": close_px.to_numpy(dtype="float64"),
                    "volume": np.full(len(group), volume, dtype="int64"),
                    "dollar_volume": (close_px * volume).to_numpy(dtype="float64"),
                    "is_price_valid": True,
                    "is_volume_valid": True,
                    "tradable_flag_prelim": True,
                    "data_quality_score": 0.99,
                    "data_version": "test_fixture_v1",
                }
            )
        )
    silver_market = pd.concat(market_frames, ignore_index=True)

    universe_snapshot = panel[
        ["date", "security_id", "is_in_universe", "feature_coverage_ratio", "liquidity_bucket"]
    ].copy()
    universe_snapshot["exclusion_reason_code"] = pd.NA
    universe_snapshot["price_t"] = silver_market["close"].to_numpy(dtype="float64")
    universe_snapshot["adv20_usd_t"] = silver_market["dollar_volume"].to_numpy(dtype="float64")
    universe_snapshot["data_quality_score"] = 0.99

    feature_panel = panel[
        [
            "date",
            "security_id",
            "symbol",
            "sector",
            "industry",
            "is_in_universe",
            "liquidity_bucket",
            "beta_estimate",
            "feature_coverage_ratio",
            "adv20",
            "borrow_status",
            *bundle.feature_columns,
        ]
    ].copy()

    valid_dates = sorted(panel["date"].unique().tolist())
    fold = FoldDefinition(
        fold_id="fold_000",
        train_dates=tuple(valid_dates[:-120]),
        valid_dates=tuple(valid_dates[-120:-60]),
        test_dates=tuple(valid_dates[-60:]),
        train_start=valid_dates[0],
        train_end=valid_dates[-121],
        valid_start=valid_dates[-120],
        valid_end=valid_dates[-61],
        test_start=valid_dates[-60],
        test_end=valid_dates[-1],
        primary_horizon_days=5,
        purge_days_applied=5,
        embargo_days_applied=5,
        expanding_train=False,
    )
    return {
        "loaded": loaded,
        "bundle": bundle,
        "panel": panel,
        "universe_snapshot": universe_snapshot,
        "feature_panel": feature_panel,
        "silver_market": silver_market,
        "folds": [fold],
    }


def test_ablation_suite_builds_feature_and_preprocessing_matrix(repo_root: Path) -> None:
    context = _build_context(repo_root)
    loaded = context["loaded"]
    result = run_ablation_suite(
        panel=context["panel"],
        folds=context["folds"],
        model_spec=ModelRunSpec(name="heuristic_blend_score"),
        feature_columns=context["bundle"].feature_columns,
        label_column=context["bundle"].label_column,
        dataset_version="gold_test",
        config_hash=loaded.config_hash,
        preprocessing_spec=PreprocessingSpec(winsor_lower=0.5, winsor_upper=99.5, scaler="zscore_by_date", neutralizer="sector"),
        universe_snapshot=context["universe_snapshot"],
        feature_panel=context["feature_panel"],
        silver_market=context["silver_market"],
        portfolio_config=loaded.bundle.portfolio,
        costs_config=loaded.bundle.costs,
        calendar=context["bundle"].calendar,
        scenario="base",
        root=str(repo_root),
    )

    assert set(result.results["scenario_group"]) == {"feature_family", "preprocessing"}
    assert "baseline_all_features" in set(result.results["scenario_name"])
    assert "baseline_current" in set(result.results["scenario_name"])
    assert result.results["feature_count"].max() > result.results["feature_count"].min()
    assert {"rank_ic_mean", "net_sharpe", "delta_rank_ic_mean", "delta_net_sharpe"} <= set(result.results.columns)


def test_figure_renderer_generates_svg_artifacts(repo_root: Path, tmp_path: Path) -> None:
    context = _build_context(repo_root)
    loaded = context["loaded"]
    oof = generate_oof_predictions(
        context["panel"],
        context["folds"],
        model_specs=[ModelRunSpec(name="heuristic_blend_score")],
        feature_columns=context["bundle"].feature_columns,
        label_column=context["bundle"].label_column,
        dataset_version="gold_test",
        config_hash=loaded.config_hash,
        preprocessing_spec=PreprocessingSpec(winsor_lower=0.5, winsor_upper=99.5, scaler="zscore_by_date", neutralizer="sector"),
    )
    predictions = oof.predictions.loc[oof.predictions["model_name"] == "heuristic_blend_score"].copy()
    backtest = run_backtest(
        predictions,
        context["universe_snapshot"],
        context["feature_panel"],
        context["silver_market"],
        loaded.bundle.portfolio,
        loaded.bundle.costs,
        context["bundle"].calendar,
        model_name="heuristic_blend_score",
        scenario="base",
    )
    decay_curve = build_decay_response_curve(
        context["panel"].merge(predictions[["date", "security_id", "raw_prediction"]], on=["date", "security_id"], how="inner"),
        prediction_column="raw_prediction",
        label_columns=[context["bundle"].label_column],
    )
    capacity_results = pd.DataFrame(
        [
            {"aum_level": 1_000_000.0, "scenario": "base", "net_sharpe": 0.3},
            {"aum_level": 2_000_000.0, "scenario": "base", "net_sharpe": 0.25},
        ]
    )

    rendered = render_mandatory_figures(
        tmp_path / "figures",
        requested_figures=list(loaded.bundle.reporting.mandatory_figures),
        universe_snapshot=context["universe_snapshot"],
        feature_panel=context["feature_panel"],
        predictions=predictions,
        labels=context["panel"][["date", "security_id", context["bundle"].label_column]],
        backtest_daily_state=backtest.daily_state,
        capacity_results=capacity_results,
        decay_curve=decay_curve,
    )

    assert len(rendered) == len(loaded.bundle.reporting.mandatory_figures)
    assert all(item.path.exists() for item in rendered)
    assert {item.path.suffix for item in rendered} == {".svg"}
