# Environment variables

The repository should run in deterministic local mode without private secrets.
Live provider credentials are optional and should stay in a local `.env` file or
the shell environment.

## Core variables

| Variable | Required | Example | Notes |
| --- | --- | --- | --- |
| `ALPHA_RESEARCH_ENV` | no | `local` | Describes the active runtime environment. |
| `ALPHA_RESEARCH_TRACKING_URI` | no | `./mlruns` | Local tracking output directory. |
| `ALPHA_RESEARCH_LOG_LEVEL` | no | `INFO` | Logging verbosity for local runs. |

## Configured adapter variables

Configured adapters may reference variables through `api_key_env`,
`user_agent_env`, or `local_path_env` in YAML config. Keep those values out of
Git unless they are harmless placeholders.

| Variable pattern | Purpose | Safe example |
| --- | --- | --- |
| `*_API_KEY` | API key for a live provider. | `replace-me` |
| `*_USER_AGENT` | Provider-specific user agent. | `alpha-research-local/0.1` |
| `*_LOCAL_PATH` | Local CSV, JSON, or Parquet fixture path. | `./tests/fixtures/provider.csv` |

## Secret handling rules

- commit `.env.example`, never a real `.env`;
- use fake placeholder values in documentation;
- prefer configured-local smoke for pull requests;
- run live-public smoke only when external access is intended and documented.
