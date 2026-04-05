from __future__ import annotations

from pathlib import Path

from alpha_research.config.loader import LoadedConfigBundle
from alpha_research.pipeline.ingest_runtime import run_ingest_command, run_reference_command

INGEST_COMMANDS = {
    "build-reference",
    "ingest-market",
    "ingest-fundamentals",
    "ingest-corporate-actions",
}


def execute_ingest_stage_command(
    command_name: str,
    root: Path,
    loaded: LoadedConfigBundle,
    *,
    stage_ids: list[str] | None = None,
) -> dict[str, object]:
    if command_name == "build-reference":
        result = run_reference_command(root, loaded)
    elif command_name in INGEST_COMMANDS:
        result = run_ingest_command(command_name, root, loaded)
    else:
        raise KeyError(f"Unsupported ingest/runtime command: {command_name}")

    return {
        "command": command_name,
        "status": "completed",
        "root": str(root),
        "config_hash": loaded.config_hash,
        "manifest_path": str(result.manifest_path.relative_to(root)),
        "primary_artifact_path": str(result.primary_artifact_path.relative_to(root)),
        "notes": result.notes,
        "stage_ids": list(stage_ids or []),
    }
