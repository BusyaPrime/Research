from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from alpha_research.config.models import UniverseConfig
from alpha_research.data.schemas import validate_dataframe

EXCLUSION_ORDER = (
    ("security_type", "excluded_security_type"),
    ("listing_status", "inactive_listing"),
    ("exchange", "exchange_not_allowed"),
    ("price", "price_below_min"),
    ("adv20", "adv20_below_min"),
    ("feature_coverage", "feature_coverage_below_min"),
    ("quality", "data_quality_below_min"),
)


def _compute_adv20(silver_market: pd.DataFrame) -> pd.DataFrame:
    frame = silver_market.copy().sort_values(["security_id", "trade_date"], kind="stable")
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.normalize()
    frame["adv20_usd_t"] = (
        frame.groupby("security_id")["dollar_volume"]
        .transform(lambda values: values.rolling(window=20, min_periods=1).mean())
    )
    return frame


def _assign_liquidity_buckets(snapshot: pd.DataFrame) -> pd.Series:
    included = snapshot["is_in_universe"] & snapshot["adv20_usd_t"].notna()
    if included.sum() == 0:
        return pd.Series(pd.NA, index=snapshot.index, dtype="string")

    percentile = snapshot.loc[included, "adv20_usd_t"].rank(method="first", pct=True)
    buckets = pd.Series(pd.NA, index=snapshot.index, dtype="string")
    buckets.loc[percentile.index[percentile <= 0.3]] = "low"
    buckets.loc[percentile.index[(percentile > 0.3) & (percentile < 0.7)]] = "medium"
    buckets.loc[percentile.index[percentile >= 0.7]] = "high"
    return buckets


def _apply_universe_filters(
    snapshot: pd.DataFrame,
    snapshot_date: pd.Timestamp,
    universe_config: UniverseConfig,
) -> pd.DataFrame:
    snapshot = snapshot.copy()
    snapshot["feature_coverage_ratio"] = pd.to_numeric(snapshot["feature_coverage_ratio"], errors="coerce")
    snapshot["data_quality_score"] = pd.to_numeric(snapshot["data_quality_score"], errors="coerce")
    snapshot["price_t"] = pd.to_numeric(snapshot["price_t"], errors="coerce")
    snapshot["adv20_usd_t"] = pd.to_numeric(snapshot["adv20_usd_t"], errors="coerce")

    checks = {
        "security_type": (
            snapshot["is_common_stock"].fillna(False)
            & snapshot["security_type"].isin(universe_config.eligible_security_types)
            & ~snapshot["security_type"].isin(universe_config.excluded_security_types)
        ),
        "listing_status": (
            (snapshot["listing_date"].isna() | (snapshot["listing_date"] <= snapshot_date))
            & (snapshot["delisting_date"].isna() | (snapshot["delisting_date"] >= snapshot_date))
        ),
        "exchange": snapshot["exchange"].isin(universe_config.allowed_exchanges),
        "price": snapshot["price_t"] >= universe_config.min_price_usd,
        "adv20": snapshot["adv20_usd_t"] >= universe_config.min_adv20_usd,
        "feature_coverage": snapshot["feature_coverage_ratio"] >= universe_config.min_feature_coverage_ratio,
        "quality": snapshot["data_quality_score"] >= universe_config.min_data_quality_score,
    }

    snapshot["is_in_universe"] = True
    snapshot["exclusion_reason_code"] = pd.Series(pd.NA, index=snapshot.index, dtype="string")
    for check_name, reason_code in EXCLUSION_ORDER:
        mask = ~checks[check_name]
        snapshot.loc[mask & snapshot["exclusion_reason_code"].isna(), "exclusion_reason_code"] = reason_code
        snapshot.loc[mask, "is_in_universe"] = False

    snapshot["liquidity_bucket"] = _assign_liquidity_buckets(snapshot)
    return snapshot


@dataclass(frozen=True)
class UniverseBuildResult:
    snapshot: pd.DataFrame
    diagnostics: pd.DataFrame


