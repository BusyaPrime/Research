from __future__ import annotations

import pandas as pd

from alpha_research.config.loader import load_resolved_config_bundle
from alpha_research.pit.builders import build_silver_market
from alpha_research.universe.builder import build_universe_snapshot


def _security_master() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"security_id": "SEC_COMMON", "symbol": "AAA", "security_type": "common_stock", "exchange": "NYSE", "listing_date": "2020-01-01", "delisting_date": None, "sector": "Tech", "industry": "Software", "country": "US", "currency": "USD", "is_common_stock": True},
            {"security_id": "SEC_ETF", "symbol": "ETF1", "security_type": "ETF", "exchange": "NYSE", "listing_date": "2020-01-01", "delisting_date": None, "sector": "ETF", "industry": "ETF", "country": "US", "currency": "USD", "is_common_stock": False},
            {"security_id": "SEC_FUTURE", "symbol": "NEW1", "security_type": "common_stock", "exchange": "NASDAQ", "listing_date": "2024-07-10", "delisting_date": None, "sector": "Tech", "industry": "Hardware", "country": "US", "currency": "USD", "is_common_stock": True},
            {"security_id": "SEC_DELISTED", "symbol": "OLD1", "security_type": "common_stock", "exchange": "NASDAQ", "listing_date": "2020-01-01", "delisting_date": "2024-07-02", "sector": "Tech", "industry": "Hardware", "country": "US", "currency": "USD", "is_common_stock": True},
            {"security_id": "SEC_OTC", "symbol": "OTC1", "security_type": "OTC", "exchange": "OTC", "listing_date": "2020-01-01", "delisting_date": None, "sector": "Tech", "industry": "Hardware", "country": "US", "currency": "USD", "is_common_stock": False},
            {"security_id": "SEC_LOWP", "symbol": "LOWP", "security_type": "common_stock", "exchange": "NASDAQ", "listing_date": "2020-01-01", "delisting_date": None, "sector": "Tech", "industry": "Hardware", "country": "US", "currency": "USD", "is_common_stock": True},
            {"security_id": "SEC_LOWADV", "symbol": "LOWA", "security_type": "common_stock", "exchange": "NASDAQ", "listing_date": "2020-01-01", "delisting_date": None, "sector": "Tech", "industry": "Hardware", "country": "US", "currency": "USD", "is_common_stock": True},
        ]
    )


def _silver_market() -> pd.DataFrame:
    rows = []
    dates = pd.date_range("2024-06-10", periods=20, freq="B")
    for date in dates:
        rows.extend(
            [
                {"security_id": "SEC_COMMON", "trade_date": date, "open": 10.0, "high": 10.5, "low": 9.8, "close": 10.0, "adj_close": 10.0, "volume": 600_000, "dollar_volume": 6_000_000.0, "is_price_valid": True, "is_volume_valid": True, "tradable_flag_prelim": True, "data_quality_score": 0.95, "data_version": "v1"},
                {"security_id": "SEC_ETF", "trade_date": date, "open": 20.0, "high": 20.5, "low": 19.5, "close": 20.0, "adj_close": 20.0, "volume": 600_000, "dollar_volume": 12_000_000.0, "is_price_valid": True, "is_volume_valid": True, "tradable_flag_prelim": True, "data_quality_score": 0.95, "data_version": "v1"},
                {"security_id": "SEC_FUTURE", "trade_date": date, "open": 15.0, "high": 15.5, "low": 14.5, "close": 15.0, "adj_close": 15.0, "volume": 600_000, "dollar_volume": 9_000_000.0, "is_price_valid": True, "is_volume_valid": True, "tradable_flag_prelim": True, "data_quality_score": 0.95, "data_version": "v1"},
                {"security_id": "SEC_DELISTED", "trade_date": date, "open": 12.0, "high": 12.5, "low": 11.5, "close": 12.0, "adj_close": 12.0, "volume": 600_000, "dollar_volume": 7_200_000.0, "is_price_valid": True, "is_volume_valid": True, "tradable_flag_prelim": True, "data_quality_score": 0.95, "data_version": "v1"},
                {"security_id": "SEC_OTC", "trade_date": date, "open": 11.0, "high": 11.2, "low": 10.8, "close": 11.0, "adj_close": 11.0, "volume": 600_000, "dollar_volume": 6_600_000.0, "is_price_valid": True, "is_volume_valid": True, "tradable_flag_prelim": True, "data_quality_score": 0.95, "data_version": "v1"},
                {"security_id": "SEC_LOWP", "trade_date": date, "open": 4.0, "high": 4.1, "low": 3.9, "close": 4.0, "adj_close": 4.0, "volume": 600_000, "dollar_volume": 2_400_000.0, "is_price_valid": True, "is_volume_valid": True, "tradable_flag_prelim": True, "data_quality_score": 0.95, "data_version": "v1"},
                {"security_id": "SEC_LOWADV", "trade_date": date, "open": 10.0, "high": 10.1, "low": 9.9, "close": 10.0, "adj_close": 10.0, "volume": 100_000, "dollar_volume": 1_000_000.0, "is_price_valid": True, "is_volume_valid": True, "tradable_flag_prelim": True, "data_quality_score": 0.95, "data_version": "v1"},
            ]
        )
    return build_silver_market(pd.DataFrame(rows))


