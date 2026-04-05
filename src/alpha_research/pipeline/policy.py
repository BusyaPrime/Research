from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from alpha_research.config.loader import LoadedConfigBundle


class OperationalPolicyError(RuntimeError):
    """Base class for strict operational policy violations."""


class UnsupportedExperimentForOperationalRun(OperationalPolicyError):
    """Raised when the selected operational experiment is not supported by the runtime."""


class IncompleteOperationalOutputs(OperationalPolicyError):
    """Raised when a release-capable run leaves requested outputs ungenerated."""


class TemporarySimplificationViolation(OperationalPolicyError):
    """Raised when strict operational policy encounters temporary simplifications."""


class ReleaseEligibilityViolation(OperationalPolicyError):
    """Raised when a fixture-only runtime is treated as release-eligible."""


RuntimeClass = Literal[
    "FixtureResearchRuntime",
    "LocalReproRuntime",
    "PublicAdapterRuntime",
    "ReleaseCandidateRuntime",
]
CapabilityClass = Literal["fixture_only", "local_repro", "public_adapter", "release_candidate"]


@dataclass(frozen=True)
class RuntimeCapability:
    runtime_class: RuntimeClass
    capability_class: CapabilityClass
    allows_release_bundle: bool
    allows_final_report: bool
    synthetic_ingest_allowed: bool
    external_proofs_required: bool


FIXTURE_RESEARCH_CAPABILITY = RuntimeCapability(
    runtime_class="FixtureResearchRuntime",
    capability_class="fixture_only",
    allows_release_bundle=False,
    allows_final_report=True,
    synthetic_ingest_allowed=True,
    external_proofs_required=False,
)
LOCAL_REPRO_CAPABILITY = RuntimeCapability(
    runtime_class="LocalReproRuntime",
    capability_class="local_repro",
    allows_release_bundle=True,
    allows_final_report=True,
    synthetic_ingest_allowed=False,
    external_proofs_required=False,
)
PUBLIC_ADAPTER_CAPABILITY = RuntimeCapability(
    runtime_class="PublicAdapterRuntime",
    capability_class="public_adapter",
    allows_release_bundle=True,
    allows_final_report=True,
    synthetic_ingest_allowed=False,
    external_proofs_required=True,
)
RELEASE_CANDIDATE_CAPABILITY = RuntimeCapability(
    runtime_class="ReleaseCandidateRuntime",
    capability_class="release_candidate",
    allows_release_bundle=True,
    allows_final_report=True,
    synthetic_ingest_allowed=False,
    external_proofs_required=True,
)


def _provider_uses_local_paths(loaded: LoadedConfigBundle) -> bool:
    providers = (
        loaded.bundle.data_sources.market_provider,
        loaded.bundle.data_sources.fundamentals_provider,
        loaded.bundle.data_sources.corporate_actions_provider,
        loaded.bundle.data_sources.security_master_provider,
        loaded.bundle.data_sources.benchmark_provider,
    )
    for provider in providers:
        for adapter in provider.adapters or []:
            if not adapter.enabled:
                continue
            if adapter.local_path or adapter.local_path_env:
                return True
    return False


def resolve_runtime_capability(
    loaded: LoadedConfigBundle,
    *,
    synthetic_bundle_active: bool,
    command_name: str,
) -> RuntimeCapability:
    provider_mode = loaded.bundle.runtime.ingest.provider_mode
    if synthetic_bundle_active or provider_mode == "synthetic_vendor_stub":
        return FIXTURE_RESEARCH_CAPABILITY

    if _provider_uses_local_paths(loaded):
        return LOCAL_REPRO_CAPABILITY

    if command_name in {"run-report", "run-full-pipeline"}:
        return RELEASE_CANDIDATE_CAPABILITY
    return PUBLIC_ADAPTER_CAPABILITY
