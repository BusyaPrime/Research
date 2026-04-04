from __future__ import annotations

from collections.abc import Mapping

from alpha_research.config.models import ReportingConfig


SECTION_TITLES = {
    "executive_summary": "Итог по запуску",
    "time_semantics": "Временная семантика",
    "data_lineage": "Происхождение данных",
    "feature_catalog": "Каталог фич",
    "validation_protocol": "Схема валидации",
    "model_comparison": "Сравнение моделей",
    "backtest_results": "Результаты бэктеста",
    "cost_sensitivity": "Чувствительность к костам",
    "capacity_analysis": "Анализ capacity",
    "regime_analysis": "Анализ по режимам",
    "decay_analysis": "Анализ затухания сигнала",
    "limitations": "Ограничения",
    "next_steps": "Что делать дальше",
}


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


def render_final_report(
    reporting_config: ReportingConfig,
    *,
    project_name: str,
    section_payloads: Mapping[str, str] | None = None,
    limitations: list[str] | None = None,
    next_steps: list[str] | None = None,
) -> str:
    payloads = dict(section_payloads or {})
    limitation_items = limitations or ["TEMPORARY SIMPLIFICATION: отчет пока неполный."]
    next_step_items = next_steps or ["Добить оставшиеся слои платформы и дожать артефакты до воспроизводимого состояния."]

    lines = [f"# {project_name}", ""]
    for section in reporting_config.include_sections:
        title = SECTION_TITLES.get(section, section.replace("_", " ").title())
        lines.append(f"## {title}")
        if section == "executive_summary":
            lines.append(payloads.get(section, "Отчет по исследовательской платформе с predictive- и portfolio-диагностикой."))
        elif section == "limitations":
            lines.extend(f"- {item}" for item in limitation_items)
        elif section == "next_steps":
            lines.extend(f"- {item}" for item in next_step_items)
        else:
            lines.append(payloads.get(section, f"Временный stub для раздела «{title}»."))
        lines.append("")

    lines.append("## Обязательные графики")
    lines.extend(f"- {figure}" for figure in reporting_config.mandatory_figures)
    return "\n".join(lines).strip() + "\n"
