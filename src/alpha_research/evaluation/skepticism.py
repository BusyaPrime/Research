from __future__ import annotations

from statistics import NormalDist

import numpy as np
import pandas as pd

from alpha_research.evaluation.metrics import compute_predictive_metrics

_NORMAL = NormalDist()


def _safe_float(value: float | int | np.floating | None) -> float:
    if value is None:
        return float("nan")
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _finite_series(values: pd.Series | np.ndarray) -> np.ndarray:
    array = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(dtype="float64")
    return array[np.isfinite(array)]


def _block_bootstrap_samples(
    values: np.ndarray,
    *,
    draws: int,
    block_size: int,
    seed: int,
) -> np.ndarray:
    clean = values[np.isfinite(values)]
    if len(clean) == 0:
        return np.asarray([], dtype="float64")
    if len(clean) == 1:
        return np.repeat(clean[0], draws)

    rng = np.random.default_rng(seed)
    effective_block = max(1, min(int(block_size), len(clean)))
    samples = np.empty(draws, dtype="float64")
    for draw in range(draws):
        indices: list[int] = []
        while len(indices) < len(clean):
            start = int(rng.integers(0, len(clean)))
            indices.extend(((start + offset) % len(clean)) for offset in range(effective_block))
        sample = clean[np.asarray(indices[: len(clean)], dtype="int64")]
        samples[draw] = float(np.mean(sample))
    return samples


def _bootstrap_sharpe_distribution(
    values: np.ndarray,
    *,
    draws: int,
    block_size: int,
    seed: int,
) -> np.ndarray:
    clean = values[np.isfinite(values)]
    if len(clean) == 0:
        return np.asarray([], dtype="float64")
    if len(clean) == 1:
        return np.asarray([float("nan")] * draws, dtype="float64")

    rng = np.random.default_rng(seed)
    effective_block = max(1, min(int(block_size), len(clean)))
    distribution = np.empty(draws, dtype="float64")
    for draw in range(draws):
        indices: list[int] = []
        while len(indices) < len(clean):
            start = int(rng.integers(0, len(clean)))
            indices.extend(((start + offset) % len(clean)) for offset in range(effective_block))
        sample = clean[np.asarray(indices[: len(clean)], dtype="int64")]
        std = float(np.std(sample, ddof=0))
        distribution[draw] = float(np.mean(sample) / std * np.sqrt(252.0)) if std > 1e-12 else float("nan")
    return distribution


def _mean_ci(values: np.ndarray, *, draws: int, block_size: int, seed: int) -> tuple[float, float, float]:
    clean = values[np.isfinite(values)]
    if len(clean) == 0:
        return float("nan"), float("nan"), float("nan")
    mean_value = float(np.mean(clean))
    bootstrap = _block_bootstrap_samples(clean, draws=draws, block_size=block_size, seed=seed)
    if len(bootstrap) == 0:
        return mean_value, float("nan"), float("nan")
    lower = float(np.quantile(bootstrap, 0.025))
    upper = float(np.quantile(bootstrap, 0.975))
    return mean_value, lower, upper


def _sample_skew(values: np.ndarray) -> float:
    clean = values[np.isfinite(values)]
    if len(clean) < 3:
        return float("nan")
    centered = clean - clean.mean()
    std = clean.std(ddof=0)
    if std <= 1e-12:
        return 0.0
    return float(np.mean((centered / std) ** 3))


def _sample_kurtosis(values: np.ndarray) -> float:
    clean = values[np.isfinite(values)]
    if len(clean) < 4:
        return float("nan")
    centered = clean - clean.mean()
    std = clean.std(ddof=0)
    if std <= 1e-12:
        return 3.0
    return float(np.mean((centered / std) ** 4))


def _one_sided_mean_pvalue(values: np.ndarray) -> float:
    clean = values[np.isfinite(values)]
    if len(clean) < 2:
        return float("nan")
    std = clean.std(ddof=1)
    if std <= 1e-12:
        return 0.0 if clean.mean() > 0 else 1.0
    z_score = float(clean.mean() / (std / np.sqrt(len(clean))))
    return float(1.0 - _NORMAL.cdf(z_score))


