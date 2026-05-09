# Configured adapter environment runbook

Configured adapters can read local paths, API keys, and user-agent values from
environment variables declared in `configs/data_sources.yaml`. This keeps the
repository reproducible while allowing private live-provider settings locally.

## Safe local pattern

1. Copy `.env.example` to `.env`.
2. Replace placeholder values only in `.env`.
3. Keep `.env` untracked.
4. Prefer configured-local smoke for pull requests.
5. Use live-public smoke only when the pull request explicitly changes external
   provider behavior.

## Adapter fields

| Field | Meaning | Failure mode |
| --- | --- | --- |
| `local_path` | Explicit repository-relative or absolute fixture path. | Permanent error when the file is missing. |
| `local_path_env` | Environment variable that points to a local fixture path. | Permanent error when both `local_path` and the env value are missing. |
| `api_key_env` | Environment variable that stores a live-provider credential. | Omitted from request when missing unless the provider requires it. |
| `api_key_header` | Header name used for the resolved API key. | Ignored when no API key is available. |
| `api_key_query_param` | Query parameter used for the resolved API key. | Ignored when no API key is available. |
| `user_agent_env` | Environment variable for a provider-specific user agent. | Falls back to `Mozilla/5.0` when missing. |

## Review checklist

- `.env.example` contains placeholders only.
- No real provider key appears in diffs or test fixtures.
- Tests monkeypatch environment variables instead of depending on local shell
  state.
- Error messages name the adapter and the missing setting.
