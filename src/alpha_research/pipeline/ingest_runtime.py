from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from alpha_research.common.io import write_json, write_parquet
from alpha_research.common.paths import RepositoryPaths
from alpha_research.config.loader import LoadedConfigBundle
from alpha_research.data.ingest.corporate_actions import CorporateActionsIngestionService
from alpha_research.data.ingest.fundamentals import FundamentalsIngestionService
from alpha_research.data.ingest.market import MarketIngestionService
from alpha_research.data.providers.configured import ConfiguredAdapterError, build_configured_ingest_context
from alpha_research.data.providers.runtime_stub import (
    SyntheticCorporateActionsProvider,
    SyntheticFundamentalsProvider,
    SyntheticMarketDataProvider,
)
from alpha_research.pipeline.fixture_data import build_synthetic_research_bundle
from alpha_research.reference.security_master import SymbolMapper, build_security_master


@dataclass(frozen=True)
class IngestStageResult:
    command: str
    manifest_path: Path
    primary_artifact_path: Path
    notes: list[str]


def _build_runtime_bundle(paths: RepositoryPaths, loaded: LoadedConfigBundle):
    runtime_config = loaded.bundle.runtime.ingest
    if runtime_config.provider_mode != "synthetic_vendor_stub":
        raise KeyError(f"Unsupported runtime ingest provider mode: {runtime_config.provider_mode}")
    return build_synthetic_research_bundle(
        start_date=runtime_config.default_start_date,
        end_date=runtime_config.default_end_date,
        n_securities=runtime_config.default_n_securities,
        seed=loaded.bundle.project.default_random_seed,
    )


def _persist_security_master(paths: RepositoryPaths, security_master) -> Path:
    reference_dir = paths.root / "data" / "reference"
    reference_dir.mkdir(parents=True, exist_ok=True)
    output_path = reference_dir / "security_master.parquet"
    manifest_path = reference_dir / "security_master.manifest.json"
    built = build_security_master(security_master, root=paths.root)
    write_parquet(built, output_path)
    write_json(
        {
            "row_count": int(len(built)),
            "path": str(output_path.relative_to(paths.root)),
        },
        manifest_path,
    )
    return output_path


def run_reference_command(root: Path, loaded: LoadedConfigBundle) -> IngestStageResult:
    paths = RepositoryPaths.from_root(root)
    if loaded.bundle.runtime.ingest.provider_mode == "synthetic_vendor_stub":
        bundle = _build_runtime_bundle(paths, loaded)
        security_master_frame = bundle.security_master
        notes = [
            "Reference layer собран через deterministic synthetic vendor stub adapter.",
            "Canonical security master сохраняется отдельным stage path.",
        ]
    elif loaded.bundle.runtime.ingest.provider_mode == "configured_adapters":
        try:
            context = build_configured_ingest_context(paths.root, loaded)
        except ConfiguredAdapterError as exc:
            raise KeyError(f"Configured reference adapters error: {exc}") from exc
        security_master_frame = context.security_master
        notes = [
            *context.notes,
            "Canonical security master сохраняется отдельным stage path.",
        ]
    else:
        raise KeyError(f"Unsupported runtime ingest provider mode: {loaded.bundle.runtime.ingest.provider_mode}")

    primary_artifact_path = _persist_security_master(paths, security_master_frame)
    manifest_path = paths.root / "data" / "reference" / "security_master.manifest.json"
    return IngestStageResult(
        command="build-reference",
        manifest_path=manifest_path,
        primary_artifact_path=primary_artifact_path,
        notes=notes,
    )


def run_ingest_command(command_name: str, root: Path, loaded: LoadedConfigBundle) -> IngestStageResult:
    paths = RepositoryPaths.from_root(root)
    page_size = loaded.bundle.runtime.ingest.page_size
    start_date = loaded.bundle.runtime.ingest.default_start_date
    end_date = loaded.bundle.runtime.ingest.default_end_date

    if loaded.bundle.runtime.ingest.provider_mode == "synthetic_vendor_stub":
        bundle = _build_runtime_bundle(paths, loaded)
        security_master_frame = bundle.security_master
        mapper = SymbolMapper(bundle.security_master)
        notes = [
            "Операционный ingest сейчас работает через deterministic synthetic vendor stub adapter.",
            "Архитектура слоя реальная: raw payload, request manifests и bronze artifacts сохраняются как в боевом path.",
        ]
        market_provider = SyntheticMarketDataProvider(bundle, page_size=page_size)
        fundamentals_provider = SyntheticFundamentalsProvider(bundle, page_size=page_size)
        corporate_actions_provider = SyntheticCorporateActionsProvider(bundle, page_size=page_size)
        symbols = bundle.security_master["symbol"].dropna().astype("string").str.upper().tolist()
        company_ids = bundle.bronze_fundamentals["source_company_id"].dropna().astype("string").str.upper().unique().tolist()
    elif loaded.bundle.runtime.ingest.provider_mode == "configured_adapters":
        try:
            context = build_configured_ingest_context(paths.root, loaded)
        except ConfiguredAdapterError as exc:
            raise KeyError(f"Configured ingest adapters error: {exc}") from exc
        security_master_frame = context.security_master
        mapper = context.symbol_mapper
        notes = [
            *context.notes,
            "Архитектура слоя реальная: raw payload, request manifests и bronze artifacts сохраняются как в боевом path.",
        ]
        market_provider = context.market_provider
        fundamentals_provider = context.fundamentals_provider
        corporate_actions_provider = context.corporate_actions_provider
        symbols = security_master_frame["symbol"].dropna().astype("string").str.upper().tolist()
        source_company_column = "source_company_id"
        if source_company_column in context.security_master_raw.columns:
            company_ids = context.security_master_raw[source_company_column].dropna().astype("string").str.upper().unique().tolist()
        else:
            company_ids = []
    else:
        raise KeyError(f"Unsupported runtime ingest provider mode: {loaded.bundle.runtime.ingest.provider_mode}")

    security_master_path = _persist_security_master(paths, security_master_frame)

    if command_name == "ingest-market":
        service = MarketIngestionService(root=paths.root)
        artifacts = service.ingest(market_provider, symbols, start_date, end_date, mapper)
        return IngestStageResult(command=command_name, manifest_path=artifacts.manifest_path, primary_artifact_path=artifacts.bronze_path, notes=[*notes, f"security_master_path={security_master_path.relative_to(paths.root)}"])

    if command_name == "ingest-fundamentals":
        service = FundamentalsIngestionService(root=paths.root)
        artifacts = service.ingest(fundamentals_provider, company_ids, start_date, end_date)
        return IngestStageResult(command=command_name, manifest_path=artifacts.manifest_path, primary_artifact_path=artifacts.bronze_path, notes=notes)

    if command_name == "ingest-corporate-actions":
        service = CorporateActionsIngestionService(root=paths.root)
        artifacts = service.ingest(corporate_actions_provider, symbols, start_date, end_date, mapper)
        return IngestStageResult(command=command_name, manifest_path=artifacts.manifest_path, primary_artifact_path=artifacts.bronze_path, notes=notes)

    raise KeyError(f"Unsupported ingest command: {command_name}")
