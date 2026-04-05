from __future__ import annotations

import pandas as pd

from alpha_research.config.models import ReportingConfig
from alpha_research.evaluation.metrics import (
    build_decay_response_curve,
    compute_portfolio_metrics,
    compute_predictive_metrics,
    compute_regime_breakdown,
)
from alpha_research.evaluation.skepticism import (
    build_model_hypothesis_registry,
    compute_multiple_testing_diagnostics,
    compute_portfolio_uncertainty,
    compute_prediction_correlation_matrix,
    compute_predictive_uncertainty,
    compute_stability_gates,
    summarize_approval_recommendation,
)
from alpha_research.evaluation.reporting import (
    render_executive_summary,
    render_final_report,
    render_final_report_html,
    render_report_sections,
)
from tests.helpers.model_data import build_model_research_bundle


def test_predictive_metrics_suite_computes_ic_and_rank_ic() -> None:
    bundle = build_model_research_bundle()
    predictions = bundle.panel[["date", "security_id"]].copy()
    predictions["raw_prediction"] = bundle.panel["mom_21_ex1"]
    labels = bundle.panel[["date", "security_id", bundle.label_column]].copy()
    metrics = compute_predictive_metrics(predictions, labels, label_column=bundle.label_column)
    summary = metrics.loc[metrics["metric"].notna()].set_index("metric")["value"].to_dict()
    assert "ic_mean" in summary
    assert "rank_ic_mean" in summary


def test_portfolio_metrics_suite_computes_sharpe_and_max_drawdown() -> None:
    daily_state = pd.DataFrame(
        [
            {"date": pd.Timestamp("2024-01-02"), "net_pnl": 100.0, "aum": 1_000_100.0},
            {"date": pd.Timestamp("2024-01-03"), "net_pnl": -50.0, "aum": 1_000_050.0},
            {"date": pd.Timestamp("2024-01-04"), "net_pnl": 200.0, "aum": 1_000_250.0},
        ]
    )
    metrics = compute_portfolio_metrics(daily_state, initial_aum=1_000_000.0).set_index("metric")["value"].to_dict()
    assert "net_sharpe" in metrics
    assert "max_drawdown" in metrics


def test_regime_analysis_suite_computes_metrics_by_regime() -> None:
    frame = pd.DataFrame(
        [
            {"regime": "risk_on", "prediction": 0.9, "label": 0.05},
            {"regime": "risk_on", "prediction": 0.8, "label": 0.04},
            {"regime": "risk_off", "prediction": 0.2, "label": -0.02},
            {"regime": "risk_off", "prediction": 0.1, "label": -0.03},
        ]
    )
    metrics = compute_regime_breakdown(frame, prediction_column="prediction", label_column="label", regime_column="regime")
    assert set(metrics["regime"]) == {"risk_on", "risk_off"}
    assert "ic" in metrics.columns


def test_decay_suite_builds_response_curve_by_horizons() -> None:
    frame = pd.DataFrame(
        [
            {"date": pd.Timestamp("2024-01-02"), "prediction": 0.1, "label_excess_1d_oo": 0.01, "label_excess_5d_oo": 0.05},
            {"date": pd.Timestamp("2024-01-02"), "prediction": 0.2, "label_excess_1d_oo": 0.02, "label_excess_5d_oo": 0.06},
            {"date": pd.Timestamp("2024-01-02"), "prediction": 0.3, "label_excess_1d_oo": 0.03, "label_excess_5d_oo": 0.07},
            {"date": pd.Timestamp("2024-01-02"), "prediction": 0.4, "label_excess_1d_oo": 0.04, "label_excess_5d_oo": 0.08},
            {"date": pd.Timestamp("2024-01-02"), "prediction": 0.5, "label_excess_1d_oo": 0.05, "label_excess_5d_oo": 0.09},
        ]
    )
    curve = build_decay_response_curve(frame, prediction_column="prediction", label_columns=["label_excess_1d_oo", "label_excess_5d_oo"])
    assert set(curve["horizon_days"]) == {1, 5}
    assert "mean_response" in curve.columns


def test_final_report_generator_includes_all_mandatory_sections() -> None:
    reporting_config = ReportingConfig(
        formats=["markdown"],
        include_sections=["executive_summary", "uncertainty_analysis", "false_discovery_control", "backtest_results", "capacity_analysis", "regime_analysis", "decay_analysis", "ablation_analysis", "approval_summary", "limitations", "next_steps"],
        mandatory_figures=["ic_over_time", "equity_curve_net", "capacity_curve"],
    )
    report = render_final_report(reporting_config, project_name="Alpha Platform", section_payloads={"backtest_results": "Тело бэктеста.", "ablation_analysis": "Тело ablation."})
    assert "## Итог по запуску" in report
    assert "## Статистическая неопределенность" in report
    assert "## Контроль ложных открытий" in report
    assert "## Результаты бэктеста" in report
    assert "## Анализ capacity" in report
    assert "## Анализ по режимам" in report
    assert "## Анализ затухания сигнала" in report
    assert "## Ablation-анализ" in report
    assert "## Решение по запуску" in report
    assert "## Ограничения" in report
    assert "## Что делать дальше" in report


