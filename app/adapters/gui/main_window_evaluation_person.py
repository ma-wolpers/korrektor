"""Evaluation person view: one person's result (moved here from the former result popup).

Shows ``StudentResult`` from ``_evaluation_data`` (person cursor ``_evaluation_person_cursor``,
order ``exam.students``): summary with grade or the domain's reason for a missing grade,
tables "Pro Aufgabe" and "Pro Kategorie", and the competency chart. Chart type and
scope share their variables with the overview's export area, so the feedback page and
the export always use what is shown here. Nothing is computed here.
"""

from __future__ import annotations

from app.adapters.gui import evaluation_format as fmt
from app.adapters.gui.main_window_constants import COMPETENCY_CHART_SCOPE_LABELS, COMPETENCY_CHART_TYPE_LABELS
from app.core.domain.student_result import category_competency_percentages, task_competency_percentages
from app.infrastructure.rendering.competency_chart_renderer import figure_to_png_bytes, render_bar_chart, render_radar_chart

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui, widgets


class MainWindowEvaluationPersonMixin:
    """Person view of the evaluation window."""

    def _build_evaluation_person(self, parent: widgets.Frame) -> None:
        """Navigation, summary, the two tables and the chart."""
        nav = widgets.Frame(parent)
        nav.pack(fill=ui.X)
        widgets.Button(nav, text="← Übersicht", style="SecondaryAction.TButton",
                       command=lambda: self._show_evaluation_view("overview")).pack(side=ui.LEFT)
        widgets.Button(nav, text="◀ Person", style="SecondaryAction.TButton",
                       command=lambda: self._on_evaluation_arrow(-1)).pack(side=ui.LEFT, padx=(12, 0))
        widgets.Button(nav, text="Person ▶", style="SecondaryAction.TButton",
                       command=lambda: self._on_evaluation_arrow(1)).pack(side=ui.LEFT, padx=(8, 0))
        self._evaluation_person_name_var = ui.StringVar(value="-")
        widgets.Label(nav, textvariable=self._evaluation_person_name_var, style="Title.TLabel").pack(side=ui.LEFT, padx=(16, 0))

        self._evaluation_person_summary_var = ui.StringVar(value="")
        widgets.Label(parent, textvariable=self._evaluation_person_summary_var, style="Muted.TLabel", justify=ui.LEFT).pack(
            anchor=ui.W, pady=(10, 0)
        )
        widgets.Label(parent, text="Pro Aufgabe", style="Muted.TLabel").pack(anchor=ui.W, pady=(12, 0))
        tasks_tree = widgets.Treeview(parent, columns=("category", "points"), show="tree headings", height=8)
        for column, text, width in (("#0", "Aufgabe", 140), ("category", "Kategorie", 160), ("points", "Punkte", 120)):
            tasks_tree.heading(column, text=text)
            tasks_tree.column(column, width=width, anchor=ui.W if column != "points" else ui.CENTER)
        tasks_tree.pack(fill=ui.X, pady=(4, 0))
        widgets.Label(parent, text="Pro Kategorie", style="Muted.TLabel").pack(anchor=ui.W, pady=(12, 0))
        categories_tree = widgets.Treeview(parent, columns=("points",), show="tree headings", height=5)
        for column, text, width in (("#0", "Kategorie", 160), ("points", "Punkte", 120)):
            categories_tree.heading(column, text=text)
            categories_tree.column(column, width=width, anchor=ui.W if column == "#0" else ui.CENTER)
        categories_tree.pack(fill=ui.X, pady=(4, 0))

        chart_controls = widgets.Frame(parent)
        chart_controls.pack(fill=ui.X, pady=(12, 0))
        widgets.Label(chart_controls, text="Kompetenzgrad", style="Muted.TLabel").pack(side=ui.LEFT)
        for variable, values, width in ((self._evaluation_chart_type_var, COMPETENCY_CHART_TYPE_LABELS, 12),
                                        (self._evaluation_chart_scope_var, COMPETENCY_CHART_SCOPE_LABELS, 14)):
            widgets.Combobox(chart_controls, textvariable=variable, state="readonly", width=width, values=values).pack(side=ui.LEFT, padx=(8, 0))
            variable.trace_add("write", lambda *_args: self._refresh_evaluation_charts())
        self._evaluation_person_chart = widgets.Label(parent)
        self._evaluation_person_chart.pack(fill=ui.X, pady=(6, 0))
        self._evaluation_person_tasks_tree = tasks_tree
        self._evaluation_person_categories_tree = categories_tree

    def _current_evaluation_result(self):
        """``StudentResult`` of the person under the cursor, or ``None``."""
        data = self._evaluation_data
        if data is None or not data.results:
            return None
        return data.results[self._evaluation_person_cursor % len(data.results)]

    def _fill_evaluation_person(self) -> None:
        """Show the person under the cursor."""
        result = self._current_evaluation_result()
        if result is None:
            return
        count = len(self._evaluation_data.results)
        self._evaluation_person_name_var.set(f"{result.display_name} ({self._evaluation_person_cursor % count + 1}/{count})")
        if result.grade_label is not None:
            grade = f" | Note: {result.grade_label} ({result.grade_percentage:g} %)"
        else:
            grade = f" | Note: – ({self._evaluation_data.grade_reasons.get(result.student_id, '')})"
        self._evaluation_person_summary_var.set(f"Gesamt: {fmt.points(result.total_achieved_points, result.total_max_points)}{grade}")
        tasks_tree = self._evaluation_person_tasks_tree
        tasks_tree.delete(*tasks_tree.get_children())
        for task in result.task_results:
            tasks_tree.insert("", ui.END, text=task.task_code, values=(task.category_name, fmt.points(task.achieved_points, task.max_points)))
        categories_tree = self._evaluation_person_categories_tree
        categories_tree.delete(*categories_tree.get_children())
        for category in result.category_results:
            categories_tree.insert("", ui.END, text=category.name, values=(fmt.points(category.achieved_points, category.max_points),))
        self._refresh_evaluation_person_chart()

    def _refresh_evaluation_person_chart(self) -> None:
        """Competency chart of the person under the cursor (percentages from the domain)."""
        result = self._current_evaluation_result()
        if result is None:
            return
        by_category = self._evaluation_chart_scope_var.get() == "Pro Kategorie"
        values = category_competency_percentages(result) if by_category else task_competency_percentages(result)
        renderer = render_radar_chart if self._evaluation_chart_type_var.get() == "Spinnennetz" else render_bar_chart
        self._evaluation_photos["person_chart"] = ui.PhotoImage(data=figure_to_png_bytes(renderer(values, title=result.display_name)))
        self._evaluation_person_chart.configure(image=self._evaluation_photos["person_chart"])

    def _refresh_evaluation_charts(self) -> None:
        """Chart type/scope changed: redraw the person chart (if shown) and the class profile."""
        if not self._evaluation_open() or self._evaluation_data is None:
            return
        if self._evaluation_view == "person":
            self._refresh_evaluation_person_chart()
        self._refresh_evaluation_class_chart()
