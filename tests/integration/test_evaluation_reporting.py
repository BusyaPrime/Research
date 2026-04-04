from __future__ import annotations

import pandas as pd

from alpha_research.config.models import ReportingConfig
from alpha_research.evaluation.metrics import (
    build_decay_response_curve,
    compute_portfolio_metrics,
    compute_predictive_metrics,
    compute_regime_breakdown,
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
        include_sections=["executive_summary", "backtest_results", "capacity_analysis", "regime_analysis", "decay_analysis", "limitations", "next_steps"],
        mandatory_figures=["ic_over_time", "equity_curve_net", "capacity_curve"],
    )
    report = render_final_report(reporting_config, project_name="Alpha Platform", section_payloads={"backtest_results": "Тело бэктеста."})
    assert "## Итог по запуску" in report
    assert "## Результаты бэктеста" in report
    assert "## Анализ capacity" in report
    assert "## Анализ по режимам" in report
    assert "## Анализ затухания сигнала" in report
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