def build_universe_snapshot(
    date: str | pd.Timestamp,
    security_master: pd.DataFrame,
    silver_market: pd.DataFrame,
    universe_config: UniverseConfig,
    *,
    feature_coverage: pd.DataFrame | None = None,
) -> UniverseBuildResult:
    snapshot_date = pd.Timestamp(date).normalize()
    result = build_universe_snapshots(
        security_master,
        silver_market,
        universe_config,
        dates=[snapshot_date],
        feature_coverage=feature_coverage,
    )
    validated = result.snapshot
    diagnostics = (
        validated.groupby(["is_in_universe", "exclusion_reason_code"], dropna=False)
        .size()
        .rename("row_count")
        .reset_index()
        .sort_values(["is_in_universe", "exclusion_reason_code"], kind="stable")
    )
    return UniverseBuildResult(snapshot=validated.reset_index(drop=True), diagnostics=diagnostics.reset_index(drop=True))


def build_universe_snapshots(
    security_master: pd.DataFrame,
    silver_market: pd.DataFrame,
    universe_config: UniverseConfig,
    *,
    dates: list[str | pd.Timestamp] | pd.DatetimeIndex | None = None,
    feature_coverage: pd.DataFrame | None = None,
) -> UniverseBuildResult:
    reference = security_master.copy()
    reference["listing_date"] = pd.to_datetime(reference["listing_date"], errors="coerce").dt.normalize()
    reference["delisting_date"] = pd.to_datetime(reference["delisting_date"], errors="coerce").dt.normalize()

    market = _compute_adv20(silver_market)
    market["trade_date"] = pd.to_datetime(market["trade_date"], errors="coerce").dt.normalize()
    market = market.rename(columns={"trade_date": "date", "close": "price_t"})
    selected_dates = (
        pd.DatetimeIndex(pd.to_datetime(list(dates), errors="coerce")).normalize()
        if dates is not None
        else pd.DatetimeIndex(sorted(market["date"].dropna().unique()))
    )
    market = market.loc[market["date"].isin(selected_dates), ["date", "security_id", "price_t", "adv20_usd_t", "data_quality_score"]].copy()
    snapshot = market.merge(reference, on="security_id", how="left")
    snapshot["feature_coverage_ratio"] = 1.0
    if feature_coverage is not None and not feature_coverage.empty:
        coverage = feature_coverage.copy()
        coverage["date"] = pd.to_datetime(coverage["date"], errors="coerce").dt.normalize()
        snapshot = snapshot.drop(columns=["feature_coverage_ratio"]).merge(
            coverage[["date", "security_id", "feature_coverage_ratio"]],
            on=["date", "security_id"],
            how="left",
        )

    filtered_frames: list[pd.DataFrame] = []
    for snapshot_date, frame in snapshot.groupby("date", sort=True):
        filtered_frames.append(_apply_universe_filters(frame, pd.Timestamp(snapshot_date), universe_config))

    output = pd.concat(filtered_frames, ignore_index=True) if filtered_frames else pd.DataFrame(
        columns=[
            "date",
            "security_id",
            "is_in_universe",
            "exclusion_reason_code",
            "price_t",
            "adv20_usd_t",
            "feature_coverage_ratio",
            "data_quality_score",
            "liquidity_bucket",
        ]
    )
    output = output[
        [
            "date",
            "security_id",
            "is_in_universe",
            "exclusion_reason_code",
            "price_t",
            "adv20_usd_t",
            "feature_coverage_ratio",
            "data_quality_score",
            "liquidity_bucket",
        ]
    ].sort_values(["date", "security_id"], kind="stable")
    validated = validate_dataframe(output, "universe_snapshot")
    diagnostics = (
        validated.groupby(["date", "is_in_universe", "exclusion_reason_code"], dropna=False)
        .size()
        .rename("row_count")
        .reset_index()
        .sort_values(["date", "is_in_universe", "exclusion_reason_code"], kind="stable")
        .reset_index(drop=True)
    )
    return UniverseBuildResult(snapshot=validated.reset_index(drop=True), diagnostics=diagnostics)
