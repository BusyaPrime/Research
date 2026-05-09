from __future__ import annotations

from alpha_research.config.models import AdapterConfig
from alpha_research.data.providers.configured_transport import (
    adapter_environment_diagnostics,
    provider_headers,
    resolve_env,
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
