from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from alpha_research.evaluation.metrics import compute_predictive_metrics

SVG_WIDTH = 960
SVG_HEIGHT = 420
PLOT_LEFT = 70
PLOT_RIGHT = 24
PLOT_TOP = 28
PLOT_BOTTOM = 50
PLOT_WIDTH = SVG_WIDTH - PLOT_LEFT - PLOT_RIGHT
PLOT_HEIGHT = SVG_HEIGHT - PLOT_TOP - PLOT_BOTTOM
SERIES_COLORS = ("#0f766e", "#b45309", "#1d4ed8", "#be123c")


@dataclass(frozen=True)
class RenderedFigure:
    figure_name: str
    path: Path
    notes: list[str]


def _write_svg(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _normalize_points(points: list[tuple[float, float]]) -> str:
    if not points:
        return ""
    x_values = [point[0] for point in points]
    y_values = [point[1] for point in points]
    x_min = min(x_values)
    x_max = max(x_values)
    y_min = min(y_values)
    y_max = max(y_values)
    if x_max == x_min:
        x_max = x_min + 1.0
    if y_max == y_min:
        y_max = y_min + 1.0

    normalized: list[str] = []
    for x_value, y_value in points:
        x_scaled = PLOT_LEFT + ((x_value - x_min) / (x_max - x_min)) * PLOT_WIDTH
        y_scaled = PLOT_TOP + PLOT_HEIGHT - ((y_value - y_min) / (y_max - y_min)) * PLOT_HEIGHT
        normalized.append(f"{x_scaled:.2f},{y_scaled:.2f}")
    return " ".join(normalized)


def _line_chart_svg(
    title: str,
    series: list[tuple[str, list[tuple[float, float]]]],
    *,
    y_label: str,
) -> str:
    legend_rows = []
    polyline_rows = []
    for idx, (name, points) in enumerate(series):
        color = SERIES_COLORS[idx % len(SERIES_COLORS)]
        polyline_rows.append(
            f'<polyline fill="none" stroke="{color}" stroke-width="2.5" points="{_normalize_points(points)}" />'
        )
        legend_rows.append(
            f'<text x="{PLOT_LEFT + idx * 180}" y="18" font-size="12" fill="{color}">{name}</text>'
        )
    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{SVG_WIDTH}" height="{SVG_HEIGHT}" viewBox="0 0 {SVG_WIDTH} {SVG_HEIGHT}">',
            '<rect width="100%" height="100%" fill="#fcfcfb" />',
            f'<text x="{PLOT_LEFT}" y="18" font-size="16" font-weight="700" fill="#111827">{title}</text>',
            *legend_rows,
            f'<line x1="{PLOT_LEFT}" y1="{PLOT_TOP + PLOT_HEIGHT}" x2="{SVG_WIDTH - PLOT_RIGHT}" y2="{PLOT_TOP + PLOT_HEIGHT}" stroke="#cbd5e1" />',
            f'<line x1="{PLOT_LEFT}" y1="{PLOT_TOP}" x2="{PLOT_LEFT}" y2="{PLOT_TOP + PLOT_HEIGHT}" stroke="#cbd5e1" />',
            f'<text x="16" y="{PLOT_TOP + 16}" font-size="12" fill="#475569">{y_label}</text>',
            *polyline_rows,
            "</svg>\n",
        ]
    )


