"""Evaluation task view: one task across all persons.

Task cursor ``_evaluation_task_cursor`` over ``exam.tasks`` (natural order, as in the
correction view). Shows the task's ``TaskStatistics`` (Ø, Min–Max, bewertet x/n, fertig
x/n), one row per person from ``task_rows`` (points, %, fertig), the points distribution
(``points_histogram``) and the most frequent symbols of the task (``symbols_for_task``).
A click on a name opens the person view (same rule as in the overview). All values come
from the domain; this module formats and draws only.
"""

from __future__ import annotations

import base64

from app.adapters.gui import evaluation_format as fmt
from app.adapters.gui.main_window_correction_marker_palette import palette_icon_png
from app.core.domain.exam_evaluation import finished_pairs, points_histogram, task_rows
from app.infrastructure.rendering.competency_chart_renderer import figure_to_png_bytes, render_count_bar_chart

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.contracts import KeyModifiers
from bw_gui.contracts.events import EventResult
from bw_gui.runtime import bind_click, ui, widgets


class MainWindowEvaluationTaskMixin:
    """Task view of the evaluation window."""

    def _build_evaluation_task(self, parent: widgets.Frame) -> None:
        """Navigation, statistics line, person table, distribution chart, frequent symbols."""
        nav = widgets.Frame(parent)
        nav.pack(fill=ui.X)
        widgets.Button(nav, text="← Übersicht", style="SecondaryAction.TButton",
                       command=lambda: self._show_evaluation_view("overview")).pack(side=ui.LEFT)
        widgets.Button(nav, text="◀ Aufgabe", style="SecondaryAction.TButton",
                       command=lambda: self._on_evaluation_arrow(-1)).pack(side=ui.LEFT, padx=(12, 0))
        widgets.Button(nav, text="Aufgabe ▶", style="SecondaryAction.TButton",
                       command=lambda: self._on_evaluation_arrow(1)).pack(side=ui.LEFT, padx=(8, 0))
        self._evaluation_task_name_var = ui.StringVar(value="-")
        widgets.Label(nav, textvariable=self._evaluation_task_name_var, style="Title.TLabel").pack(side=ui.LEFT, padx=(16, 0))
        self._evaluation_task_stats_var = ui.StringVar(value="")
        widgets.Label(parent, textvariable=self._evaluation_task_stats_var, style="Muted.TLabel", justify=ui.LEFT).pack(
            anchor=ui.W, pady=(10, 0)
        )
        tree = widgets.Treeview(parent, columns=("name", "points", "percent", "finished"), show="headings", height=4, selectmode="none")
        for column, text, width in (("name", "Name", 200), ("points", "Punkte", 110), ("percent", "%", 80), ("finished", "fertig", 80)):
            tree.heading(column, text=text)
            tree.column(column, width=width, anchor=ui.W if column == "name" else ui.CENTER)
        tree.pack(anchor=ui.W, pady=(6, 0))
        bind_click(tree, self._on_evaluation_task_click)
        self._evaluation_task_tree = tree
        widgets.Label(parent, text="Punkteverteilung", style="Muted.TLabel").pack(anchor=ui.W, pady=(12, 0))
        self._evaluation_task_chart = widgets.Label(parent)
        self._evaluation_task_chart.pack(anchor=ui.W, pady=(4, 0))
        widgets.Label(parent, text="Häufigste Symbole", style="Muted.TLabel").pack(anchor=ui.W, pady=(12, 0))
        self._evaluation_task_symbols = widgets.Frame(parent)
        self._evaluation_task_symbols.pack(fill=ui.X, pady=(4, 0))

    def _current_evaluation_task(self):
        """``TaskStatistics`` of the task under the cursor, or ``None``."""
        data = self._evaluation_data
        if data is None or not data.task_statistics:
            return None
        return data.task_statistics[self._evaluation_task_cursor % len(data.task_statistics)]

    def _fill_evaluation_task(self) -> None:
        """Show the task under the cursor."""
        stat = self._current_evaluation_task()
        if stat is None or self._current_exam is None:
            return
        count = len(self._evaluation_data.task_statistics)
        self._evaluation_task_name_var.set(f"Aufgabe {stat.task_code} ({self._evaluation_task_cursor % count + 1}/{count})")
        span = fmt.UNSCORED if stat.minimum is None else f"{stat.minimum:g}–{stat.maximum:g}"
        average = fmt.number(None if stat.average is None else round(stat.average, 2))
        self._evaluation_task_stats_var.set(
            f"{'Bonusaufgabe · ' if stat.is_bonus else ''}Max. {stat.max_points:g} Punkte · Ø {average} ({fmt.percent(stat.average_percent)}) · Min–Max {span} · "
            f"bewertet {fmt.count_of(stat.scored_count, stat.total_count)} · fertig {fmt.count_of(stat.finished_count, stat.total_count)}"
        )
        rows = task_rows(self._evaluation_data.results, finished_pairs(self._current_exam.person_task_completions), stat.task_code)
        tree = self._evaluation_task_tree
        tree.delete(*tree.get_children())
        for row in rows:
            tree.insert("", ui.END, iid=row.student_id, values=(
                row.display_name, fmt.points(row.achieved_points, row.max_points), fmt.percent(row.percent), "✓" if row.finished else ""))
        tree.configure(height=max(1, len(rows)))
        figure = render_count_bar_chart(points_histogram(rows), xlabel="Punkte", ylabel="Personen")
        self._evaluation_photos["task_chart"] = ui.PhotoImage(data=figure_to_png_bytes(figure))
        self._evaluation_task_chart.configure(image=self._evaluation_photos["task_chart"])
        self._fill_evaluation_task_symbols(stat.task_code)

    def _fill_evaluation_task_symbols(self, task_code: str) -> None:
        """Icon, name and count of the task's most frequent symbols."""
        frame = self._evaluation_task_symbols
        for child in frame.winfo_children():
            child.destroy()
        usages = self._controller.frequent_symbols_for_task(exam=self._current_exam, task_code=task_code)
        if not usages:
            widgets.Label(frame, text="Bei dieser Aufgabe wurden noch keine Symbole gesetzt.", style="Muted.TLabel").pack(anchor=ui.W)
            return
        for index, usage in enumerate(usages):
            photo = ui.PhotoImage(data=base64.b64encode(palette_icon_png(usage.content, self._default_annotation_color_hex)).decode("ascii"), format="png")
            self._evaluation_photos[f"task_symbol_{index}"] = photo
            row = widgets.Frame(frame)
            row.pack(anchor=ui.W, pady=(0, 2))
            widgets.Label(row, image=photo).pack(side=ui.LEFT)
            widgets.Label(row, text=f"{usage.label} – {usage.count}×").pack(side=ui.LEFT, padx=(8, 0))

    def _on_evaluation_task_click(self, event):
        """Click on a name (no modifier) -> person view."""
        modifiers = event.modifiers
        if isinstance(modifiers, KeyModifiers) and (modifiers.control or modifiers.shift):
            return None
        tree = self._evaluation_task_tree
        if tree.identify_region(event.x, event.y) == "cell" and tree.identify_column(event.x) == "#1":
            row = tree.identify_row(event.y)
            if row:
                self._show_evaluation_person(row)
                return EventResult.HANDLED
        return None
