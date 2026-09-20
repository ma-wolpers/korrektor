from __future__ import annotations

from pathlib import Path

from app.adapters.gui.dialog_services import filedialog, messagebox
from app.adapters.gui.main_window_constants import COMPETENCY_CHART_SCOPE_LABELS, COMPETENCY_CHART_TYPE_LABELS
from app.core.domain.student_result import category_competency_percentages, task_competency_percentages
from app.infrastructure.rendering.competency_chart_renderer import figure_to_png_bytes, render_bar_chart, render_radar_chart

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui, widgets

_EXPORT_FORMAT_LABELS: tuple[str, ...] = ("PNG", "JPG", "PDF")
_EXPORT_EXTENSION_BY_LABEL: dict[str, str] = {"PNG": "png", "JPG": "jpg", "PDF": "pdf"}


def _format_points(achieved: float | None, max_points: float) -> str:
    if achieved is None:
        return f"- / {max_points:g}"
    return f"{achieved:g} / {max_points:g}"


class MainWindowStudentResultMixin:
    """Ergebnis-Uebersichtsseite pro Schueler:in (Meilenstein 5): Popup mit Personen-Navigation.

    Zeigt `compute_student_result_for_exam`'s Ergebnis rein tabellarisch;
    berechnet selbst nichts fachlich (Grundregel 1) - jede Zahl kommt
    fertig vom Controller/der Domain-Funktion `compute_student_result`.
    Scores werden einmal pro Popup-Oeffnen geladen (`load_scores_for_exam`),
    nicht pro Personenwechsel neu von der CSV gelesen.
    """

    def _open_student_result_popup(self) -> None:
        if self._controller is None or self._current_exam is None:
            return
        if not self._current_exam.students:
            messagebox.showinfo("Hinweis", "Diese Klausur hat keine Schueler:innen.")
            return
        if self._student_result_popup is None or not self._student_result_popup.winfo_exists():
            self._build_student_result_popup()
        else:
            self._register_popup_window(self._student_result_popup)
        self._student_result_scores = self._controller.load_scores_for_exam(exam=self._current_exam)
        self._student_result_cursor = 0
        self._student_result_export_list.delete(0, ui.END)
        for student in self._current_exam.students:
            self._student_result_export_list.insert(ui.END, student.display_name)
        self._student_result_export_list.select_set(0, ui.END)
        self._refresh_student_result_popup()
        self._student_result_popup.deiconify()
        self._student_result_popup.lift()

    def _build_student_result_popup(self) -> None:
        popup = ui.Toplevel(self.root)
        popup.title("Auswertung")
        popup.geometry("640x760")
        popup.transient(self.root)
        self._register_popup_window(popup)
        popup.protocol("WM_DELETE_WINDOW", self._close_student_result_popup)

        body = widgets.Frame(popup, padding=10)
        body.pack(fill=ui.BOTH, expand=True)

        nav = widgets.Frame(body, style="Surface.TFrame")
        nav.pack(fill=ui.X)
        widgets.Button(
            nav, text="◀ Person", style="SecondaryAction.TButton", command=lambda: self._move_student_result_cursor(-1)
        ).pack(side=ui.LEFT)
        widgets.Button(
            nav, text="Person ▶", style="SecondaryAction.TButton", command=lambda: self._move_student_result_cursor(1)
        ).pack(side=ui.LEFT, padx=(8, 0))
        self._student_result_name_var = ui.StringVar(value="-")
        widgets.Label(nav, textvariable=self._student_result_name_var, style="Title.TLabel").pack(side=ui.LEFT, padx=(16, 0))

        self._student_result_summary_var = ui.StringVar(value="")
        widgets.Label(body, textvariable=self._student_result_summary_var, style="Muted.TLabel", justify=ui.LEFT).pack(
            anchor=ui.W, pady=(10, 0)
        )

        widgets.Label(body, text="Pro Aufgabe", style="Muted.TLabel").pack(anchor=ui.W, pady=(12, 0))
        self._student_result_tasks_tree = widgets.Treeview(body, columns=("points",), show="tree headings", height=8)
        self._student_result_tasks_tree.heading("#0", text="Aufgabe")
        self._student_result_tasks_tree.heading("points", text="Punkte")
        self._student_result_tasks_tree.column("#0", width=140)
        self._student_result_tasks_tree.column("points", width=120, anchor=ui.CENTER)
        self._student_result_tasks_tree.pack(fill=ui.X, pady=(4, 0))

        widgets.Label(body, text="Pro Kategorie", style="Muted.TLabel").pack(anchor=ui.W, pady=(12, 0))
        self._student_result_categories_tree = widgets.Treeview(body, columns=("points",), show="tree headings", height=6)
        self._student_result_categories_tree.heading("#0", text="Kategorie")
        self._student_result_categories_tree.heading("points", text="Punkte")
        self._student_result_categories_tree.column("#0", width=140)
        self._student_result_categories_tree.column("points", width=120, anchor=ui.CENTER)
        self._student_result_categories_tree.pack(fill=ui.X, pady=(4, 0))

        chart_controls = widgets.Frame(body, style="Surface.TFrame")
        chart_controls.pack(fill=ui.X, pady=(12, 0))
        widgets.Label(chart_controls, text="Kompetenzgrad", style="Muted.TLabel").pack(side=ui.LEFT)
        self._student_result_chart_type_var = ui.StringVar(value=COMPETENCY_CHART_TYPE_LABELS[0])
        widgets.Combobox(
            chart_controls,
            textvariable=self._student_result_chart_type_var,
            state="readonly",
            width=12,
            values=COMPETENCY_CHART_TYPE_LABELS,
        ).pack(side=ui.LEFT, padx=(8, 0))
        self._student_result_chart_scope_var = ui.StringVar(value=COMPETENCY_CHART_SCOPE_LABELS[0])
        chart_scope_combo = widgets.Combobox(
            chart_controls,
            textvariable=self._student_result_chart_scope_var,
            state="readonly",
            width=14,
            values=COMPETENCY_CHART_SCOPE_LABELS,
        )
        chart_scope_combo.pack(side=ui.LEFT, padx=(8, 0))
        self._student_result_chart_type_var.trace_add("write", lambda *_args: self._refresh_student_result_chart())
        self._student_result_chart_scope_var.trace_add("write", lambda *_args: self._refresh_student_result_chart())

        self._student_result_chart_label = widgets.Label(body)
        self._student_result_chart_label.pack(fill=ui.X, pady=(6, 0))

        export_controls = widgets.Frame(body, style="Surface.TFrame")
        export_controls.pack(fill=ui.X, pady=(12, 0))
        widgets.Label(export_controls, text="Export", style="Muted.TLabel").pack(anchor=ui.W)
        self._student_result_export_list = ui.Listbox(export_controls, selectmode=ui.EXTENDED, height=5, exportselection=False)
        self._student_result_export_list.pack(fill=ui.X, pady=(4, 0))
        self._attach_hover_help(
            self._student_result_export_list, label="Auswahl der zu exportierenden Personen (Mehrfachauswahl moeglich)"
        )

        export_actions = widgets.Frame(export_controls, style="Surface.TFrame")
        export_actions.pack(fill=ui.X, pady=(6, 0))
        self._student_result_export_format_var = ui.StringVar(value=_EXPORT_FORMAT_LABELS[0])
        widgets.Combobox(
            export_actions,
            textvariable=self._student_result_export_format_var,
            state="readonly",
            width=6,
            values=_EXPORT_FORMAT_LABELS,
        ).pack(side=ui.LEFT)
        widgets.Button(
            export_actions,
            text="Exportieren...",
            style="SecondaryAction.TButton",
            command=self._export_selected_student_results,
        ).pack(side=ui.LEFT, padx=(8, 0))

        widgets.Button(body, text="Schliessen", style="SecondaryAction.TButton", command=self._close_student_result_popup).pack(
            anchor=ui.E, pady=(14, 0)
        )

        self._student_result_popup = popup
        self._student_result_current_result = None

    def _move_student_result_cursor(self, delta: int) -> None:
        if self._current_exam is None or not self._current_exam.students:
            return
        self._student_result_cursor = (self._student_result_cursor + delta) % len(self._current_exam.students)
        self._refresh_student_result_popup()

    def _refresh_student_result_popup(self) -> None:
        if self._current_exam is None or self._controller is None or self._student_result_scores is None:
            return
        students = self._current_exam.students
        if not students:
            return
        student = students[self._student_result_cursor % len(students)]
        result = self._controller.compute_student_result_for_exam(
            exam=self._current_exam, student_id=student.student_id, scores=self._student_result_scores
        )
        if result is None:
            return

        self._student_result_name_var.set(f"{result.display_name} ({self._student_result_cursor + 1}/{len(students)})")

        total_text = _format_points(result.total_achieved_points, result.total_max_points)
        if result.grade_label is not None:
            grade_text = f" | Note: {result.grade_label} ({result.grade_percentage:g}%)"
        elif self._current_exam.grading_scale_snapshot is not None:
            grade_text = " | Note: noch nicht ermittelbar (unvollstaendig oder ausserhalb der Notenstufen)"
        else:
            grade_text = ""
        self._student_result_summary_var.set(f"Gesamt: {total_text}{grade_text}")

        self._student_result_tasks_tree.delete(*self._student_result_tasks_tree.get_children())
        for task in result.task_results:
            self._student_result_tasks_tree.insert(
                "", ui.END, text=task.task_code, values=(_format_points(task.achieved_points, task.max_points),)
            )

        self._student_result_categories_tree.delete(*self._student_result_categories_tree.get_children())
        for category in result.category_results:
            self._student_result_categories_tree.insert(
                "", ui.END, text=category.name, values=(_format_points(category.achieved_points, category.max_points),)
            )

        self._student_result_current_result = result
        self._refresh_student_result_chart()

    def _refresh_student_result_chart(self) -> None:
        """Re-render the Kompetenzgrad-Diagramm for the current student/type/scope selection.

        Only rendering happens here (Meilenstein 6): the percentages
        themselves come pre-computed from `task_competency_percentages`/
        `category_competency_percentages` (Domain), this method just picks
        which of those to call and which renderer to hand them to, then
        converts the resulting matplotlib `Figure` to a `tk.PhotoImage`.
        """
        if self._student_result_current_result is None or not hasattr(self, "_student_result_chart_label"):
            return
        result = self._student_result_current_result
        scope = self._student_result_chart_scope_var.get()
        chart_type = self._student_result_chart_type_var.get()

        values = category_competency_percentages(result) if scope == "Pro Kategorie" else task_competency_percentages(result)
        renderer = render_radar_chart if chart_type == "Spinnennetz" else render_bar_chart
        figure = renderer(values, title=result.display_name)

        self._student_result_chart_photo = ui.PhotoImage(data=figure_to_png_bytes(figure))
        self._student_result_chart_label.configure(image=self._student_result_chart_photo)

    def _export_selected_student_results(self) -> None:
        """Ask for a target folder, then export one full report file per selected student.

        Selection defaults to "all students" (pre-selected when the list
        is populated) but can be narrowed - matches "ausgewaehlte
        Ergebnisse" in the Korrektor-Wunschliste, not an all-or-nothing
        export.
        """
        if self._current_exam is None or self._controller is None or self._student_result_scores is None:
            return
        selected_indices = self._student_result_export_list.curselection()
        if not selected_indices:
            messagebox.showinfo("Hinweis", "Bitte mindestens eine Person auswaehlen.")
            return
        students = self._current_exam.students
        student_ids = [students[index].student_id for index in selected_indices if index < len(students)]

        target_dir = filedialog.askdirectory(title="Zielordner fuer den Export waehlen")
        if not target_dir:
            return

        extension = _EXPORT_EXTENSION_BY_LABEL[self._student_result_export_format_var.get()]
        exported, failed = self._controller.export_student_results(
            exam=self._current_exam,
            student_ids=student_ids,
            scores=self._student_result_scores,
            chart_type=self._student_result_chart_type_var.get(),
            chart_scope=self._student_result_chart_scope_var.get(),
            output_dir=Path(target_dir),
            file_extension=extension,
        )

        if failed:
            messagebox.showwarning(
                "Export teilweise fehlgeschlagen",
                f"{len(exported)} exportiert, fehlgeschlagen fuer: {', '.join(failed)}",
            )
        else:
            messagebox.showinfo("Export abgeschlossen", f"{len(exported)} Ergebnis(se) exportiert nach:\n{target_dir}")

    def _close_student_result_popup(self) -> None:
        if self._student_result_popup is not None and self._student_result_popup.winfo_exists():
            popup_id = str(self._student_result_popup)
            self._popup_registry.close_popup(popup_id)
            self._tracked_popup_ids.discard(popup_id)
            self._student_result_popup.withdraw()
