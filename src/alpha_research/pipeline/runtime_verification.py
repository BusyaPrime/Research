from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from alpha_research.release.verification import ReleaseVerificationResult, verify_release_bundle


@dataclass(frozen=True)
class StageFailureSemantics:
    fail_fast: bool
    blocks_release: bool
    rationale: str


@dataclass(frozen=True)
class StageEligibilityContract:
    release_grade_allowed: bool
    requires_zero_pending_outputs: bool
    requires_release_eligible_bundle: bool
    allowed_capability_classes: tuple[str, ...]


def strict_failure_semantics(*, rationale: str) -> StageFailureSemantics:
    return StageFailureSemantics(
        fail_fast=True,
        blocks_release=True,
        rationale=rationale,
    )


def release_contract(
    *,
    release_grade_allowed: bool,
    allowed_capability_classes: tuple[str, ...] = ("release_candidate",),
    requires_zero_pending_outputs: bool = False,
    requires_release_eligible_bundle: bool = False,
) -> StageEligibilityContract:
    return StageEligibilityContract(
        release_grade_allowed=release_grade_allowed,
        requires_zero_pending_outputs=requires_zero_pending_outputs,
        requires_release_eligible_bundle=requires_release_eligible_bundle,
        allowed_capability_classes=allowed_capability_classes,
    )


def verify_run_review_bundle(root: Path, review_bundle_path: Path | None = None) -> ReleaseVerificationResult:
    return verify_release_bundle(root, review_bundle_path=review_bundle_path)