def _daily_predictive_rows(predictions: pd.DataFrame, labels: pd.DataFrame, *, label_column: str) -> pd.DataFrame:
    metrics = compute_predictive_metrics(predictions, labels, label_column=label_column)
    daily_rows = metrics.loc[metrics["metric"].isna()].copy()
    if daily_rows.empty:
        return pd.DataFrame(columns=["date", "ic", "rank_ic"])
    daily_rows["date"] = pd.to_datetime(daily_rows["date"], errors="coerce").dt.normalize()
    return daily_rows[["date", "ic", "rank_ic"]].sort_values("date", kind="stable").reset_index(drop=True)


def compute_predictive_uncertainty(
    predictions: pd.DataFrame,
    labels: pd.DataFrame,
    *,
    label_column: str,
    bootstrap_draws: int = 300,
    bootstrap_block_size: int = 20,
    seed: int = 42,
) -> pd.DataFrame:
    daily_rows = _daily_predictive_rows(predictions, labels, label_column=label_column)
    rank_ic_values = _finite_series(daily_rows["rank_ic"])
    ic_values = _finite_series(daily_rows["ic"])
    rank_ic_mean, rank_ic_ci_lower, rank_ic_ci_upper = _mean_ci(
        rank_ic_values,
        draws=bootstrap_draws,
        block_size=bootstrap_block_size,
        seed=seed,
    )
    ic_mean, ic_ci_lower, ic_ci_upper = _mean_ci(
        ic_values,
        draws=bootstrap_draws,
        block_size=bootstrap_block_size,
        seed=seed + 1,
    )
    rows = [
        {"metric": "ic_mean", "value": ic_mean},
        {"metric": "ic_ci_lower", "value": ic_ci_lower},
        {"metric": "ic_ci_upper", "value": ic_ci_upper},
        {"metric": "rank_ic_mean", "value": rank_ic_mean},
        {"metric": "rank_ic_ci_lower", "value": rank_ic_ci_lower},
        {"metric": "rank_ic_ci_upper", "value": rank_ic_ci_upper},
        {"metric": "rank_ic_positive_fraction", "value": float(np.mean(rank_ic_values > 0.0)) if len(rank_ic_values) else float("nan")},
        {"metric": "rank_ic_p_value", "value": _one_sided_mean_pvalue(rank_ic_values)},
        {"metric": "sample_size_days", "value": float(len(rank_ic_values))},
    ]
    return pd.DataFrame(rows)


def _daily_net_returns(daily_state: pd.DataFrame, *, initial_aum: float | None = None) -> np.ndarray:
    state = daily_state.copy().sort_values("date", kind="stable").reset_index(drop=True)
    if state.empty:
        return np.asarray([], dtype="float64")
    previous_aum = pd.Series(state["aum"].shift(1), index=state.index, dtype="float64")
    previous_aum.iloc[0] = float(initial_aum if initial_aum is not None else state.loc[0, "aum"] - state.loc[0, "net_pnl"])
    returns = pd.to_numeric(state["net_pnl"], errors="coerce") / previous_aum.replace(0.0, np.nan)
    return returns.fillna(0.0).to_numpy(dtype="float64")


def probabilistic_sharpe_ratio(
    returns: np.ndarray,
    *,
    benchmark_sharpe: float = 0.0,
) -> float:
    clean = returns[np.isfinite(returns)]
    if len(clean) < 2:
        return float("nan")
    std = clean.std(ddof=0)
    if std <= 1e-12:
        return float(clean.mean() > 0.0)
    sharpe = float(clean.mean() / std * np.sqrt(252.0))
    skew = _sample_skew(clean)
    kurt = _sample_kurtosis(clean)
    denominator = 1.0 - (0.0 if np.isnan(skew) else skew) * sharpe + (((0.0 if np.isnan(kurt) else kurt) - 1.0) / 4.0) * (sharpe**2)
    if denominator <= 1e-12:
        return float("nan")
    statistic = (sharpe - benchmark_sharpe) * np.sqrt(max(len(clean) - 1, 1)) / np.sqrt(denominator)
    return float(_NORMAL.cdf(statistic))