def _bar_chart_svg(title: str, items: list[tuple[str, float]], *, y_label: str) -> str:
    values = [value for _, value in items] or [0.0]
    max_value = max(values) if values else 1.0
    if max_value <= 0:
        max_value = 1.0
    bar_width = PLOT_WIDTH / max(len(items), 1)
    bars = []
    labels = []
    for idx, (label, value) in enumerate(items):
        height = (value / max_value) * PLOT_HEIGHT if max_value else 0.0
        x = PLOT_LEFT + idx * bar_width + 8
        y = PLOT_TOP + PLOT_HEIGHT - height
        bars.append(
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{max(bar_width - 16, 20):.2f}" height="{max(height, 1):.2f}" fill="#0f766e" opacity="0.85" />'
        )
        labels.append(
            f'<text x="{x + max(bar_width - 16, 20) / 2:.2f}" y="{PLOT_TOP + PLOT_HEIGHT + 18}" text-anchor="middle" font-size="10" fill="#334155">{label}</text>'
        )
    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{SVG_WIDTH}" height="{SVG_HEIGHT}" viewBox="0 0 {SVG_WIDTH} {SVG_HEIGHT}">',
            '<rect width="100%" height="100%" fill="#fcfcfb" />',
            f'<text x="{PLOT_LEFT}" y="18" font-size="16" font-weight="700" fill="#111827">{title}</text>',
            f'<line x1="{PLOT_LEFT}" y1="{PLOT_TOP + PLOT_HEIGHT}" x2="{SVG_WIDTH - PLOT_RIGHT}" y2="{PLOT_TOP + PLOT_HEIGHT}" stroke="#cbd5e1" />',
            f'<line x1="{PLOT_LEFT}" y1="{PLOT_TOP}" x2="{PLOT_LEFT}" y2="{PLOT_TOP + PLOT_HEIGHT}" stroke="#cbd5e1" />',
            f'<text x="16" y="{PLOT_TOP + 16}" font-size="12" fill="#475569">{y_label}</text>',
            *bars,
            *labels,
            "</svg>\n",
        ]
    )


def _heatmap_svg(title: str, frame: pd.DataFrame, *, value_column: str) -> str:
    if frame.empty:
        return _bar_chart_svg(title, [("empty", 0.0)], y_label=value_column)
    pivot = frame.pivot(index="row_key", columns="col_key", values=value_column).fillna(0.0)
    rows = list(pivot.index)
    cols = list(pivot.columns)
    min_value = float(pivot.min().min())
    max_value = float(pivot.max().max())
    span = max(max_value - min_value, 1e-9)
    cell_width = PLOT_WIDTH / max(len(cols), 1)
    cell_height = PLOT_HEIGHT / max(len(rows), 1)
    cells = []
    row_labels = []
    col_labels = []
    for row_idx, row_name in enumerate(rows):
        y = PLOT_TOP + row_idx * cell_height
        row_labels.append(
            f'<text x="10" y="{y + cell_height / 2:.2f}" font-size="10" fill="#334155">{row_name}</text>'
        )
        for col_idx, col_name in enumerate(cols):
            value = float(pivot.loc[row_name, col_name])
            intensity = (value - min_value) / span
            red = int(245 - 150 * intensity)
            green = int(248 - 60 * intensity)
            blue = int(250 - 180 * intensity)
            x = PLOT_LEFT + col_idx * cell_width
            cells.append(
                f'<rect x="{x:.2f}" y="{y:.2f}" width="{cell_width:.2f}" height="{cell_height:.2f}" fill="rgb({red},{green},{blue})" stroke="#ffffff" />'
            )
    for col_idx, col_name in enumerate(cols):
        x = PLOT_LEFT + col_idx * cell_width + cell_width / 2
        col_labels.append(
            f'<text x="{x:.2f}" y="{PLOT_TOP + PLOT_HEIGHT + 16}" text-anchor="middle" font-size="9" fill="#334155">{col_name}</text>'
        )
    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{SVG_WIDTH}" height="{SVG_HEIGHT}" viewBox="0 0 {SVG_WIDTH} {SVG_HEIGHT}">',
            '<rect width="100%" height="100%" fill="#fcfcfb" />',
            f'<text x="{PLOT_LEFT}" y="18" font-size="16" font-weight="700" fill="#111827">{title}</text>',
            *cells,
            *row_labels,
            *col_labels,
            "</svg>\n",
        ]
    )


