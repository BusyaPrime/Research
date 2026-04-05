from __future__ import annotations

from alpha_research.pipeline import runtime_reporting as _runtime_reporting
from alpha_research.pipeline import runtime_research as _runtime_research
from alpha_research.pipeline.runtime_release import (
    COMMAND_TO_STAGE_IDS,
    STAGE_GRAPH,
)
from alpha_research.pipeline.runtime_release import (
    execute_operational_command as _dispatch_execute_operational_command,
)
from alpha_research.pipeline.runtime_release import (
    execute_stage_command as _execute_stage_command,
)
from alpha_research.pipeline.runtime_release import (
    resolve_stage_plan as _resolve_stage_plan,
)
from alpha_research.pipeline.runtime_release import (
    stage_contract_snapshot as _stage_contract_snapshot,
)

OPERATIONAL_COMMANDS = _runtime_research.OPERATIONAL_COMMANDS
PRIMARY_ARTIFACT_BY_COMMAND = _runtime_research.PRIMARY_ARTIFACT_BY_COMMAND
SUPPORTED_MODEL_NAMES = _runtime_research.SUPPORTED_MODEL_NAMES
OperationalRunResult = _runtime_research.OperationalRunResult
StageCommandGraph = STAGE_GRAPH
StageCommandMap = COMMAND_TO_STAGE_IDS
execute_stage_command = _execute_stage_command
resolve_stage_plan = _resolve_stage_plan
stage_contract_snapshot = _stage_contract_snapshot

# Compatibility bridge: existing tests and local tooling monkeypatch symbols on
# alpha_research.pipeline.runtime. Before dispatching into the extracted
# research/reporting runtimes we mirror those overrides into the extracted
# modules.
_RESEARCH_PATCHABLE_SYMBOLS = (
    "resolve_operational_bundle",
    "_build_model_specs",
    "run_ablation_suite",
    "build_universe_snapshots",
    "build_feature_panel",
    "build_label_panel",
    "build_gold_panel",
    "generate_walk_forward_splits",
    "generate_oof_predictions",
    "run_backtest",
    "run_capacity_analysis",
    "capture_runtime_metadata",
    "compute_predictive_metrics",
    "compute_portfolio_metrics",
    "compute_regime_breakdown",
    "build_decay_response_curve",
)
_REPORTING_PATCHABLE_SYMBOLS = (
    "render_mandatory_figures",
    "render_final_report",
    "render_final_report_html",
    "render_report_sections",
)

for _name in _RESEARCH_PATCHABLE_SYMBOLS:
    globals()[_name] = getattr(_runtime_research, _name)
for _name in _REPORTING_PATCHABLE_SYMBOLS:
    globals()[_name] = getattr(_runtime_reporting, _name)


def _sync_runtime_overrides() -> None:
    for name in _RESEARCH_PATCHABLE_SYMBOLS:
        setattr(_runtime_research, name, globals()[name])
    for name in _REPORTING_PATCHABLE_SYMBOLS:
        setattr(_runtime_reporting, name, globals()[name])


def execute_operational_command(*args, **kwargs):
    _sync_runtime_overrides()
    return _dispatch_execute_operational_command(*args, **kwargs)
