from __future__ import annotations

from dataclasses import dataclass
from html import escape
from collections.abc import Mapping

from alpha_research.config.models import ReportingConfig


SECTION_TITLES = {
    "executive_summary": "Итог по запуску",
    "time_semantics": "Временная семантика",
    "data_lineage": "Происхождение данных",
    "feature_catalog": "Каталог фич",
    "validation_protocol": "Схема валидации",
    "evaluation_protocol": "Контракт оценки",
    "uncertainty_analysis": "Статистическая неопределенность",
    "false_discovery_control": "Контроль ложных открытий",
    "model_registry": "Реестр моделей",
    "model_comparison": "Сравнение моделей",
    "model_stability": "Стабильность моделей",
    "backtest_results": "Результаты бэктеста",
    "cost_sensitivity": "Чувствительность к костам",
    "capacity_analysis": "Анализ capacity",
    "regime_analysis": "Анализ по режимам",
    "decay_analysis": "Анализ затухания сигнала",
    "ablation_analysis": "Ablation-анализ",
    "approval_summary": "Решение по запуску",
    "limitations": "Ограничения",
    "next_steps": "Что делать дальше",
}


@dataclass(frozen=True)
class RenderedReportSection:
    key: str
    title: str
    body: str


def render_executive_summary(
    *,
    project_name: str,
    headline: str,
    limitations: list[str],
    next_steps: list[str],
) -> str:
    lines = [f"# {project_name}", "", "## Итог по запуску", headline, ""]
    lines.append("### Ограничения")
    lines.extend(f"- {item}" for item in limitations)
    lines.append("")
    lines.append("### Что делать дальше")
    lines.extend(f"- {item}" for item in next_steps)
    return "\n".join(lines).strip() + "\n"


def render_report_sections(
    reporting_config: ReportingConfig,
    *,
    section_payloads: Mapping[str, str] | None = None,
    limitations: list[str] | None = None,
    next_steps: list[str] | None = None,
) -> list[RenderedReportSection]:
    payloads = dict(section_payloads or {})
    limitation_items = limitations or ["TEMPORARY SIMPLIFICATION: отчет пока неполный."]
    next_step_items = next_steps or ["Добить оставшиеся слои платформы и дожать артефакты до воспроизводимого состояния."]

    sections: list[RenderedReportSection] = []
    for section in reporting_config.include_sections:
        title = SECTION_TITLES.get(section, section.replace("_", " ").title())
        if section == "executive_summary":
            body = payloads.get(section, "Отчет по исследовательской платформе с predictive- и portfolio-диагностикой.")
        elif section == "limitations":
            body = "\n".join(f"- {item}" for item in limitation_items)
        elif section == "next_steps":
            body = "\n".join(f"- {item}" for item in next_step_items)
        else:
            body = payloads.get(section, f"Временный stub для раздела «{title}».")
        sections.append(RenderedReportSection(key=section, title=title, body=body))
    return sections


def render_final_report(
    reporting_config: ReportingConfig,
    *,
    project_name: str,
    section_payloads: Mapping[str, str] | None = None,
    limitations: list[str] | None = None,
    next_steps: list[str] | None = None,
) -> str:
    lines = [f"# {project_name}", ""]
    for section in render_report_sections(
        reporting_config,
        section_payloads=section_payloads,
        limitations=limitations,
        next_steps=next_steps,
    ):
        lines.append(f"## {section.title}")
        lines.append(section.body)
        lines.append("")

    lines.append("## Обязательные графики")
    lines.extend(f"- {figure}" for figure in reporting_config.mandatory_figures)
    return "\n".join(lines).strip() + "\n"


def _render_html_body(body: str) -> list[str]:
    lines: list[str] = []
    bullet_items = [line[2:].strip() for line in body.splitlines() if line.startswith("- ")]
    non_bullet_lines = [line.strip() for line in body.splitlines() if line.strip() and not line.startswith("- ")]
    if non_bullet_lines:
        lines.extend(f"<p>{escape(line)}</p>" for line in non_bullet_lines)
    if bullet_items:
        lines.append("<ul>")
        lines.extend(f"<li>{escape(item)}</li>" for item in bullet_items)
        lines.append("</ul>")
    if not non_bullet_lines and not bullet_items:
        lines.append("<p></p>")
    return lines


def render_final_report_html(
    reporting_config: ReportingConfig,
    *,
    project_name: str,
    section_payloads: Mapping[str, str] | None = None,
    limitations: list[str] | None = None,
    next_steps: list[str] | None = None,
) -> str:
    sections = render_report_sections(
        reporting_config,
        section_payloads=section_payloads,
        limitations=limitations,
        next_steps=next_steps,
    )
    lines = [
        "<!DOCTYPE html>",
        "<html lang=\"ru\">",
        "<head>",
        "  <meta charset=\"utf-8\">",
        f"  <title>{escape(project_name)}</title>",
        "  <style>",
        "    body { font-family: 'Segoe UI', sans-serif; margin: 40px auto; max-width: 960px; line-height: 1.6; color: #1f2937; }",
        "    h1, h2 { color: #111827; }",
        "    section { margin-bottom: 28px; }",
        "    ul { padding-left: 20px; }",
        "    code { background: #f3f4f6; padding: 2px 4px; border-radius: 4px; }",
        "  </style>",
        "</head>",
        "<body>",
        f"  <h1>{escape(project_name)}</h1>",
    ]
    for section in sections:
        lines.append("  <section>")
        lines.append(f"    <h2>{escape(section.title)}</h2>")
        lines.extend(f"    {line}" for line in _render_html_body(section.body))
        lines.append("  </section>")
    lines.append("  <section>")
    lines.append("    <h2>Обязательные графики</h2>")
    lines.append("    <ul>")
    lines.extend(f"      <li>{escape(figure)}</li>" for figure in reporting_config.mandatory_figures)
    lines.append("    </ul>")
    lines.append("  </section>")
    lines.append("</body>")
    lines.append("</html>")
    return "\n".join(lines) + "\n"
