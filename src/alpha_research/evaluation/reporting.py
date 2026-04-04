from __future__ import annotations

from collections.abc import Mapping

from alpha_research.config.models import ReportingConfig


SECTION_TITLES = {
    "executive_summary": "Executive Summary",
    "time_semantics": "Time Semantics",
    "data_lineage": "Data Lineage",
    "feature_catalog": "Feature Catalog",
    "validation_protocol": "Validation Protocol",
    "model_comparison": "Model Comparison",
    "backtest_results": "Backtest Results",
    "cost_sensitivity": "Cost Sensitivity",
    "capacity_analysis": "Capacity Analysis",
    "regime_analysis": "Regime Analysis",
    "decay_analysis": "Decay Analysis",
    "limitations": "Limitations",
    "next_steps": "Next Steps",
}


def render_executive_summary(
    *,
    project_name: str,
    headline: str,
    limitations: list[str],
    next_steps: list[str],
) -> str:
    lines = [f"# {project_name}", "", "## Executive Summary", headline, ""]
    lines.append("### Limitations")
    lines.extend(f"- {item}" for item in limitations)
    lines.append("")
    lines.append("### Next Steps")
    lines.extend(f"- {item}" for item in next_steps)
    return "\n".join(lines).strip() + "\n"


def render_final_report(
    reporting_config: ReportingConfig,
    *,
    project_name: str,
    section_payloads: Mapping[str, str] | None = None,
    limitations: list[str] | None = None,
    next_steps: list[str] | None = None,
) -> str:
    payloads = dict(section_payloads or {})
    limitation_items = limitations or ["TEMPORARY SIMPLIFICATION: report content incomplete."]
    next_step_items = next_steps or ["Implement remaining platform layers and harden artifacts."]

    lines = [f"# {project_name}", ""]
    for section in reporting_config.include_sections:
        title = SECTION_TITLES.get(section, section.replace("_", " ").title())
        lines.append(f"## {title}")
        if section == "executive_summary":
            lines.append(payloads.get(section, "Alpha research platform report covering predictive and portfolio diagnostics."))
        elif section == "limitations":
            lines.extend(f"- {item}" for item in limitation_items)
        elif section == "next_steps":
            lines.extend(f"- {item}" for item in next_step_items)
        else:
            lines.append(payloads.get(section, f"Stub section for {title}."))
        lines.append("")

    lines.append("## Mandatory Figures")
    lines.extend(f"- {figure}" for figure in reporting_config.mandatory_figures)
    return "\n".join(lines).strip() + "\n"
