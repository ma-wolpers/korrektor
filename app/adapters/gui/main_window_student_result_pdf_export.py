from __future__ import annotations

from app.adapters.gui.dialog_services import messagebox

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui, widgets


class MainWindowStudentResultPdfExportMixin:
    """Statistikseite an die echte Klausur-PDF anhängen/entfernen (GUI-Teil).

    Eigene Datei statt weiterem Wachstum von `main_window_student_result.py`
    (Datei-Groessen-Konvention). Baut zwei Buttons unterhalb des
    bestehenden Datei-Export-Bereichs im Auswertungspopup, wiederverwendet
    dessen Mehrfachauswahl-Liste (`_student_result_export_list`) und
    `chart_type`/`chart_scope`-Variablen - kein Zielordner-Dialog noetig,
    es wird direkt die vorhandene Klausur-PDF pro Person veraendert.
    """

    def _build_student_result_pdf_export_controls(self, export_controls) -> None:
        pdf_export_row = widgets.Frame(export_controls, style="Surface.TFrame")
        pdf_export_row.pack(fill=ui.X, pady=(6, 0))
        append_button = widgets.Button(
            pdf_export_row,
            text="An PDF anhängen",
            style="SecondaryAction.TButton",
            command=self._append_student_result_report_to_pdfs,
        )
        append_button.pack(side=ui.LEFT)
        self._attach_hover_help(
            append_button,
            label="Fügt die Auswertungs-Report-Seite als letzte Seite der jeweiligen Klausur-PDF an "
            "(ersetzt eine zuvor angehängte Statistikseite statt sie zu duplizieren)",
        )
        remove_button = widgets.Button(
            pdf_export_row,
            text="Von PDF entfernen",
            style="SecondaryAction.TButton",
            command=self._remove_student_result_report_from_pdfs,
        )
        remove_button.pack(side=ui.LEFT, padx=(8, 0))
        self._attach_hover_help(remove_button, label="Entfernt eine zuvor angehängte Statistikseite wieder von der Klausur-PDF")

    def _selected_student_result_ids(self) -> list[str] | None:
        if self._current_exam is None:
            return None
        selected_indices = self._student_result_export_list.curselection()
        if not selected_indices:
            messagebox.showinfo("Hinweis", "Bitte mindestens eine Person auswaehlen.")
            return None
        students = self._current_exam.students
        return [students[index].student_id for index in selected_indices if index < len(students)]

    def _append_student_result_report_to_pdfs(self) -> None:
        if self._current_exam is None or self._controller is None or self._student_result_scores is None:
            return
        student_ids = self._selected_student_result_ids()
        if not student_ids:
            return
        updated = self._controller.append_student_result_report_to_pdfs_immediate(
            exam=self._current_exam,
            student_ids=student_ids,
            scores=self._student_result_scores,
            chart_type=self._student_result_chart_type_var.get(),
            chart_scope=self._student_result_chart_scope_var.get(),
        )
        if updated is None:
            return
        self._current_exam = updated

    def _remove_student_result_report_from_pdfs(self) -> None:
        if self._current_exam is None or self._controller is None:
            return
        student_ids = self._selected_student_result_ids()
        if not student_ids:
            return
        updated = self._controller.remove_student_result_report_from_pdfs_immediate(
            exam=self._current_exam, student_ids=student_ids
        )
        if updated is None:
            return
        self._current_exam = updated
