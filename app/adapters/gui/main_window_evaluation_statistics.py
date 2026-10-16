"""Evaluation overview statistics: grade distribution ("Notenspiegel") and class competency profile.

Shown below the overview table. Everything comes finished from ``ExamEvaluation``:
``grades.rows`` (every grade of the scale, also with 0 persons), ``grades.ungraded``
(reason, count), ``grades.average_grade`` or its ``average_note``, and
``category_averages`` (mean of the persons' category percentages, with ``n``). The class
profile uses the chart type chosen in the export area / person view.
"""

from __future__ import annotations

from app.infrastructure.rendering.competency_chart_renderer import figure_to_png_bytes, render_bar_chart, render_radar_chart

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui, widgets


class MainWindowEvaluationStatisticsMixin:
    """Grade distribution and class competency profile of the overview."""

    def _build_evaluation_statistics(self, parent: widgets.Frame) -> None:
        """Two blocks: Notenspiegel (table + notes) and Kompetenzprofil der Klasse (chart + note)."""
        widgets.Label(parent, text="Notenspiegel", style="Title.TLabel").pack(anchor=ui.W, pady=(16, 0))
        tree = widgets.Treeview(parent, columns=("count",), show="tree headings", height=3, selectmode="none")
        tree.heading("#0", text="Note")
        tree.heading("count", text="Anzahl")
        tree.column("#0", width=160)
        tree.column("count", width=90, anchor=ui.CENTER)
        tree.pack(anchor=ui.W, pady=(4, 0))
        self._evaluation_grades_tree = tree
        self._evaluation_grades_note_var = ui.StringVar(value="")
        widgets.Label(parent, textvariable=self._evaluation_grades_note_var, style="Muted.TLabel", justify=ui.LEFT).pack(
            anchor=ui.W, pady=(4, 0)
        )
        widgets.Label(parent, text="Kompetenzprofil der Klasse", style="Title.TLabel").pack(anchor=ui.W, pady=(16, 0))
        self._evaluation_class_note_var = ui.StringVar(value="")
        widgets.Label(parent, textvariable=self._evaluation_class_note_var, style="Muted.TLabel", justify=ui.LEFT).pack(
            anchor=ui.W, pady=(4, 0)
        )
        self._evaluation_class_chart = widgets.Label(parent)
        self._evaluation_class_chart.pack(anchor=ui.W, pady=(4, 0))

    def _fill_evaluation_statistics(self) -> None:
        """Fill the grade table and notes, then the class profile."""
        data = self._evaluation_data
        if data is None:
            return
        grades = data.grades
        tree = self._evaluation_grades_tree
        tree.delete(*tree.get_children())
        for label, count in grades.rows:
            tree.insert("", ui.END, text=label, values=(count,))
        tree.configure(height=max(1, len(grades.rows)))
        lines = []
        if not grades.rows:
            lines.append("Kein Notenschlüssel zugeordnet.")
        if grades.average_grade is not None:
            lines.append(f"Notendurchschnitt: {grades.average_grade:g} (über {grades.graded_count} Personen)")
        elif grades.rows:
            lines.append(f"Kein Notendurchschnitt: {grades.average_note}.")
        lines.extend(f"Ohne Note: {count} ({reason})" for reason, count in grades.ungraded)
        self._evaluation_grades_note_var.set("\n".join(lines))
        self._refresh_evaluation_class_chart()

    def _refresh_evaluation_class_chart(self) -> None:
        """Class competency profile per category in the chosen chart type (or a note why there is none)."""
        data = self._evaluation_data
        if data is None:
            return
        averages = data.category_averages
        if not averages:
            self._evaluation_class_note_var.set("Noch kein Profil: Es gibt keine vollständig bewertete Kategorie.")
            self._evaluation_class_chart.configure(image="")
            self._evaluation_photos.pop("class_chart", None)
            return
        counts = ", ".join(f"{name}: {n}" for name, _percent, n in averages)
        self._evaluation_class_note_var.set(f"Mittel der Kategorie-Prozente pro Person – gezählte Personen: {counts}")
        values = [(name, percent) for name, percent, _n in averages]
        renderer = render_radar_chart if self._evaluation_chart_type_var.get() == "Spinnennetz" else render_bar_chart
        self._evaluation_photos["class_chart"] = ui.PhotoImage(data=figure_to_png_bytes(renderer(values, title="Klasse")))
        self._evaluation_class_chart.configure(image=self._evaluation_photos["class_chart"])