def _equity_and_drawdown(backtest_daily_state: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    state = backtest_daily_state.copy().sort_values("date", kind="stable").reset_index(drop=True)
    previous_aum = state["aum"].shift(1)
    if not state.empty:
        previous_aum.iloc[0] = float(state.loc[0, "aum"] - state.loc[0, "net_pnl"])
    state["gross_return"] = pd.to_numeric(state["gross_pnl"], errors="coerce") / previous_aum.replace(0.0, np.nan)
    state["net_return"] = pd.to_numeric(state["net_pnl"], errors="coerce") / previous_aum.replace(0.0, np.nan)
    state["gross_curve"] = (1.0 + state["gross_return"].fillna(0.0)).cumprod()
    state["net_curve"] = (1.0 + state["net_return"].fillna(0.0)).cumprod()
    running_peak = state["net_curve"].cummax()
    drawdown = state[["date"]].copy()
    drawdown["drawdown"] = state["net_curve"] / running_peak - 1.0
    return state, drawdown


def render_mandatory_figures(
    output_dir: Path,
    *,
    requested_figures: list[str],
    universe_snapshot: pd.DataFrame,
    feature_panel: pd.DataFrame,
    predictions: pd.DataFrame,
    labels: pd.DataFrame,
    backtest_daily_state: pd.DataFrame,
    capacity_results: pd.DataFrame,
    decay_curve: pd.DataFrame,
) -> list[RenderedFigure]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rendered: list[RenderedFigure] = []
    label_column = next((column for column in labels.columns if column.startswith("label_")), None)
    predictive_metrics = (
        compute_predictive_metrics(predictions, labels[["date", "security_id", label_column]], label_column=label_column)
        if label_column is not None and not predictions.empty
        else pd.DataFrame(columns=["date", "ic", "rank_ic"])
    )
    predictive_daily = predictive_metrics.loc[predictive_metrics["date"].notna()].copy()
    predictive_daily["rolling_rank_ic"] = pd.to_numeric(predictive_daily["rank_ic"], errors="coerce").rolling(21, min_periods=3).mean()
    equity_frame, drawdown_frame = _equity_and_drawdown(backtest_daily_state)

    universe_size = (
        universe_snapshot.loc[universe_snapshot["is_in_universe"].fillna(False)]
        .groupby("date", sort=True)
        .size()
        .reset_index(name="value")
    )
    coverage_heatmap = feature_panel.copy()
    coverage_heatmap["month"] = pd.to_datetime(coverage_heatmap["date"], errors="coerce").dt.strftime("%Y-%m")
    coverage_heatmap = (
        coverage_heatmap.groupby(["sector", "month"], dropna=False)["feature_coverage_ratio"]
        .mean()
        .reset_index()
        .rename(columns={"sector": "row_key", "month": "col_key"})
    )
    if coverage_heatmap["col_key"].nunique(dropna=True) > 12:
        keep_months = sorted(coverage_heatmap["col_key"].dropna().unique().tolist())[-12:]
        coverage_heatmap = coverage_heatmap.loc[coverage_heatmap["col_key"].isin(keep_months)].copy()

    cost_columns = [
        "commission_cost",
        "spread_cost",
        "slippage_cost",
        "impact_cost",
        "borrow_cost",
    ]
    cost_items = [
        (column.replace("_cost", ""), float(pd.to_numeric(backtest_daily_state[column], errors="coerce").sum()))
        for column in cost_columns
        if column in backtest_daily_state.columns
    ]
    capacity_base = capacity_results.loc[capacity_results["scenario"] == "base"].copy()
    if capacity_base.empty:
        capacity_base = capacity_results.copy()
    capacity_base = capacity_base.sort_values("aum_level", kind="stable")
    decay_top = decay_curve.sort_values(["horizon_days", "prediction_bucket"], kind="stable").groupby("horizon_days").tail(1)
    decay_bottom = decay_curve.sort_values(["horizon_days", "prediction_bucket"], kind="stable").groupby("horizon_days").head(1)

    figure_builders: dict[str, tuple[str, str]] = {
        "universe_size_over_time": (
            "Число бумаг в PIT-universe",
            _line_chart_svg(
                "Число бумаг в PIT-universe",
                [("universe_size", list(enumerate(pd.to_numeric(universe_size["value"], errors="coerce").fillna(0.0).tolist())))],
                y_label="count",
            ),
        ),
        "coverage_heatmap": (
            "Покрытие фич по секторам",
            _heatmap_svg("Покрытие фич по секторам", coverage_heatmap, value_column="feature_coverage_ratio"),
        ),
        "ic_over_time": (
            "IC по времени",
            _line_chart_svg(
                "IC по времени",
                [
                    ("ic", list(enumerate(pd.to_numeric(predictive_daily["ic"], errors="coerce").fillna(0.0).tolist()))),
                    ("rank_ic", list(enumerate(pd.to_numeric(predictive_daily["rank_ic"], errors="coerce").fillna(0.0).tolist()))),
                ],
                y_label="ic",
            ),
        ),
        "rolling_ic": (
            "Rolling rank IC",
            _line_chart_svg(
                "Rolling rank IC",
                [("rolling_rank_ic", list(enumerate(pd.to_numeric(predictive_daily["rolling_rank_ic"], errors="coerce").fillna(0.0).tolist())))],
                y_label="rank_ic",
            ),
        ),
        "equity_curve_gross": (
            "Gross equity curve",
            _line_chart_svg(
                "Gross equity curve",
                [("gross_curve", list(enumerate(pd.to_numeric(equity_frame["gross_curve"], errors="coerce").fillna(1.0).tolist())))],
                y_label="equity",
            ),
        ),
        "equity_curve_net": (
            "Net equity curve",
            _line_chart_svg(
                "Net equity curve",
                [("net_curve", list(enumerate(pd.to_numeric(equity_frame["net_curve"], errors="coerce").fillna(1.0).tolist())))],
                y_label="equity",
            ),
        ),
        "drawdown_curve": (
            "Drawdown curve",
            _line_chart_svg(
                "Drawdown curve",
                [("drawdown", list(enumerate(pd.to_numeric(drawdown_frame["drawdown"], errors="coerce").fillna(0.0).tolist())))],
                y_label="drawdown",
            ),
        ),
        "turnover_curve": (
            "Turnover",
            _line_chart_svg(
                "Turnover",
                [("turnover", list(enumerate(pd.to_numeric(backtest_daily_state["turnover"], errors="coerce").fillna(0.0).tolist())))],
                y_label="turnover",
            ),
        ),
        "cost_decomposition": (
            "Cost decomposition",
            _bar_chart_svg("Cost decomposition", cost_items or [("empty", 0.0)], y_label="usd"),
        ),
        "exposure_curve": (
            "Exposure curve",
            _line_chart_svg(
                "Exposure curve",
                [
                    ("gross_exposure", list(enumerate(pd.to_numeric(backtest_daily_state["gross_exposure"], errors="coerce").fillna(0.0).tolist()))),
                    ("net_exposure", list(enumerate(pd.to_numeric(backtest_daily_state["net_exposure"], errors="coerce").fillna(0.0).tolist()))),
                ],
                y_label="exposure",
            ),
        ),
        "capacity_curve": (
            "Capacity curve",
            _line_chart_svg(
                "Capacity curve",
                [("net_sharpe", list(zip(pd.to_numeric(capacity_base["aum_level"], errors="coerce").fillna(0.0).tolist(), pd.to_numeric(capacity_base["net_sharpe"], errors="coerce").fillna(0.0).tolist())))],
                y_label="net_sharpe",
            ),
        ),
        "decay_curve": (
            "Decay curve",
            _line_chart_svg(
                "Decay curve",
                [
                    ("top_bucket", list(zip(pd.to_numeric(decay_top["horizon_days"], errors="coerce").fillna(0.0).tolist(), pd.to_numeric(decay_top["mean_response"], errors="coerce").fillna(0.0).tolist()))),
                    ("bottom_bucket", list(zip(pd.to_numeric(decay_bottom["horizon_days"], errors="coerce").fillna(0.0).tolist(), pd.to_numeric(decay_bottom["mean_response"], errors="coerce").fillna(0.0).tolist()))),
                ],
                y_label="response",
            ),
        ),
    }

    for figure_name in requested_figures:
        title, svg = figure_builders[figure_name]
        path = _write_svg(output_dir / f"{figure_name}.svg", svg)
        rendered.append(RenderedFigure(figure_name=figure_name, path=path, notes=[title]))
    return rendered
