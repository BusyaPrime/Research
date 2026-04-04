from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

from alpha_research.config.models import PortfolioConfig


def map_scores_to_ranks(frame: pd.DataFrame, score_column: str = "raw_prediction") -> pd.DataFrame:
    output = frame.copy()
    output["score_rank"] = output.groupby("date", dropna=False)[score_column].transform(lambda values: values.rank(method="first", pct=True))
    return output.sort_values([score_column, "security_id"], ascending=[False, True], kind="stable").reset_index(drop=True)


def prepare_portfolio_inputs(
    date: str | pd.Timestamp,
    oof_predictions: pd.DataFrame,
    universe_snapshot: pd.DataFrame,
    feature_panel: pd.DataFrame,
    *,
    model_name: str | None = None,
) -> pd.DataFrame:
    decision_date = pd.Timestamp(date).normalize()
    preds = oof_predictions.copy()
    preds["date"] = pd.to_datetime(preds["date"], errors="coerce").dt.normalize()
    preds = preds.loc[preds["date"] == decision_date].copy()
    if model_name is not None:
        preds = preds.loc[preds["model_name"] == model_name].copy()
    elif "model_name" in preds.columns and preds["model_name"].nunique(dropna=True) > 1:
        raise ValueError("Multiple model_name values present. Specify model_name explicitly.")

    universe = universe_snapshot.copy()
    universe["date"] = pd.to_datetime(universe["date"], errors="coerce").dt.normalize()
    universe = universe.loc[universe["date"] == decision_date].copy()

    features = feature_panel.copy()
    features["date"] = pd.to_datetime(features["date"], errors="coerce").dt.normalize()
    features = features.loc[features["date"] == decision_date, ["date", "security_id", "sector", "beta_estimate", "adv20", "liquidity_bucket"]].copy()
    features = features.rename(columns={"adv20": "adv20_usd_t"})

    merged = preds.merge(universe, on=["date", "security_id"], how="left", suffixes=("", "__universe"))
    merged = merged.merge(features, on=["date", "security_id"], how="left", suffixes=("", "__feature"))
    if "liquidity_bucket__feature" in merged.columns:
        merged["liquidity_bucket"] = merged["liquidity_bucket"].fillna(merged["liquidity_bucket__feature"])
        merged = merged.drop(columns=["liquidity_bucket__feature"])
    if "adv20_usd_t__feature" in merged.columns:
        merged["adv20_usd_t"] = merged["adv20_usd_t"].fillna(merged["adv20_usd_t__feature"])
        merged = merged.drop(columns=["adv20_usd_t__feature"])
    merged["borrow_status"] = merged.get("borrow_status", merged.get("liquidity_bucket", pd.Series("medium", index=merged.index))).fillna("medium")
    return merged


def _side_targets(portfolio_config: PortfolioConfig) -> tuple[float, float]:
    long_gross = (portfolio_config.gross_exposure + portfolio_config.net_target) / 2.0
    short_gross = (portfolio_config.gross_exposure - portfolio_config.net_target) / 2.0
    if long_gross < 0 or short_gross < 0:
        raise ValueError("gross_exposure and net_target imply negative side exposure.")
    return long_gross, short_gross


def _available_sector_net_capacity(sector_net: float, sign: int, max_sector_net: float) -> float:
    if sign > 0:
        return max_sector_net - sector_net if sector_net >= 0 else max_sector_net + abs(sector_net)
    return max_sector_net - abs(sector_net) if sector_net <= 0 else max_sector_net + sector_net


def _allocate_side(
    candidates: pd.DataFrame,
    *,
    sign: int,
    target_gross: float,
    portfolio_config: PortfolioConfig,
    weights: pd.Series,
    sector_gross: dict[str, float],
    sector_net: dict[str, float],
) -> tuple[pd.Series, list[dict[str, object]]]:
    if candidates.empty or target_gross <= 0:
        return weights, []

    rejected: list[dict[str, object]] = []
    remaining = float(target_gross)
    current = candidates.copy().reset_index(drop=True)
    base_weight = target_gross / max(len(current), 1)
    active = current.copy()
    tolerance = 1e-12

    while remaining > tolerance and not active.empty:
        per_name = min(base_weight, remaining / len(active))
        progress = False
        next_active_rows: list[pd.Series] = []
        for _, row in active.iterrows():
            security_id = str(row["security_id"])
            sector = str(row.get("sector", "UNKNOWN"))
            if sign < 0 and portfolio_config.reject_unborrowable_shorts and str(row.get("borrow_status", "")).lower() == "unborrowable":
                rejected.append({"security_id": security_id, "reason": "unborrowable_short"})
                continue

            name_capacity = max(portfolio_config.max_weight_per_name - abs(float(weights.get(security_id, 0.0))), 0.0)
            gross_capacity = max(portfolio_config.max_sector_gross_exposure - sector_gross.get(sector, 0.0), 0.0)
            net_capacity = max(_available_sector_net_capacity(sector_net.get(sector, 0.0), sign, portfolio_config.max_sector_net_exposure), 0.0)
            capacity = min(name_capacity, gross_capacity, net_capacity, remaining)
            allocation = min(per_name, capacity)
            if allocation > tolerance:
                weights.loc[security_id] = float(weights.get(security_id, 0.0)) + sign * allocation
                sector_gross[sector] = sector_gross.get(sector, 0.0) + allocation
                sector_net[sector] = sector_net.get(sector, 0.0) + sign * allocation
                remaining -= allocation
                progress = True
                residual_name_capacity = max(portfolio_config.max_weight_per_name - abs(float(weights.loc[security_id])), 0.0)
                residual_gross_capacity = max(portfolio_config.max_sector_gross_exposure - sector_gross.get(sector, 0.0), 0.0)
                residual_net_capacity = max(_available_sector_net_capacity(sector_net.get(sector, 0.0), sign, portfolio_config.max_sector_net_exposure), 0.0)
                if min(residual_name_capacity, residual_gross_capacity, residual_net_capacity) > tolerance:
                    next_active_rows.append(row)
            else:
                rejected.append({"security_id": security_id, "reason": "capacity_constraint"})
        if not progress:
            break
        active = pd.DataFrame(next_active_rows)
    return weights, rejected


