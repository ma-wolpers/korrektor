from __future__ import annotations

from matplotlib.figure import Figure

from app.core.domain.student_result import (
    StudentResult,
    category_competency_percentages,
    task_competency_percentages,
)
from app.infrastructure.rendering.competency_chart_renderer import draw_bar, draw_radar


def _format_points(achieved: float | None, max_points: float) -> str:
    if achieved is None:
        return f"- / {max_points:g}"
    return f"{achieved:g} / {max_points:g}"


def render_student_result_report(
    result: StudentResult,
    *,
    chart_type: str = "Spinnennetz",
    chart_scope: str = "Pro Aufgabe",
) -> Figure:
    """Compose one full-page Auswertungs-Report for `result`: summary, per-task/-category tables, and a chart.

    Meilenstein 7 der Korrektor-Wunschliste: the export must represent the
    *complete* `StudentResult`, not just the chart - `matplotlib.savefig()`
    (called by the export usecase on the `Figure` this returns) is only the
    technical output mechanism, the actual "what goes into the export" is
    decided entirely here. Reuses `draw_radar`/`draw_bar`
    (`competency_chart_renderer.py`) for the chart panel instead of
    duplicating that drawing logic - this function only owns the page
    layout (`Figure.add_axes` placement) and the text/table panels.
    """
    fig = Figure(figsize=(8.27, 11.69))  # A4 portrait, in inches
    fig.suptitle(result.display_name, fontsize=16, fontweight="bold")

    summary_axes = fig.add_axes((0.06, 0.90, 0.88, 0.05))
    summary_axes.axis("off")
    total_text = f"Gesamt: {_format_points(result.total_achieved_points, result.total_max_points)}"
    if result.grade_label is not None:
        total_text += f"  |  Note: {result.grade_label} ({result.grade_percentage:g}%)"
    summary_axes.text(0.0, 0.5, total_text, fontsize=12, va="center")

    task_axes = fig.add_axes((0.06, 0.55, 0.40, 0.30))
    task_axes.axis("off")
    task_axes.set_title("Pro Aufgabe", fontsize=11, loc="left")
    if result.task_results:
        task_axes.table(
            cellText=[[task.task_code, _format_points(task.achieved_points, task.max_points)] for task in result.task_results],
            colLabels=["Aufgabe", "Punkte"],
            loc="upper left",
            cellLoc="left",
        )

    category_axes = fig.add_axes((0.54, 0.55, 0.40, 0.30))
    category_axes.axis("off")
    category_axes.set_title("Pro Kategorie", fontsize=11, loc="left")
    if result.category_results:
        category_axes.table(
            cellText=[
                [category.name, _format_points(category.achieved_points, category.max_points)]
                for category in result.category_results
            ],
            colLabels=["Kategorie", "Punkte"],
            loc="upper left",
            cellLoc="left",
        )
    else:
        category_axes.text(0.0, 0.9, "Keine Kategorien", fontsize=9, va="top")

    values = category_competency_percentages(result) if chart_scope == "Pro Kategorie" else task_competency_percentages(result)
    is_radar = chart_type == "Spinnennetz"
    chart_axes = fig.add_axes((0.18, 0.06, 0.64, 0.42), polar=is_radar)
    if is_radar:
        draw_radar(chart_axes, values, title="Kompetenzgrad")
    else:
        draw_bar(chart_axes, values, title="Kompetenzgrad")

    return fig
