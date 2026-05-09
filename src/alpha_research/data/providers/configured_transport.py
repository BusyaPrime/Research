from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from alpha_research.common.hashing import hash_mapping
from alpha_research.common.io import read_json, read_parquet
from alpha_research.config.models import AdapterConfig


class ConfiguredAdapterError(RuntimeError):
    pass


class ConfiguredAdapterTransientError(ConfiguredAdapterError):
    pass


class ConfiguredAdapterPermanentError(ConfiguredAdapterError):
    pass


@dataclass(frozen=True)
class AdapterEnvironmentDiagnostics:
    adapter_name: str
    local_path_env: str | None
    local_path_env_present: bool
    api_key_env: str | None
    api_key_env_present: bool
    user_agent_env: str | None
    user_agent_env_present: bool

    def as_dict(self) -> dict[str, bool | str | None]:
        return {
            "adapter_name": self.adapter_name,
            "local_path_env": self.local_path_env,
            "local_path_env_present": self.local_path_env_present,
            "api_key_env": self.api_key_env,
            "api_key_env_present": self.api_key_env_present,
            "user_agent_env": self.user_agent_env,
            "user_agent_env_present": self.user_agent_env_present,
        }


@dataclass(frozen=True)
class ResponseCache:
    root: Path

    def _cache_path(self, cache_key: str) -> Path:
        return self.root / f"{hash_mapping({'cache_key': cache_key})}.bin"

    def get(self, cache_key: str) -> bytes | None:
        path = self._cache_path(cache_key)
        return path.read_bytes() if path.exists() else None

    def put(self, cache_key: str, payload: bytes) -> None:
        path = self._cache_path(cache_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)


def _raw_http_get_bytes(url: str, headers: dict[str, str] | None = None, timeout_seconds: int = 30) -> bytes:
    request = Request(url, headers=headers or {})
    with urlopen(request, timeout=timeout_seconds) as response:
        return response.read()


def resolve_env(name: str | None) -> str | None:
    if not name:
        return None
    value = os.environ.get(name)
    return value.strip() if isinstance(value, str) and value.strip() else None


def adapter_environment_diagnostics(adapter: AdapterConfig) -> AdapterEnvironmentDiagnostics:
    return AdapterEnvironmentDiagnostics(
        adapter_name=adapter.adapter_name,
        local_path_env=adapter.local_path_env,
        local_path_env_present=resolve_env(adapter.local_path_env) is not None,
        api_key_env=adapter.api_key_env,
        api_key_env_present=resolve_env(adapter.api_key_env) is not None,
        user_agent_env=adapter.user_agent_env,
        user_agent_env_present=resolve_env(adapter.user_agent_env) is not None,
    )


def resolve_local_path(adapter: AdapterConfig, root: Path) -> Path:
    local_path = adapter.local_path or resolve_env(adapter.local_path_env)
    if not local_path:
        raise ConfiguredAdapterPermanentError(
            f"Для adapter `{adapter.adapter_name}` не указан local_path и не задан env `{adapter.local_path_env}`."
        )
    candidate = Path(local_path)
    if not candidate.is_absolute():
        candidate = (root / candidate).resolve()
    if not candidate.exists():
        raise ConfiguredAdapterPermanentError(f"Локальный файл для adapter `{adapter.adapter_name}` не найден: {candidate}")
    return candidate


def load_table_from_path(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".parquet", ".pq"}:
        return read_parquet(path)
    if suffix == ".json":
        payload = read_json(path)
        if isinstance(payload, list):
            return pd.DataFrame(payload)
        if isinstance(payload, dict) and "records" in payload:
            return pd.DataFrame(payload["records"])
        return pd.DataFrame([payload])
    raise ConfiguredAdapterPermanentError(f"Неподдерживаемый формат локального файла: {path}")


