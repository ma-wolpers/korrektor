from __future__ import annotations

from matplotlib.figure import Figure

from app.core.domain.student_result import (
    StudentResult,
    category_competency_percentages,
    task_competency_percentages,
)
from app.infrastructure.rendering.competency_chart_renderer import draw_bar, draw_radar

ALL_REPORT_SECTIONS: frozenset[str] = frozenset({"summary", "tasks", "categories", "chart"})


def _format_points(achieved: float | None, max_points: float) -> str:
    if achieved is None:
        return f"- / {max_points:g}"
    return f"{achieved:g} / {max_points:g}"


def render_student_result_report(
    result: StudentResult,
    *,
    chart_type: str = "Spinnennetz",
    chart_scope: str = "Pro Aufgabe",
    sections: frozenset[str] = ALL_REPORT_SECTIONS,
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

    `sections` (zentraler Exportmodus, Korrektor-Wunschliste) picks which
    of the four blocks to include - default is all four, identical to the
    original fixed layout (verified: with every section enabled, this
    produces the exact same `add_axes` coordinates as the pre-modular
    version). Blocks are stacked top-to-bottom in a fixed order (summary,
    then the task/category row, then the chart) using only as much
    vertical space as the *included* blocks need - an omitted block frees
    its space for whatever comes after it, rather than leaving a blank
    gap. Task and category tables sit side-by-side only when both are
    included; either alone takes the full row width. `sections == frozenset()`
    is tolerated here (renders just the title) - whether that is a valid
    *state* for a caller to reach is enforced one layer up (the
    zentraler-Exportmodus controller/GUI), not by this renderer.
    """
    fig = Figure(figsize=(8.27, 11.69))  # A4 portrait, in inches
    fig.suptitle(result.display_name, fontsize=16, fontweight="bold")

    show_summary = "summary" in sections
    show_tasks = "tasks" in sections
    show_categories = "categories" in sections
    show_chart = "chart" in sections

    cursor = 0.95  # upper bound of the still-free vertical space, below the title

    if show_summary:
        height = 0.05
        summary_axes = fig.add_axes((0.06, cursor - height, 0.88, height))
        summary_axes.axis("off")
        total_text = f"Gesamt: {_format_points(result.total_achieved_points, result.total_max_points)}"
        if result.grade_label is not None:
            total_text += f"  |  Note: {result.grade_label} ({result.grade_percentage:g}%)"
        summary_axes.text(0.0, 0.5, total_text, fontsize=12, va="center")
        cursor -= height + 0.05

    if show_tasks or show_categories:
        height = 0.30
        row_bottom = cursor - height
        task_axes = None
        category_axes = None
        if show_tasks and show_categories:
            task_axes = fig.add_axes((0.06, row_bottom, 0.40, height))
            category_axes = fig.add_axes((0.54, row_bottom, 0.40, height))
        elif show_tasks:
            task_axes = fig.add_axes((0.06, row_bottom, 0.88, height))
        else:
            category_axes = fig.add_axes((0.06, row_bottom, 0.88, height))

        if task_axes is not None:
            task_axes.axis("off")
            task_axes.set_title("Pro Aufgabe", fontsize=11, loc="left")
            if result.task_results:
                task_axes.table(
                    cellText=[
                        [task.task_code, task.category_name, _format_points(task.achieved_points, task.max_points)]
                        for task in result.task_results
                    ],
                    colLabels=["Aufgabe", "Kategorie", "Punkte"],
                    loc="upper left",
                    cellLoc="left",
                )
        if category_axes is not None:
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

        cursor = row_bottom - 0.07

    if show_chart:
        height = max(0.1, min(cursor - 0.04, 0.42))
        chart_axes = fig.add_axes((0.18, cursor - height, 0.64, height), polar=(chart_type == "Spinnennetz"))
        values = (
            category_competency_percentages(result) if chart_scope == "Pro Kategorie" else task_competency_percentages(result)
        )
        if chart_type == "Spinnennetz":
            draw_radar(chart_axes, values, title="Kompetenzgrad")
        else:
            draw_bar(chart_axes, values, title="Kompetenzgrad")

    return fig