def test_universe_security_type_filter_excludes_etf_adr_otc(minimal_repo) -> None:
    config = load_resolved_config_bundle(minimal_repo).bundle.universe
    snapshot = build_universe_snapshot("2024-07-05", _security_master(), _silver_market(), config).snapshot
    row = snapshot.loc[snapshot["security_id"] == "SEC_ETF"].iloc[0]
    assert not row["is_in_universe"]
    assert row["exclusion_reason_code"] == "excluded_security_type"


def test_universe_listing_and_delisting_filter_respects_snapshot_date(minimal_repo) -> None:
    config = load_resolved_config_bundle(minimal_repo).bundle.universe
    snapshot = build_universe_snapshot("2024-07-05", _security_master(), _silver_market(), config).snapshot
    future = snapshot.loc[snapshot["security_id"] == "SEC_FUTURE"].iloc[0]
    delisted = snapshot.loc[snapshot["security_id"] == "SEC_DELISTED"].iloc[0]
    assert future["exclusion_reason_code"] == "inactive_listing"
    assert delisted["exclusion_reason_code"] == "inactive_listing"


def test_universe_min_price_filter_uses_point_in_time_price(minimal_repo) -> None:
    config = load_resolved_config_bundle(minimal_repo).bundle.universe
    snapshot = build_universe_snapshot("2024-07-05", _security_master(), _silver_market(), config).snapshot
    low_price = snapshot.loc[snapshot["security_id"] == "SEC_LOWP"].iloc[0]
    assert low_price["price_t"] == 4.0
    assert low_price["exclusion_reason_code"] == "price_below_min"


def test_universe_min_adv_filter_uses_point_in_time_adv20(minimal_repo) -> None:
    config = load_resolved_config_bundle(minimal_repo).bundle.universe
    snapshot = build_universe_snapshot("2024-07-05", _security_master(), _silver_market(), config).snapshot
    low_adv = snapshot.loc[snapshot["security_id"] == "SEC_LOWADV"].iloc[0]
    assert low_adv["adv20_usd_t"] < config.min_adv20_usd
    assert low_adv["exclusion_reason_code"] == "adv20_below_min"


def test_universe_exclusion_reasons_are_deterministic(minimal_repo) -> None:
    config = load_resolved_config_bundle(minimal_repo).bundle.universe
    first = build_universe_snapshot("2024-07-05", _security_master(), _silver_market(), config).snapshot
    second = build_universe_snapshot("2024-07-05", _security_master(), _silver_market(), config).snapshot
    assert first["exclusion_reason_code"].tolist() == second["exclusion_reason_code"].tolist()


def test_universe_snapshots_are_reproducible(minimal_repo) -> None:
    config = load_resolved_config_bundle(minimal_repo).bundle.universe
    first = build_universe_snapshot("2024-07-05", _security_master(), _silver_market(), config).snapshot
    second = build_universe_snapshot("2024-07-05", _security_master(), _silver_market(), config).snapshot
    pd.testing.assert_frame_equal(first, second)
