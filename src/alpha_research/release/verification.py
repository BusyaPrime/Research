from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


REQUIRED_MANIFEST_FIELDS = ("run_id", "dataset_version", "config_hash", "runtime_metadata")
REQUIRED_REVIEW_FIELDS = (
    "run_id",
    "manifest_path",
    "report_path",
    "release_checklist_path",
    "required_manifests",
    "required_reports",
    "report_section_paths",
    "key_metrics",
    "pending_outputs",
    "temporary_simplifications",
    "runtime_class",
    "capability_class",
    "release_eligible",
)


class ReleaseVerificationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReleaseVerificationResult:
    ok: bool
    review_bundle_path: Path
    manifest_count: int
    report_count: int
    section_count: int
    figure_count: int
    pending_output_count: int
    notes: list[str]


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _require_file(root: Path, relative_path: str | None, *, label: str) -> Path:
    if not relative_path:
        raise ReleaseVerificationError(f"В {label} не указан путь к артефакту.")
    candidate = root / relative_path
    if not candidate.exists():
        raise ReleaseVerificationError(f"Не найден обязательный артефакт {label}: {relative_path}")
    return candidate


def _resolve_review_bundle_path(root: Path, review_bundle_path: Path | None) -> Path:
    if review_bundle_path is not None:
        return review_bundle_path
    candidates = sorted((root / "artifacts" / "runs").glob("*/manifests/review_bundle.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    if not candidates:
        raise ReleaseVerificationError("Не найден ни один review_bundle.json в artifacts/runs.")
    return candidates[0]


def verify_release_bundle(root: Path, review_bundle_path: Path | None = None) -> ReleaseVerificationResult:
    root = Path(root).resolve()
    bundle_path = _resolve_review_bundle_path(root, review_bundle_path).resolve()
    if not bundle_path.exists():
        raise ReleaseVerificationError(f"Не найден review bundle: {bundle_path}")

    review_bundle = _read_json(bundle_path)
    for field in REQUIRED_REVIEW_FIELDS:
        if field not in review_bundle:
            raise ReleaseVerificationError(f"В review bundle отсутствует обязательное поле: {field}")

    manifest_path = _require_file(root, str(review_bundle["manifest_path"]), label="pipeline manifest")
    _require_file(root, str(review_bundle["report_path"]), label="final report")
    _require_file(root, str(review_bundle["release_checklist_path"]), label="release checklist")

    report_html_path = review_bundle.get("report_html_path")
    if report_html_path:
        _require_file(root, str(report_html_path), label="html report")

    manifest_payload = _read_json(manifest_path)
    for field in REQUIRED_MANIFEST_FIELDS:
        if field not in manifest_payload:
            raise ReleaseVerificationError(f"В pipeline manifest отсутствует обязательное поле: {field}")

    required_manifests = review_bundle["required_manifests"]
    required_reports = review_bundle["required_reports"]
    section_paths = review_bundle["report_section_paths"]
    pending_outputs = review_bundle["pending_outputs"]
    temporary_simplifications = review_bundle["temporary_simplifications"]

    for name, relative_path in required_manifests.items():
        _require_file(root, str(relative_path), label=f"manifest:{name}")
    for name, relative_path in required_reports.items():
        if relative_path is not None:
            _require_file(root, str(relative_path), label=f"report:{name}")
    for name, relative_path in section_paths.items():
        _require_file(root, str(relative_path), label=f"report_section:{name}")

    figure_count = 0
    report_bundle_path = review_bundle.get("report_bundle_path")
    notes: list[str] = []
    if report_bundle_path:
        resolved_report_bundle = _require_file(root, str(report_bundle_path), label="report bundle")
        report_bundle = _read_json(resolved_report_bundle)
        for figure in report_bundle.get("figure_artifacts", []):
            if figure.get("status") == "generated":
                _require_file(root, str(figure.get("path")), label=f"figure:{figure.get('figure_name')}")
                figure_count += 1
        notes.append(f"generated_formats={','.join(report_bundle.get('generated_formats', []))}")

    if pending_outputs:
        raise ReleaseVerificationError(f"В review bundle остались незакрытые pending outputs: {pending_outputs}")
    if temporary_simplifications:
        raise ReleaseVerificationError(
            "Release-grade verifier не принимает run с временными упрощениями: "
            f"{temporary_simplifications}"
        )
    if not bool(review_bundle["release_eligible"]):
        raise ReleaseVerificationError(
            "Review bundle помечен как non-release-eligible. "
            f"capability_class={review_bundle['capability_class']}, runtime_class={review_bundle['runtime_class']}."
        )

    notes.append(f"temporary_simplifications={len(temporary_simplifications)}")
    notes.append(f"artifacts={len(manifest_payload.get('artifacts', []))}")
    return ReleaseVerificationResult(
        ok=True,
        review_bundle_path=bundle_path,
        manifest_count=len(required_manifests),
        report_count=sum(1 for value in required_reports.values() if value is not None),
        section_count=len(section_paths),
        figure_count=figure_count,
        pending_output_count=len(pending_outputs),
        notes=notes,
    )
