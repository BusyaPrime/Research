# Project structure

The repository is organized around research validity first and implementation
convenience second. Keep new code close to the invariant it protects.

| Path | Responsibility |
| --- | --- |
| `configs/` | Runtime configuration and adapter contracts. |
| `schemas/` | Machine-readable data and feature registry contracts. |
| `src/alpha_research/config` | Config loading, validation, hashing, and snapshots. |
| `src/alpha_research/time` | Trading calendars and decision/execution timestamp rules. |
| `src/alpha_research/data` | Provider contracts, raw/bronze ingest, QA, and storage. |
| `src/alpha_research/pit` | Point-in-time interval logic and as-of joins. |
| `src/alpha_research/features` | Registry-driven feature engineering. |
| `src/alpha_research/labels` | Label generation with explicit forward windows. |
| `src/alpha_research/splits` | Purged walk-forward split construction. |
| `src/alpha_research/models` | Baseline models and model-facing interfaces. |
| `src/alpha_research/training` | OOF training and tuning orchestration. |
| `src/alpha_research/portfolio` | Target weights, constraints, and turnover handling. |
| `src/alpha_research/execution` | Execution simulation and cost handling. |
| `src/alpha_research/evaluation` | Metrics, uncertainty, stability, and reports. |
| `src/alpha_research/pipeline` | Stage graph, dispatcher, and runtime handlers. |
| `tests/unit` | Fast deterministic checks for pure logic. |
| `tests/integration` | Cross-module pipeline and artifact checks. |
| `tests/leakage` | Time and fold leakage guards. |
| `docs/status` | Machine-readable implementation and acceptance evidence. |

When adding a new subsystem, add tests in the same branch and update the status
map when the change enforces or documents a specification clause.
