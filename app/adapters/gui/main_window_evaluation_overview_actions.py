"""Evaluation overview actions on the selected persons: feedback page, file export, batch export.

All actions reuse the existing controller methods unchanged:

* "Feedbackseite anhängen/aktualisieren": ``append_student_result_report_to_pdfs_immediate``
  for the whole selection - persons that already have a page get it replaced
  (``replace_existing``), so a mixed selection is fine. One undo step per action.
* "Feedbackseite entfernen": the controller requires every given person to have a page,
  so only selected persons **with** a page are passed; the others are named as skipped.
* Errors: the controller is all-or-nothing with rollback and its own error message;
  the window then simply shows the unchanged state.
* After every action the window reloads (``_refresh_evaluation``); undo/redo reload via
  ``refresh_exam_content_in_place``. The status column therefore always mirrors
  ``StudentExam.stats_report_appended``, which the controller keeps in line with the PDFs.
"""

from __future__ import annotations

from pathlib import Path

from app.adapters.gui.dialog_services import filedialog, messagebox
from app.adapters.gui.main_window_constants import COMPETENCY_CHART_SCOPE_LABELS, COMPETENCY_CHART_TYPE_LABELS

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import treeview_selection, ui, widgets

EXPORT_FORMATS: dict[str, str] = {"PNG": "png", "JPG": "jpg", "PDF": "pdf"}


class MainWindowEvaluationOverviewActionsMixin:
    """Selection buttons, feedback page and export actions of the overview."""

    def _build_evaluation_overview_actions(self, parent: widgets.Frame) -> None:
        """Rows: selection · chart for page/export · feedback page · file export."""
        selection_row = widgets.Frame(parent)
        selection_row.pack(fill=ui.X, pady=(8, 0))
        widgets.Button(selection_row, text="Alle auswählen", style="SecondaryAction.TButton",
                       command=self._select_all_evaluation_rows).pack(side=ui.LEFT)
        widgets.Button(selection_row, text="Auswahl aufheben", style="SecondaryAction.TButton",
                       command=lambda: treeview_selection.clear(self._evaluation_overview_tree)).pack(side=ui.LEFT, padx=(8, 0))

        chart_row = widgets.Frame(parent)
        chart_row.pack(fill=ui.X, pady=(8, 0))
        widgets.Label(chart_row, text="Diagramm für Feedbackseite und Export", style="Muted.TLabel").pack(side=ui.LEFT)
        for variable, values, width in ((self._evaluation_chart_type_var, COMPETENCY_CHART_TYPE_LABELS, 12),
                                        (self._evaluation_chart_scope_var, COMPETENCY_CHART_SCOPE_LABELS, 14)):
            widgets.Combobox(chart_row, textvariable=variable, state="readonly", width=width, values=values).pack(side=ui.LEFT, padx=(8, 0))

        page_row = widgets.Frame(parent)
        page_row.pack(fill=ui.X, pady=(8, 0))
        append = widgets.Button(page_row, text="Feedbackseite anhängen/aktualisieren", style="SecondaryAction.TButton",
                                command=self._append_evaluation_feedback)
        append.pack(side=ui.LEFT)
        self._attach_hover_help(append, label="Hängt die Auswertungsseite an die PDFs der ausgewählten Personen an "
                                              "(eine schon vorhandene wird ersetzt)")
        widgets.Button(page_row, text="Feedbackseite entfernen", style="SecondaryAction.TButton",
                       command=self._remove_evaluation_feedback).pack(side=ui.LEFT, padx=(8, 0))

        export_row = widgets.Frame(parent)
        export_row.pack(fill=ui.X, pady=(8, 0))
        self._evaluation_export_format_var = ui.StringVar(value="PNG")
        widgets.Combobox(export_row, textvariable=self._evaluation_export_format_var, state="readonly", width=6,
                         values=tuple(EXPORT_FORMATS)).pack(side=ui.LEFT)
        widgets.Button(export_row, text="Exportieren…", style="SecondaryAction.TButton",
                       command=self._export_evaluation_selection).pack(side=ui.LEFT, padx=(8, 0))
        widgets.Button(export_row, text="Sammelexport…", style="SecondaryAction.TButton",
                       command=self._open_batch_export_from_evaluation).pack(side=ui.LEFT, padx=(8, 0))

    def _select_all_evaluation_rows(self) -> None:
        """Select every person row (never the footers)."""
        treeview_selection.set(self._evaluation_overview_tree, [student.student_id for student in self._current_exam.students])

    def _selection_or_hint(self) -> list[str] | None:
        """The selected person ids, or ``None`` after a hint if nothing is selected."""
        ids = self._evaluation_selected_ids()
        if not ids:
            messagebox.showinfo("Hinweis", "Bitte zuerst Personen in der Übersicht auswählen.")
            return None
        return ids

    def _append_evaluation_feedback(self) -> None:
        """Append (or replace) the feedback page for every selected person - one undo step."""
        ids = self._selection_or_hint()
        if ids is None or self._controller is None:
            return
        updated = self._controller.append_student_result_report_to_pdfs_immediate(
            exam=self._current_exam, student_ids=ids, scores=self._evaluation_scores,
            chart_type=self._evaluation_chart_type_var.get(), chart_scope=self._evaluation_chart_scope_var.get(),
        )
        if updated is not None:
            self._current_exam = updated
        self._refresh_evaluation()

    def _remove_evaluation_feedback(self) -> None:
        """Remove the feedback page of the selected persons that have one; name the skipped ones."""
        ids = self._selection_or_hint()
        if ids is None or self._controller is None:
            return
        has_page = {student.student_id for student in self._current_exam.students if student.stats_report_appended}
        with_page = [student_id for student_id in ids if student_id in has_page]
        skipped = len(ids) - len(with_page)
        if not with_page:
            messagebox.showinfo("Hinweis", "Keine der ausgewählten Personen hat eine Feedbackseite.")
            return
        updated = self._controller.remove_student_result_report_from_pdfs_immediate(exam=self._current_exam, student_ids=with_page)
        if updated is not None:
            self._current_exam = updated
            if skipped:
                self.set_status(f"Feedbackseite von {len(with_page)} PDF(s) entfernt, {skipped} ohne Feedbackseite übersprungen")
        self._refresh_evaluation()

    def _export_evaluation_selection(self) -> None:
        """One report file per selected person into a chosen folder (read-only, no undo)."""
        ids = self._selection_or_hint()
        if ids is None or self._controller is None:
            return
        target_dir = filedialog.askdirectory(title="Zielordner für den Export wählen")
        if not target_dir:
            return
        exported, failed = self._controller.export_student_results(
            exam=self._current_exam, student_ids=ids, scores=self._evaluation_scores,
            chart_type=self._evaluation_chart_type_var.get(), chart_scope=self._evaluation_chart_scope_var.get(),
            output_dir=Path(target_dir), file_extension=EXPORT_FORMATS[self._evaluation_export_format_var.get()],
        )
        if failed:
            messagebox.showwarning("Export teilweise fehlgeschlagen", f"{len(exported)} exportiert, fehlgeschlagen für: {', '.join(failed)}")
        else:
            messagebox.showinfo("Export abgeschlossen", f"{len(exported)} Ergebnis(se) exportiert nach:\n{target_dir}")

    def _open_batch_export_from_evaluation(self) -> None:
        """Close this window and open the batch export with the current selection (no nested modal windows)."""
        ids = self._evaluation_selected_ids()
        self._close_evaluation_popup()
        self._open_batch_export_popup(preselected_ids=ids or None)
