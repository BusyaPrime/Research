from __future__ import annotations

import argparse
import json
from pathlib import Path

from alpha_research.release.smoke import run_release_smoke


def main() -> int:
    parser = argparse.ArgumentParser(description="Запускает компактный operational release smoke path.")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Корень репозитория.")
    parser.add_argument("--extra-policy", choices=("forbid", "warn"), default="forbid")
    parser.add_argument(
        "--mode",
        choices=("configured-local", "live-public", "synthetic"),
        default="configured-local",
        help="configured-local: configured adapters с локальными fixture-файлами; live-public: configured adapters через публичные источники; synthetic: детерминированный synthetic fallback.",
    )
    args = parser.parse_args()

    provider_mode_override = None
    prepare_local_fixtures = None
    if args.mode == "configured-local":
        provider_mode_override = "configured_adapters"
        prepare_local_fixtures = True
    elif args.mode == "live-public":
        provider_mode_override = "configured_adapters"
        prepare_local_fixtures = False
    elif args.mode == "synthetic":
        provider_mode_override = "synthetic_vendor_stub"
        prepare_local_fixtures = False

    result = run_release_smoke(
        args.root,
        extra_policy=args.extra_policy,
        provider_mode_override=provider_mode_override,
        prepare_local_configured_fixtures_override=prepare_local_fixtures,
    )
    print(
        json.dumps(
            {
                "status": "completed",
                "summary_path": str(result.summary_path),
                "run_id": result.run_id,
                "ingest_commands_run": list(result.ingest_commands_run),
                "verification": {
                    "ok": result.verification.ok,
                    "manifest_count": result.verification.manifest_count,
                    "report_count": result.verification.report_count,
                    "section_count": result.verification.section_count,
                    "figure_count": result.verification.figure_count,
                    "pending_output_count": result.verification.pending_output_count,
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
