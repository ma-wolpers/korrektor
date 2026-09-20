from __future__ import annotations

from app.adapters.gui.dialog_services import messagebox

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui, widgets


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
        self._refresh_student_result_popup()
        self._student_result_popup.deiconify()
        self._student_result_popup.lift()

    def _build_student_result_popup(self) -> None:
        popup = ui.Toplevel(self.root)
        popup.title("Auswertung")
        popup.geometry("620x560")
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

        widgets.Button(body, text="Schliessen", style="SecondaryAction.TButton", command=self._close_student_result_popup).pack(
            anchor=ui.E, pady=(14, 0)
        )

        self._student_result_popup = popup

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

    def _close_student_result_popup(self) -> None:
        if self._student_result_popup is not None and self._student_result_popup.winfo_exists():
            popup_id = str(self._student_result_popup)
            self._popup_registry.close_popup(popup_id)
            self._tracked_popup_ids.discard(popup_id)
            self._student_result_popup.withdraw()
