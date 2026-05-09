from __future__ import annotations

from alpha_research.config.models import AdapterConfig
from alpha_research.data.providers.configured_transport import (
    ConfiguredAdapterPermanentError,
    adapter_environment_diagnostics,
    provider_headers,
    resolve_env,
    resolve_local_path,
)


def test_resolve_env_strips_blank_values(monkeypatch) -> None:
    monkeypatch.setenv("ALPHA_RESEARCH_TEST_VALUE", "  usable-value  ")
    monkeypatch.setenv("ALPHA_RESEARCH_BLANK_VALUE", "   ")

    assert resolve_env("ALPHA_RESEARCH_TEST_VALUE") == "usable-value"
    assert resolve_env("ALPHA_RESEARCH_BLANK_VALUE") is None
    assert resolve_env(None) is None


def test_adapter_environment_diagnostics_reports_presence_without_values(monkeypatch) -> None:
    monkeypatch.setenv("ALPHA_RESEARCH_API_KEY", "secret-value")
    monkeypatch.setenv("ALPHA_RESEARCH_USER_AGENT", "alpha-research-test")

    adapter = AdapterConfig(
        adapter_name="diagnostic_adapter",
        adapter_type="http",
        api_key_env="ALPHA_RESEARCH_API_KEY",
        local_path_env="ALPHA_RESEARCH_LOCAL_PATH",
        user_agent_env="ALPHA_RESEARCH_USER_AGENT",
    )

    diagnostics = adapter_environment_diagnostics(adapter)

    assert diagnostics.api_key_env_present is True
    assert diagnostics.user_agent_env_present is True
    assert diagnostics.local_path_env_present is False
    assert diagnostics.as_dict()["api_key_env"] == "ALPHA_RESEARCH_API_KEY"


def test_provider_headers_uses_default_user_agent_when_env_missing(monkeypatch) -> None:
    monkeypatch.delenv("ALPHA_RESEARCH_USER_AGENT", raising=False)
    adapter = AdapterConfig(
        adapter_name="headers_adapter",
        adapter_type="http",
        user_agent_env="ALPHA_RESEARCH_USER_AGENT",
    )

    assert provider_headers(adapter)["User-Agent"] == "Mozilla/5.0"


def test_resolve_local_path_error_names_missing_env(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("ALPHA_RESEARCH_LOCAL_PATH", raising=False)
    adapter = AdapterConfig(
        adapter_name="local_fixture_adapter",
        adapter_type="local_file_market_daily",
        local_path_env="ALPHA_RESEARCH_LOCAL_PATH",
    )

    try:
        resolve_local_path(adapter, tmp_path)
    except ConfiguredAdapterPermanentError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected missing local path to raise a permanent adapter error")

    assert "local_fixture_adapter" in message
    assert "ALPHA_RESEARCH_LOCAL_PATH" in message
    assert "local_path_env_present" in message


def test_resolve_local_path_error_names_missing_file_source(tmp_path) -> None:
    adapter = AdapterConfig(
        adapter_name="missing_file_adapter",
        adapter_type="local_file_market_daily",
        local_path="fixtures/missing.csv",
    )

    try:
        resolve_local_path(adapter, tmp_path)
    except ConfiguredAdapterPermanentError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected missing fixture file to raise a permanent adapter error")

    assert "missing_file_adapter" in message
    assert "fixtures" in message
    assert "source=local_path" in message
