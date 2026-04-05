from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from alpha_research.common.manifests import (
    ReportBundle,
    ReportFigureArtifact,
    ReportSectionArtifact,
    StageArtifact,
    write_json_document,
    write_model_document,
)
from alpha_research.config.models import ReportingConfig
from alpha_research.evaluation.figures import render_mandatory_figures
from alpha_research.evaluation.reporting import render_final_report, render_final_report_html, render_report_sections


@dataclass(frozen=True)
class ReportingArtifactsResult:
    report_path: Path
    report_html_path: Path | None
    report_bundle_path: Path
    section_index_path: Path
    section_artifacts: list[ReportSectionArtifact]
    pending_formats: list[str]
    stage_artifacts: list[StageArtifact]


def persist_reporting_artifacts(
    *,
    root: Path,
    manifests_dir: Path,
    report_dir: Path,
    report_sections_dir: Path,
    reporting_config: ReportingConfig,
    project_name: str,
    section_payloads: dict[str, str],
    limitations: list[str],
    next_steps: list[str],
    universe_snapshot: pd.DataFrame,
    feature_panel: pd.DataFrame,
    predictions: pd.DataFrame,
    labels: pd.DataFrame,
    backtest_daily_state: pd.DataFrame,
    capacity_results: pd.DataFrame,
    decay_curve: pd.DataFrame,
) -> ReportingArtifactsResult:
    stage_artifacts: list[StageArtifact] = []
    report_text = render_final_report(
        reporting_config,
        project_name=project_name,
        section_payloads=section_payloads,
        limitations=limitations,
        next_steps=next_steps,
    )
    rendered_sections = render_report_sections(
        reporting_config,
        section_payloads=section_payloads,
        limitations=limitations,
        next_steps=next_steps,
    )
    report_path = report_dir / "final_report.md"
    report_path.write_text(report_text, encoding="utf-8")
    stage_artifacts.append(StageArtifact(name="final_report", path=str(report_path.relative_to(root)), format="markdown"))

    section_artifacts: list[ReportSectionArtifact] = []
    section_index_payload: dict[str, dict[str, str | int]] = {}
    for index, section in enumerate(rendered_sections, start=1):
        section_path = report_sections_dir / f"{index:02d}_{section.key}.md"
        section_body = f"## {section.title}\n\n{section.body}\n"
        section_path.write_text(section_body, encoding="utf-8")
        relative_path = str(section_path.relative_to(root))
        section_artifacts.append(
            ReportSectionArtifact(
                section_key=section.key,
                title=section.title,
                path=relative_path,
                line_count=len(section_body.splitlines()),
            )
        )
        section_index_payload[section.key] = {"title": section.title, "path": relative_path, "line_count": len(section_body.splitlines())}

    section_index_path = write_json_document(section_index_payload, manifests_dir / "report_sections.json")
    stage_artifacts.append(
        StageArtifact(
            name="report_sections_index",
            path=str(section_index_path.relative_to(root)),
            row_count=len(section_artifacts),
            format="json",
        )
    )

    generated_formats = ["markdown"]
    pending_formats: list[str] = []
    report_html_path: Path | None = None
    if "html" in reporting_config.formats:
        report_html = render_final_report_html(
            reporting_config,
            project_name=project_name,
            section_payloads=section_payloads,
            limitations=limitations,
            next_steps=next_steps,
        )
        report_html_path = report_dir / "final_report.html"
        report_html_path.write_text(report_html, encoding="utf-8")
        generated_formats.append("html")
        stage_artifacts.append(StageArtifact(name="final_report_html", path=str(report_html_path.relative_to(root)), format="html"))

    for fmt in reporting_config.formats:
        if fmt not in generated_formats:
            pending_formats.append(fmt)

    rendered_figures = render_mandatory_figures(
        report_dir / "figures",
        requested_figures=list(reporting_config.mandatory_figures),
        universe_snapshot=universe_snapshot,
        feature_panel=feature_panel,
        predictions=predictions,
        labels=labels,
        backtest_daily_state=backtest_daily_state,
        capacity_results=capacity_results,
        decay_curve=decay_curve,
    )
    figure_artifacts = [
        ReportFigureArtifact(
            figure_name=figure.figure_name,
            status="generated",
            path=str(figure.path.relative_to(root)),
            notes=figure.notes,
        )
        for figure in rendered_figures
    ]
    for figure in figure_artifacts:
        stage_artifacts.append(StageArtifact(name=f"figure::{figure.figure_name}", path=str(figure.path), format="svg"))

    report_bundle = ReportBundle(
        project_name=project_name,
        report_path=str(report_path.relative_to(root)),
        report_html_path=None if report_html_path is None else str(report_html_path.relative_to(root)),
        section_index_path=str(section_index_path.relative_to(root)),
        section_artifacts=section_artifacts,
        figure_artifacts=figure_artifacts,
        requested_formats=list(reporting_config.formats),
        generated_formats=generated_formats,
        pending_formats=pending_formats,
    )
    report_bundle_path = write_model_document(report_bundle, manifests_dir / "report_bundle.json")
    stage_artifacts.append(
        StageArtifact(name="report_bundle", path=str(report_bundle_path.relative_to(root)), format="json")
    )

    return ReportingArtifactsResult(
        report_path=report_path,
        report_html_path=report_html_path,
        report_bundle_path=report_bundle_path,
        section_index_path=section_index_path,
        section_artifacts=section_artifacts,
        pending_formats=pending_formats,
        stage_artifacts=stage_artifacts,
    )