def provider_headers(adapter: AdapterConfig) -> dict[str, str]:
    headers = dict(adapter.default_headers or {})
    api_key = resolve_env(adapter.api_key_env)
    if adapter.api_key_header and api_key:
        headers[adapter.api_key_header] = api_key
    user_agent = resolve_env(adapter.user_agent_env)
    if user_agent:
        headers["User-Agent"] = user_agent
    if "User-Agent" not in headers:
        headers["User-Agent"] = "Mozilla/5.0"
    return headers


def provider_url(adapter: AdapterConfig, path: str, query: dict[str, str | int | float | None] | None = None) -> str:
    if not adapter.base_url:
        raise ConfiguredAdapterPermanentError(f"Для adapter `{adapter.adapter_name}` не задан base_url.")
    base = adapter.base_url.rstrip("/")
    relative = path.lstrip("/")
    params = {key: value for key, value in (query or {}).items() if value is not None}
    api_key = resolve_env(adapter.api_key_env)
    if adapter.api_key_query_param and api_key:
        params[adapter.api_key_query_param] = api_key
    encoded = urlencode(params)
    return f"{base}/{relative}?{encoded}" if encoded else f"{base}/{relative}"


def _classify_transport_failure(adapter: AdapterConfig, exc: Exception) -> ConfiguredAdapterError:
    if isinstance(exc, HTTPError):
        if exc.code in {408, 409, 425, 429} or 500 <= exc.code <= 599:
            return ConfiguredAdapterTransientError(
                f"Временная HTTP ошибка для adapter `{adapter.adapter_name}`: code={exc.code}, url={exc.url}"
            )
        return ConfiguredAdapterPermanentError(
            f"Постоянная HTTP ошибка для adapter `{adapter.adapter_name}`: code={exc.code}, url={exc.url}"
        )
    if isinstance(exc, URLError):
        return ConfiguredAdapterTransientError(f"Сетевая ошибка для adapter `{adapter.adapter_name}`: {exc.reason}")
    if isinstance(exc, TimeoutError):
        return ConfiguredAdapterTransientError(f"Timeout для adapter `{adapter.adapter_name}`.")
    if isinstance(exc, ConfiguredAdapterError):
        return exc
    return ConfiguredAdapterPermanentError(f"Неожиданная ошибка transport слоя для `{adapter.adapter_name}`: {exc}")


def _response_cache(adapter: AdapterConfig, root: Path | None) -> ResponseCache | None:
    if not adapter.cache_enabled or root is None:
        return None
    subdir = adapter.cache_subdir or adapter.adapter_name
    return ResponseCache((root / ".cache" / "configured_adapters" / subdir).resolve())


def http_get_bytes(
    adapter: AdapterConfig,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    root: Path | None = None,
    cache_key: str | None = None,
) -> bytes:
    cache = _response_cache(adapter, root)
    resolved_cache_key = cache_key or url
    if cache is not None:
        cached = cache.get(resolved_cache_key)
        if cached is not None:
            return cached

    last_error: ConfiguredAdapterError | None = None
    for attempt in range(adapter.max_retries + 1):
        try:
            payload = _raw_http_get_bytes(url, headers=headers, timeout_seconds=adapter.timeout_seconds)
            if cache is not None:
                cache.put(resolved_cache_key, payload)
            return payload
        except Exception as exc:  # noqa: BLE001
            classified = _classify_transport_failure(adapter, exc)
            last_error = classified
            if isinstance(classified, ConfiguredAdapterPermanentError) or attempt >= adapter.max_retries:
                raise classified
            time.sleep(adapter.backoff_seconds * (2**attempt))
    if last_error is not None:
        raise last_error
    raise ConfiguredAdapterTransientError(f"Transport слой `{adapter.adapter_name}` завершился без payload и без явной ошибки.")


def http_get_json(
    adapter: AdapterConfig,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    root: Path | None = None,
    cache_key: str | None = None,
) -> Any:
    payload = http_get_bytes(adapter, url, headers=headers, root=root, cache_key=cache_key)
    return json.loads(payload.decode("utf-8"))
