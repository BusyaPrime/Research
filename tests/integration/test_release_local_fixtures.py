from __future__ import annotations

from alpha_research.config.loader import load_resolved_config_bundle
from alpha_research.release.local_fixtures import prepare_local_configured_smoke_bundle


def test_prepare_local_configured_smoke_bundle_writes_fixture_adapters(minimal_repo) -> None:
    loaded = load_resolved_config_bundle(minimal_repo)
    prepared_loaded, fixture_dir = prepare_local_configured_smoke_bundle(
        minimal_repo,
        loaded,
        start_date="2023-05-01",
        end_date="2024-06-28",
        n_securities=4,
    )

    assert fixture_dir.exists()
    assert (fixture_dir / "security_master.csv").exists()
    assert (fixture_dir / "market_daily.csv").exists()
    assert (fixture_dir / "fundamentals.csv").exists()
    assert (fixture_dir / "corporate_actions.csv").exists()
    assert (fixture_dir / "benchmark_market.csv").exists()
    assert prepared_loaded.bundle.runtime.ingest.provider_mode == "configured_adapters"
    assert prepared_loaded.config_hash != loaded.config_hash

    market_adapters = prepared_loaded.bundle.data_sources.market_provider.adapters or []
    benchmark_adapters = prepared_loaded.bundle.data_sources.benchmark_provider.adapters or []
    assert any(adapter.adapter_name == "local_file_market_daily" and adapter.enabled for adapter in market_adapters)
    assert any(adapter.adapter_name == "local_file_benchmark" and adapter.enabled for adapter in benchmark_adapters)
