from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pandas as pd

from alpha_research.common.hashing import hash_mapping
from alpha_research.config.loader import LoadedConfigBundle
from alpha_research.config.models import DataSourcesConfig
from alpha_research.pipeline.fixture_data import SyntheticResearchBundle, build_synthetic_research_bundle


def _write_csv(path: Path, frame: pd.DataFrame) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return path


def _security_master_with_source_ids(bundle: SyntheticResearchBundle) -> pd.DataFrame:
    frame = bundle.security_master.copy()
    frame["source_company_id"] = frame["security_id"].astype("string").str.replace("SEC_", "COMP_", regex=False)
    return frame


def _market_fixture(bundle: SyntheticResearchBundle) -> pd.DataFrame:
    mapping = bundle.security_master[["security_id", "symbol"]].copy()
    frame = bundle.silver_market.merge(mapping, on="security_id", how="left")
    frame["provider_symbol"] = frame["symbol"].astype("string").str.upper()
    frame["currency"] = "USD"
    frame["raw_payload_version"] = "release_smoke_fixture_v1"
    return frame[
        [
            "provider_symbol",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "adj_close",
            "volume",
            "currency",
            "raw_payload_version",
        ]
    ].copy()


def _fundamentals_fixture(bundle: SyntheticResearchBundle) -> pd.DataFrame:
    return bundle.bronze_fundamentals[
        [
            "security_id",
            "source_company_id",
            "form_type",
            "filing_date",
            "acceptance_datetime",
            "fiscal_period_end",
            "metric_name_raw",
            "metric_value",
            "metric_unit",
            "statement_type",
        ]
    ].copy()


def _corporate_actions_fixture(bundle: SyntheticResearchBundle) -> pd.DataFrame:
    security_master = bundle.security_master.reset_index(drop=True)
    dates = pd.to_datetime(bundle.silver_market["trade_date"], errors="coerce").dropna().sort_values()
    midpoint = dates.iloc[len(dates) // 2].normalize() if not dates.empty else pd.Timestamp("2024-06-03")
    rows: list[dict[str, object]] = []
    if not security_master.empty:
        first = security_master.iloc[0]
        rows.append(
            {
                "security_id": first["security_id"],
                "symbol": first["symbol"],
                "event_type": "split",
                "event_date": midpoint.date().isoformat(),
                "effective_date": midpoint.date().isoformat(),
                "split_ratio": 2.0,
                "dividend_amount": None,
                "delisting_code": None,
                "old_symbol": None,
                "new_symbol": None,
            }
        )
    if len(security_master) > 1:
        second = security_master.iloc[1]
        rows.append(
            {
                "security_id": second["security_id"],
                "symbol": second["symbol"],
                "event_type": "dividend",
                "event_date": (midpoint + pd.Timedelta(days=5)).date().isoformat(),
                "effective_date": (midpoint + pd.Timedelta(days=5)).date().isoformat(),
                "split_ratio": None,
                "dividend_amount": 0.12,
                "delisting_code": None,
                "old_symbol": None,
                "new_symbol": None,
            }
        )
    return pd.DataFrame(rows)


def _benchmark_fixture(bundle: SyntheticResearchBundle) -> pd.DataFrame:
    return bundle.benchmark_market[["trade_date", "open", "high", "low", "close"]].copy()


def _updated_bundle_with_fixture_adapters(loaded: LoadedConfigBundle, fixture_dir: Path) -> LoadedConfigBundle:
    data_sources = loaded.bundle.data_sources.model_dump(mode="python")

    def _enable_only(provider_name: str, adapter_name: str, relative_path: str | None = None) -> None:
        provider = data_sources[provider_name]
        for adapter in provider["adapters"]:
            adapter["enabled"] = adapter["adapter_name"] == adapter_name
            if relative_path is not None and adapter["adapter_name"] == adapter_name:
                adapter["local_path"] = relative_path

    _enable_only("market_provider", "local_file_market_daily", str((fixture_dir / "market_daily.csv").as_posix()))
    _enable_only("fundamentals_provider", "local_file_fundamentals", str((fixture_dir / "fundamentals.csv").as_posix()))
    _enable_only("corporate_actions_provider", "local_file_corporate_actions", str((fixture_dir / "corporate_actions.csv").as_posix()))
    _enable_only("security_master_provider", "local_file_security_master", str((fixture_dir / "security_master.csv").as_posix()))
    _enable_only("benchmark_provider", "local_file_benchmark", str((fixture_dir / "benchmark_market.csv").as_posix()))
    validated_data_sources = DataSourcesConfig.model_validate(data_sources)

    updated_bundle = loaded.bundle.model_copy(
        update={
            "data_sources": validated_data_sources,
            "runtime": loaded.bundle.runtime.model_copy(
                update={
                    "ingest": loaded.bundle.runtime.ingest.model_copy(update={"provider_mode": "configured_adapters"})
                }
            ),
        }
    )
    updated_hash = hash_mapping(updated_bundle.model_dump(mode="json"))
    return replace(loaded, bundle=updated_bundle, config_hash=updated_hash)


def prepare_local_configured_smoke_bundle(
    root: Path,
    loaded: LoadedConfigBundle,
    *,
    start_date: str,
    end_date: str,
    n_securities: int,
) -> tuple[LoadedConfigBundle, Path]:
    fixture_dir = root / "artifacts" / "release_smoke_fixtures" / "configured_local"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    bundle = build_synthetic_research_bundle(
        start_date=start_date,
        end_date=end_date,
        n_securities=n_securities,
        seed=loaded.bundle.project.default_random_seed,
    )

    _write_csv(fixture_dir / "security_master.csv", _security_master_with_source_ids(bundle))
    _write_csv(fixture_dir / "market_daily.csv", _market_fixture(bundle))
    _write_csv(fixture_dir / "fundamentals.csv", _fundamentals_fixture(bundle))
    _write_csv(fixture_dir / "corporate_actions.csv", _corporate_actions_fixture(bundle))
    _write_csv(fixture_dir / "benchmark_market.csv", _benchmark_fixture(bundle))
    return _updated_bundle_with_fixture_adapters(loaded, fixture_dir), fixture_dir