def test_report_sections_and_html_renderer_preserve_requested_structure() -> None:
    reporting_config = ReportingConfig(
        formats=["markdown", "html"],
        include_sections=["executive_summary", "backtest_results", "limitations", "next_steps"],
        mandatory_figures=["ic_over_time", "equity_curve_net"],
    )
    sections = render_report_sections(
        reporting_config,
        section_payloads={"backtest_results": "Тело бэктеста."},
        limitations=["Есть временные упрощения."],
        next_steps=["Дорендерить figure-артефакты."],
    )
    html_report = render_final_report_html(
        reporting_config,
        project_name="Alpha Platform",
        section_payloads={"backtest_results": "Тело бэктеста."},
        limitations=["Есть временные упрощения."],
        next_steps=["Дорендерить figure-артефакты."],
    )

    assert [section.key for section in sections] == ["executive_summary", "backtest_results", "limitations", "next_steps"]
    assert "<html lang=\"ru\">" in html_report
    assert "<h2>Результаты бэктеста</h2>" in html_report
    assert "Дорендерить figure-артефакты." in html_report


def test_executive_summary_template_contains_limitations_and_next_steps() -> None:
    summary = render_executive_summary(
        project_name="Alpha Platform",
        headline="Короткий итог по исследовательскому стеку.",
        limitations=["Capacity layer пока синтетический."],
        next_steps=["Добавить более плотный robustness report."],
    )
    assert "Ограничения" in summary
    assert "Что делать дальше" in summary


def test_skepticism_suite_computes_uncertainty_and_fdr_controls() -> None:
    bundle = build_model_research_bundle()
    predictions = bundle.panel[["date", "security_id"]].copy()
    predictions["model_name"] = "ridge_regression"
    predictions["raw_prediction"] = bundle.panel["mom_21_ex1"]
    labels = bundle.panel[["date", "security_id", bundle.label_column]].copy()

    predictive_uncertainty = compute_predictive_uncertainty(predictions, labels, label_column=bundle.label_column)
    assert {"rank_ic_ci_lower", "rank_ic_ci_upper", "rank_ic_p_value"} <= set(predictive_uncertainty["metric"])

    hypotheses = build_model_hypothesis_registry(predictions, labels, label_column=bundle.label_column)
    multiple_testing = compute_multiple_testing_diagnostics(hypotheses, effective_trial_count=7)
    assert "rejected_fdr" in multiple_testing.columns
    assert int(multiple_testing["effective_trial_count"].iloc[0]) == 7


def test_portfolio_uncertainty_and_approval_summary_are_machine_readable() -> None:
    daily_state = pd.DataFrame(
        [
            {"date": pd.Timestamp("2024-01-02"), "net_pnl": 120.0, "aum": 1_000_120.0},
            {"date": pd.Timestamp("2024-01-03"), "net_pnl": 80.0, "aum": 1_000_200.0},
            {"date": pd.Timestamp("2024-01-04"), "net_pnl": -20.0, "aum": 1_000_180.0},
            {"date": pd.Timestamp("2024-01-05"), "net_pnl": 110.0, "aum": 1_000_290.0},
        ]
    )
    portfolio_uncertainty = compute_portfolio_uncertainty(daily_state, initial_aum=1_000_000.0, trial_count=5)
    assert {"probabilistic_sharpe_ratio", "deflated_sharpe_ratio"} <= set(portfolio_uncertainty["metric"])

    predictive_uncertainty = pd.DataFrame(
        [
            {"metric": "rank_ic_ci_lower", "value": 0.01},
            {"metric": "rank_ic_mean", "value": 0.03},
        ]
    )
    regime_metrics = pd.DataFrame([{"regime": "risk_on", "ic": 0.02}, {"regime": "risk_off", "ic": 0.01}])
    cost_sensitivity = pd.DataFrame([{"scenario": "base", "net_sharpe": 1.2}, {"scenario": "stressed", "net_sharpe": 0.8}])
    ablation_results = pd.DataFrame([{"delta_rank_ic_mean": -0.01}, {"delta_rank_ic_mean": 0.0}])
    holdings_snapshots = pd.DataFrame([{"weight": 0.15}, {"weight": -0.10}, {"weight": 0.05}])
    capacity_results = pd.DataFrame([{"fraction_trades_clipped": 0.05}])
    stability_gates = compute_stability_gates(
        predictive_uncertainty=predictive_uncertainty,
        portfolio_uncertainty=portfolio_uncertainty,
        regime_metrics=regime_metrics,
        cost_sensitivity=cost_sensitivity,
        ablation_results=ablation_results,
        holdings_snapshots=holdings_snapshots,
        capacity_results=capacity_results,
    )
    multiple_testing = pd.DataFrame([{"hypothesis_id": "model::ridge", "rejected_fdr": True}])
    approval = summarize_approval_recommendation(
        stability_gates=stability_gates,
        multiple_testing=multiple_testing,
        capability_class="release_candidate",
        release_eligible=True,
    )
    assert approval["status"] == "approved_for_extended_research"
    assert approval["failed_gate_count"] == 0


def test_prediction_correlation_matrix_tracks_model_similarity() -> None:
    frame = pd.DataFrame(
        [
            {"date": pd.Timestamp("2024-01-02"), "security_id": "A", "model_name": "m1", "raw_prediction": 0.1},
            {"date": pd.Timestamp("2024-01-02"), "security_id": "A", "model_name": "m2", "raw_prediction": 0.1},
            {"date": pd.Timestamp("2024-01-02"), "security_id": "B", "model_name": "m1", "raw_prediction": 0.2},
            {"date": pd.Timestamp("2024-01-02"), "security_id": "B", "model_name": "m2", "raw_prediction": 0.2},
        ]
    )
    matrix = compute_prediction_correlation_matrix(frame)
    self_corr = matrix.loc[(matrix["model_name_left"] == "m1") & (matrix["model_name_right"] == "m1"), "prediction_correlation"].iloc[0]
    cross_corr = matrix.loc[(matrix["model_name_left"] == "m1") & (matrix["model_name_right"] == "m2"), "prediction_correlation"].iloc[0]
    assert self_corr == 1.0
    assert cross_corr == 1.0