def deflated_sharpe_ratio(
    returns: np.ndarray,
    *,
    trial_count: int,
) -> float:
    clean = returns[np.isfinite(returns)]
    if len(clean) < 2:
        return float("nan")
    std = clean.std(ddof=0)
    if std <= 1e-12:
        return float(clean.mean() > 0.0)
    sharpe = float(clean.mean() / std * np.sqrt(252.0))
    skew = _sample_skew(clean)
    kurt = _sample_kurtosis(clean)
    denominator = 1.0 - (0.0 if np.isnan(skew) else skew) * sharpe + (((0.0 if np.isnan(kurt) else kurt) - 1.0) / 4.0) * (sharpe**2)
    if denominator <= 1e-12:
        return float("nan")
    sr_std = float(np.sqrt(denominator / max(len(clean) - 1, 1)))
    effective_trials = max(int(trial_count), 1)
    if effective_trials == 1:
        benchmark_sharpe = 0.0
    else:
        benchmark_sharpe = sr_std * (
            (1.0 - 0.5772156649) * _NORMAL.inv_cdf(1.0 - 1.0 / effective_trials)
            + 0.5772156649 * _NORMAL.inv_cdf(1.0 - 1.0 / (effective_trials * np.e))
        )
    statistic = (sharpe - benchmark_sharpe) * np.sqrt(max(len(clean) - 1, 1)) / np.sqrt(denominator)
    return float(_NORMAL.cdf(statistic))


def compute_portfolio_uncertainty(
    daily_state: pd.DataFrame,
    *,
    initial_aum: float | None = None,
    bootstrap_draws: int = 300,
    bootstrap_block_size: int = 20,
    seed: int = 42,
    trial_count: int = 1,
) -> pd.DataFrame:
    returns = _daily_net_returns(daily_state, initial_aum=initial_aum)
    if len(returns) == 0:
        return pd.DataFrame(columns=["metric", "value"])
    std = float(np.std(returns, ddof=0))
    sharpe = float(np.mean(returns) / std * np.sqrt(252.0)) if std > 1e-12 else float("nan")
    sharpe_bootstrap = _bootstrap_sharpe_distribution(
        returns,
        draws=bootstrap_draws,
        block_size=bootstrap_block_size,
        seed=seed,
    )
    if len(sharpe_bootstrap):
        sharpe_ci_lower = float(np.nanquantile(sharpe_bootstrap, 0.025))
        sharpe_ci_upper = float(np.nanquantile(sharpe_bootstrap, 0.975))
    else:
        sharpe_ci_lower = float("nan")
        sharpe_ci_upper = float("nan")
    rows = [
        {"metric": "net_sharpe", "value": sharpe},
        {"metric": "net_sharpe_ci_lower", "value": sharpe_ci_lower},
        {"metric": "net_sharpe_ci_upper", "value": sharpe_ci_upper},
        {"metric": "probabilistic_sharpe_ratio", "value": probabilistic_sharpe_ratio(returns)},
        {"metric": "deflated_sharpe_ratio", "value": deflated_sharpe_ratio(returns, trial_count=trial_count)},
        {"metric": "effective_trial_count", "value": float(max(trial_count, 1))},
        {"metric": "return_skewness", "value": _sample_skew(returns)},
        {"metric": "return_kurtosis", "value": _sample_kurtosis(returns)},
        {"metric": "sample_size_days", "value": float(len(returns))},
    ]
    return pd.DataFrame(rows)