def _heuristic_beta_neutralize(frame: pd.DataFrame, weights: pd.Series, portfolio_config: PortfolioConfig) -> pd.Series:
    if not portfolio_config.beta_neutralize or "beta_estimate" not in frame.columns:
        return weights

    beta_frame = frame[["security_id", "beta_estimate"]].drop_duplicates().set_index("security_id")
    beta = pd.to_numeric(beta_frame["beta_estimate"], errors="coerce").reindex(weights.index).fillna(0.0)
    exposure = float((weights * beta).sum())
    denom = float((beta.pow(2)).sum())
    if denom <= 1e-12 or abs(exposure) <= 1e-10:
        return weights

    # TEMPORARY SIMPLIFICATION: heuristic projection instead of constrained optimizer.
    adjusted = weights - exposure * beta / denom
    gross = adjusted.abs().sum()
    if gross > 0:
        adjusted *= portfolio_config.gross_exposure / gross
    net = adjusted.sum()
    if abs(net - portfolio_config.net_target) > 1e-10:
        offset = (net - portfolio_config.net_target) / max(len(adjusted), 1)
        adjusted -= offset
    return adjusted.clip(lower=-portfolio_config.max_weight_per_name, upper=portfolio_config.max_weight_per_name)


@dataclass(frozen=True)
class TargetBuildResult:
    targets: pd.DataFrame
    rejected: pd.DataFrame


def build_portfolio_targets(
    signal_frame: pd.DataFrame,
    portfolio_config: PortfolioConfig,
    *,
    score_column: str = "raw_prediction",
) -> TargetBuildResult:
    if signal_frame.empty:
        empty_targets = pd.DataFrame(columns=["date", "security_id", "target_weight", "score_rank", "sector", "beta_estimate", "adv20_usd_t", "liquidity_bucket", "borrow_status"])
        empty_rejected = pd.DataFrame(columns=["date", "security_id", "reason"])
        return TargetBuildResult(targets=empty_targets, rejected=empty_rejected)

    frame = signal_frame.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    frame = frame.loc[frame["is_in_universe"].fillna(False)].copy()
    frame = map_scores_to_ranks(frame, score_column=score_column)

    long_gross, short_gross = _side_targets(portfolio_config)
    long_n = max(1, int(math.ceil(len(frame) * portfolio_config.long_quantile)))
    short_n = max(1, int(math.ceil(len(frame) * portfolio_config.short_quantile)))

    longs = frame.nlargest(long_n, score_column, keep="first").copy()
    shorts = frame.nsmallest(short_n, score_column, keep="first").copy()
    if portfolio_config.reject_unborrowable_shorts:
        shorts = shorts.loc[shorts.get("borrow_status", pd.Series("", index=shorts.index)).astype("string").str.lower() != "unborrowable"].copy()

    weight_index = pd.Index(frame["security_id"].astype("string").unique(), dtype="string")
    weights = pd.Series(0.0, index=weight_index, dtype="float64")
    sector_gross: dict[str, float] = {}
    sector_net: dict[str, float] = {}
    rejected_rows: list[dict[str, object]] = []

    weights, rejected_long = _allocate_side(longs, sign=1, target_gross=long_gross, portfolio_config=portfolio_config, weights=weights, sector_gross=sector_gross, sector_net=sector_net)
    weights, rejected_short = _allocate_side(shorts, sign=-1, target_gross=short_gross, portfolio_config=portfolio_config, weights=weights, sector_gross=sector_gross, sector_net=sector_net)
    rejected_rows.extend(rejected_long)
    rejected_rows.extend(rejected_short)

    weights = _heuristic_beta_neutralize(frame, weights, portfolio_config)
    weights = weights.where(weights.abs() > 1e-10, 0.0)

    target = frame[["date", "security_id", "score_rank", "sector", "beta_estimate", "adv20_usd_t", "liquidity_bucket", "borrow_status"]].drop_duplicates("security_id").copy()
    target["target_weight"] = target["security_id"].map(weights).fillna(0.0)
    target = target.sort_values(["target_weight", "security_id"], ascending=[False, True], kind="stable").reset_index(drop=True)

    rejected = pd.DataFrame(rejected_rows)
    if not rejected.empty:
        rejected["date"] = target["date"].iloc[0]
        rejected = rejected[["date", "security_id", "reason"]].drop_duplicates().reset_index(drop=True)
    else:
        rejected = pd.DataFrame(columns=["date", "security_id", "reason"])
    return TargetBuildResult(targets=target, rejected=rejected)
