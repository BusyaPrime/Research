from __future__ import annotations

import argparse
import json
from pathlib import Path

from alpha_research.release.verification import ReleaseVerificationError, verify_release_bundle


def main() -> int:
    parser = argparse.ArgumentParser(description="Проверяет release bundle и связанные артефакты.")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Корень репозитория.")
    parser.add_argument("--review-bundle", type=Path, default=None, help="Путь до review_bundle.json. Если не указан, берется самый свежий.")
    args = parser.parse_args()

    try:
        result = verify_release_bundle(args.root, args.review_bundle)
    except ReleaseVerificationError as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error": str(exc),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    print(
        json.dumps(
            {
                "status": "ok",
                "review_bundle_path": str(result.review_bundle_path),
                "manifest_count": result.manifest_count,
                "report_count": result.report_count,
                "section_count": result.section_count,
                "figure_count": result.figure_count,
                "pending_output_count": result.pending_output_count,
                "notes": result.notes,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