def build_model_hypothesis_registry(
    predictions: pd.DataFrame,
    labels: pd.DataFrame,
    *,
    label_column: str,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for model_name in sorted(predictions["model_name"].dropna().astype("string").unique()):
        model_predictions = predictions.loc[predictions["model_name"] == model_name].copy()
        daily_rows = _daily_predictive_rows(model_predictions, labels, label_column=label_column)
        rank_ic_values = _finite_series(daily_rows["rank_ic"])
        rows.append(
            {
                "hypothesis_id": f"model::{model_name}",
                "family": "model_family",
                "model_name": str(model_name),
                "rank_ic_mean": float(np.mean(rank_ic_values)) if len(rank_ic_values) else float("nan"),
                "sample_size_days": int(len(rank_ic_values)),
                "p_value": _one_sided_mean_pvalue(rank_ic_values),
            }
        )
    return pd.DataFrame(rows)


def compute_multiple_testing_diagnostics(
    hypotheses: pd.DataFrame,
    *,
    fdr_level: float = 0.10,
    effective_trial_count: int | None = None,
) -> pd.DataFrame:
    if hypotheses.empty:
        return pd.DataFrame(columns=["hypothesis_id", "family", "p_value", "bh_rank", "bh_threshold", "rejected_fdr"])

    frame = hypotheses.copy().sort_values(["family", "p_value", "hypothesis_id"], kind="stable").reset_index(drop=True)
    frame["bh_rank"] = frame.groupby("family", sort=False).cumcount() + 1
    family_sizes = frame.groupby("family", sort=False)["hypothesis_id"].transform("count")
    frame["bh_threshold"] = frame["bh_rank"] / family_sizes * float(fdr_level)
    frame["rejected_fdr"] = pd.to_numeric(frame["p_value"], errors="coerce") <= pd.to_numeric(frame["bh_threshold"], errors="coerce")
    if effective_trial_count is not None:
        frame["effective_trial_count"] = int(max(effective_trial_count, 1))
    return frame


def compute_prediction_correlation_matrix(predictions: pd.DataFrame) -> pd.DataFrame:
    frame = predictions.copy()
    if frame.empty:
        return pd.DataFrame(columns=["model_name_left", "model_name_right", "prediction_correlation"])
    wide = (
        frame.pivot_table(index=["date", "security_id"], columns="model_name", values="raw_prediction", aggfunc="first")
        .sort_index(axis=1)
        .sort_index()
    )
    if wide.empty:
        return pd.DataFrame(columns=["model_name_left", "model_name_right", "prediction_correlation"])
    corr = wide.corr()
    rows: list[dict[str, object]] = []
    for left_name in corr.index:
        for right_name in corr.columns:
            rows.append(
                {
                    "model_name_left": left_name,
                    "model_name_right": right_name,
                    "prediction_correlation": corr.loc[left_name, right_name],
                }
            )
    return pd.DataFrame(rows)


def compute_stability_gates(
    *,
    predictive_uncertainty: pd.DataFrame,
    portfolio_uncertainty: pd.DataFrame,
    regime_metrics: pd.DataFrame,
    cost_sensitivity: pd.DataFrame,
    ablation_results: pd.DataFrame,
    holdings_snapshots: pd.DataFrame,
    capacity_results: pd.DataFrame,
) -> pd.DataFrame:
    predictive_map = predictive_uncertainty.set_index("metric")["value"].to_dict() if not predictive_uncertainty.empty else {}
    portfolio_map = portfolio_uncertainty.set_index("metric")["value"].to_dict() if not portfolio_uncertainty.empty else {}

    rank_ic_lower = _safe_float(predictive_map.get("rank_ic_ci_lower"))
    dsr = _safe_float(portfolio_map.get("deflated_sharpe_ratio"))
    regime_floor = float(pd.to_numeric(regime_metrics.get("ic"), errors="coerce").min()) if not regime_metrics.empty else float("nan")

    stressed_rows = cost_sensitivity.loc[cost_sensitivity["scenario"].astype("string").str.contains("stress", case=False, na=False)].copy()
    stressed_sharpe = float(pd.to_numeric(stressed_rows["net_sharpe"], errors="coerce").min()) if not stressed_rows.empty else float("nan")
    base_rows = cost_sensitivity.loc[cost_sensitivity["scenario"].astype("string") == "base"].copy()
    base_sharpe = float(pd.to_numeric(base_rows["net_sharpe"], errors="coerce").max()) if not base_rows.empty else float("nan")

    worst_ablation_delta = float(pd.to_numeric(ablation_results.get("delta_rank_ic_mean"), errors="coerce").min()) if not ablation_results.empty else float("nan")
    max_weight = float(pd.to_numeric(holdings_snapshots.get("weight"), errors="coerce").abs().max()) if not holdings_snapshots.empty else float("nan")
    clipped_fraction = float(pd.to_numeric(capacity_results.get("fraction_trades_clipped"), errors="coerce").max()) if not capacity_results.empty else float("nan")

    gates = [
        {
            "gate_name": "predictive_floor",
            "passed": bool(np.isnan(rank_ic_lower) or rank_ic_lower >= -0.01),
            "observed_value": rank_ic_lower,
            "threshold": -0.01,
            "failure_reason": "rank_ic нижняя граница ушла слишком глубоко в отрицательную зону.",
        },
        {
            "gate_name": "deflated_sharpe",
            "passed": bool(np.isnan(dsr) or dsr >= 0.5),
            "observed_value": dsr,
            "threshold": 0.5,
            "failure_reason": "deflated sharpe слишком слабый, selection bias все еще может рулить результатом.",
        },
        {
            "gate_name": "regime_balance",
            "passed": bool(np.isnan(regime_floor) or regime_floor >= -0.10),
            "observed_value": regime_floor,
            "threshold": -0.10,
            "failure_reason": "alpha разваливается в одном из рыночных режимов.",
        },
        {
            "gate_name": "cost_robustness",
            "passed": bool(np.isnan(stressed_sharpe) or np.isnan(base_sharpe) or stressed_sharpe >= min(0.0, base_sharpe * 0.5)),
            "observed_value": stressed_sharpe,
            "threshold": min(0.0, base_sharpe * 0.5) if np.isfinite(base_sharpe) else float("nan"),
            "failure_reason": "стратегия слишком хрупкая к умеренному ужесточению cost assumptions.",
        },
        {
            "gate_name": "ablation_resilience",
            "passed": bool(np.isnan(worst_ablation_delta) or worst_ablation_delta >= -0.05),
            "observed_value": worst_ablation_delta,
            "threshold": -0.05,
            "failure_reason": "результат слишком сильно зависит от одного куска feature/preprocessing контура.",
        },
        {
            "gate_name": "position_concentration",
            "passed": bool(np.isnan(max_weight) or max_weight <= 0.25),
            "observed_value": max_weight,
            "threshold": 0.25,
            "failure_reason": "слишком высокая концентрация в одной позиции.",
        },
        {
            "gate_name": "capacity_clip",
            "passed": bool(np.isnan(clipped_fraction) or clipped_fraction <= 0.25),
            "observed_value": clipped_fraction,
            "threshold": 0.25,
            "failure_reason": "capacity layer слишком часто режет сделки по participation limits.",
        },
    ]
    return pd.DataFrame(gates)


def summarize_approval_recommendation(
    *,
    stability_gates: pd.DataFrame,
    multiple_testing: pd.DataFrame,
    capability_class: str,
    release_eligible: bool,
) -> dict[str, object]:
    failed = stability_gates.loc[~stability_gates["passed"].fillna(False)].copy()
    any_significant = False
    if not multiple_testing.empty and "rejected_fdr" in multiple_testing.columns:
        any_significant = bool(multiple_testing["rejected_fdr"].fillna(False).any())

    if not release_eligible:
        status = "not_release_eligible"
        reason = f"runtime capability `{capability_class}` не допускает release-grade handoff."
    elif not any_significant:
        status = "rejected_due_to_instability"
        reason = "после FDR-контроля не осталось убедительных гипотез."
    elif not failed.empty:
        status = "rejected_due_to_instability"
        reason = "; ".join(failed["failure_reason"].astype("string").tolist())
    else:
        status = "approved_for_extended_research"
        reason = "основные stability gates пройдены, гипотеза пережила базовый skepticism layer."

    return {
        "status": status,
        "reason": reason,
        "failed_gate_count": int(len(failed)),
        "failed_gates": failed["gate_name"].astype("string").tolist(),
        "significant_hypothesis_count": int(multiple_testing["rejected_fdr"].fillna(False).sum()) if "rejected_fdr" in multiple_testing.columns else 0,
    }
