from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from app.adapters.gui.dialog_services import messagebox
from app.core.domain.models import ExamProject, StudentExam
from app.infrastructure.pdf.pdf_document_writer import (
    append_marked_stats_page,
    read_trailing_page_bytes,
    read_trailing_page_marker,
    remove_trailing_page,
)
from app.infrastructure.rendering.competency_chart_renderer import figure_to_pdf_bytes
from app.infrastructure.rendering.student_result_report_renderer import render_student_result_report


class UiIntentControllerStudentResultPdfExportMixin:
    """Statistikseite an die echte Klausur-PDF anhängen/entfernen: ein Exam-Mutator mit Datei-Nebenwirkung.

    Separat von `ui_intent_controller_student_result.py` (dessen Docstring
    "kein Exam-Mutator, keine HistoryAction" festhält) - diese Methoden
    sind beides. Physische Identität geht vor persistiertem Flag: jede von
    `append_marked_stats_page` erzeugte Seite trägt eine
    `KORREKTOR_STATS_PAGE`-Markierung; vor jeder Mutation wird
    `read_trailing_page_marker` gegen `StudentExam.stats_report_appended`
    geprüft - bei Widerspruch wird **nichts** mutiert (weder Datei noch
    JSON), sondern mit personenbezogener Diagnose abgelehnt. Undo/Redo
    verwenden ausschließlich die zum Zeitpunkt der Aktion tatsächlich
    gelesenen/geschriebenen Seiten-Bytes (nie eine Neuberechnung) - Redo
    stellt exakt die damals erzeugte Seite wieder her, auch wenn sich der
    `StudentResult` der Person inzwischen geändert hat. Folgt dem
    Batch-Muster von `set_persons_area_finished_immediate`/
    `rename_students_immediate`: ein `HistoryAction` pro Aufruf,
    Alles-oder-nichts-Vorprüfung vor jeder Mutation, vollständiges
    Rollback bei einem Fehler mitten im Batch.
    """

    @staticmethod
    def _resolve_student_pdf_paths_or_none(
        *, exam: ExamProject, student_ids: Sequence[str]
    ) -> list[tuple[StudentExam, Path]] | None:
        """Resolve each student_id to its `(StudentExam, pdf_path)`, or show a diagnostic and return `None`.

        Rejects the whole batch if any id is unknown or its PDF file is
        missing - shared first pass for both append and remove, mirroring
        `UiIntentControllerSuperpositionMixin._resolve_superposition_targets_or_none`.
        """
        students_by_id = {student.student_id: student for student in exam.students}
        resolved: list[tuple[StudentExam, Path]] = []
        for student_id in student_ids:
            student = students_by_id.get(student_id)
            if student is None:
                messagebox.showerror("Unbekannte Person", f"Unbekannte Person-ID: {student_id}")
                return None
            pdf_path = Path(exam.folder_path) / student.pdf_filename
            if not pdf_path.exists():
                messagebox.showerror("Statistikseite nicht möglich", f"Datei fehlt: {student.pdf_filename}")
                return None
            resolved.append((student, pdf_path))
        return resolved

    @staticmethod
    def _check_marker_consistency_or_none(resolved: list[tuple[StudentExam, Path]]) -> str | None:
        """Verify the physical marker on each PDF agrees with `stats_report_appended`, or return a diagnostic.

        Never trusts the JSON flag alone (see class docstring) - checked
        for every target before any mutation happens, so an inconsistency
        anywhere aborts the whole batch untouched.
        """
        for student, pdf_path in resolved:
            has_marker = read_trailing_page_marker(pdf_path) is not None
            if student.stats_report_appended and not has_marker:
                return (
                    f"{student.display_name}: laut Klausurdaten ist eine Statistikseite angehängt, "
                    "die letzte PDF-Seite trägt aber keine Korrektor-Markierung - die Datei wurde "
                    "vermutlich extern verändert. Keine Änderung durchgeführt."
                )
            if not student.stats_report_appended and has_marker:
                return (
                    f"{student.display_name}: die letzte PDF-Seite trägt bereits eine Korrektor-"
                    "Statistikseiten-Markierung, laut Klausurdaten ist aber keine angehängt - "
                    "widersprüchlicher Zustand. Keine Änderung durchgeführt."
                )
        return None

    def append_student_result_report_to_pdfs_immediate(
        self,
        *,
        exam: ExamProject,
        student_ids: Sequence[str],
        scores: dict[str, dict[str, float]],
        chart_type: str,
        chart_scope: str,
    ) -> ExamProject | None:
        """Render each student's Auswertungs-Report and append/replace it as their PDF's last page.

        Overwrites a previously appended report (same page count
        afterwards) rather than accumulating pages. Unvollständigkeit des
        `StudentResult` ist kein Ablehnungsgrund - der Renderer zeigt
        fehlende Werte bereits als "-", identisch zum bestehenden
        Datei-Export.
        """
        target_ids = list(dict.fromkeys(student_ids))
        if not target_ids:
            messagebox.showerror("Ungültige Eingabe", "Keine Personen ausgewählt.")
            return None

        resolved = self._resolve_student_pdf_paths_or_none(exam=exam, student_ids=target_ids)
        if resolved is None:
            return None
        inconsistency = self._check_marker_consistency_or_none(resolved)
        if inconsistency is not None:
            messagebox.showerror("Statistikseite nicht möglich", inconsistency)
            return None

        applied: list[tuple[StudentExam, bytes | None, bytes]] = []

        def _rollback_applied() -> None:
            """Undo every append/replace already performed in this batch call, in reverse order."""
            for prev_student, prev_before_bytes, _prev_after_bytes in reversed(applied):
                prev_path = Path(exam.folder_path) / prev_student.pdf_filename
                if prev_before_bytes is None:
                    remove_trailing_page(prev_path)
                else:
                    append_marked_stats_page(prev_path, prev_before_bytes, replace_existing=True)

        for student, pdf_path in resolved:
            result = self.compute_student_result_for_exam(exam=exam, student_id=student.student_id, scores=scores)
            if result is None:
                _rollback_applied()
                messagebox.showerror("Statistikseite nicht möglich", f"{student.display_name}: Auswertung nicht verfügbar.")
                return None

            had_previous = student.stats_report_appended
            before_bytes = read_trailing_page_bytes(pdf_path) if had_previous else None
            new_page_bytes = figure_to_pdf_bytes(render_student_result_report(result, chart_type=chart_type, chart_scope=chart_scope))

            self._app.invalidate_doc_cache([student.pdf_filename])
            try:
                append_marked_stats_page(pdf_path, new_page_bytes, replace_existing=had_previous)
                after_bytes = read_trailing_page_bytes(pdf_path)
            except Exception as exc:
                _rollback_applied()
                messagebox.showerror("Statistikseite nicht möglich", f"{student.display_name}: {exc}")
                return None
            applied.append((student, before_bytes, after_bytes))

        before_payload = exam.to_dict()
        for student, _before_bytes, _after_bytes in applied:
            student.stats_report_appended = True

        exam_file = self._save_exam_guarded(exam)
        if exam_file is None:
            _rollback_applied()
            return None
        updated = self._deps.exam_repository.load_exam(exam_file)
        after_payload = updated.to_dict()

        pdf_filenames = [student.pdf_filename for student, _b, _a in applied]
        # (pdf_filename, before_bytes, after_bytes, replace_existing_on_redo) - `replace_existing`
        # for redo is fixed here (the state *before* this action, i.e. whether a page already
        # existed when it originally ran), not re-derived from anything that could later change.
        entries = [
            (student.pdf_filename, before_bytes, after_bytes, before_bytes is not None)
            for student, before_bytes, after_bytes in applied
        ]

        def _undo() -> None:
            self._app.invalidate_doc_cache(pdf_filenames)
            for pdf_filename, before_bytes, _after_bytes, _replace_on_redo in entries:
                pdf_path = Path(exam.folder_path) / pdf_filename
                if before_bytes is None:
                    remove_trailing_page(pdf_path)
                else:
                    append_marked_stats_page(pdf_path, before_bytes, replace_existing=True)
            self._write_exam_payload(exam_file, before_payload)

        def _redo() -> None:
            self._app.invalidate_doc_cache(pdf_filenames)
            for pdf_filename, _before_bytes, after_bytes, replace_on_redo in entries:
                pdf_path = Path(exam.folder_path) / pdf_filename
                append_marked_stats_page(pdf_path, after_bytes, replace_existing=replace_on_redo)
            self._write_exam_payload(exam_file, after_payload)

        description = (
            f"Statistikseite angehängt: {applied[0][0].display_name}"
            if len(applied) == 1
            else f"Statistikseite an {len(applied)} PDFs angehängt"
        )
        self._record_history_action(description=description, undo=_undo, redo=_redo)
        self._app.set_status(description)
        return updated

    def remove_student_result_report_from_pdfs_immediate(
        self, *, exam: ExamProject, student_ids: Sequence[str]
    ) -> ExamProject | None:
        """Remove the appended Statistikseite from each selected student's PDF.

        All-or-nothing: every selected student must currently have a
        consistent (flag+marker) appended Statistikseite, or the whole
        batch is rejected with a diagnostic naming the first offending
        person - matching `apply_scored_superposition_immediate`'s
        validate-then-execute contract.
        """
        target_ids = list(dict.fromkeys(student_ids))
        if not target_ids:
            messagebox.showerror("Ungültige Eingabe", "Keine Personen ausgewählt.")
            return None

        resolved = self._resolve_student_pdf_paths_or_none(exam=exam, student_ids=target_ids)
        if resolved is None:
            return None
        inconsistency = self._check_marker_consistency_or_none(resolved)
        if inconsistency is not None:
            messagebox.showerror("Statistikseite nicht möglich", inconsistency)
            return None
        missing = [student.display_name for student, _p in resolved if not student.stats_report_appended]
        if missing:
            messagebox.showerror(
                "Statistikseite nicht möglich",
                "Keine Statistikseite vorhanden für: " + ", ".join(missing),
            )
            return None

        applied: list[tuple[StudentExam, bytes]] = []

        def _rollback_applied() -> None:
            """Re-append every page already removed in this batch call, in reverse order."""
            for prev_student, prev_bytes in reversed(applied):
                prev_path = Path(exam.folder_path) / prev_student.pdf_filename
                append_marked_stats_page(prev_path, prev_bytes, replace_existing=False)

        for student, pdf_path in resolved:
            before_bytes = read_trailing_page_bytes(pdf_path)
            if before_bytes is None:
                _rollback_applied()
                messagebox.showerror("Statistikseite nicht möglich", f"{student.display_name}: PDF ist leer.")
                return None
            self._app.invalidate_doc_cache([student.pdf_filename])
            try:
                remove_trailing_page(pdf_path)
            except Exception as exc:
                _rollback_applied()
                messagebox.showerror("Statistikseite nicht möglich", f"{student.display_name}: {exc}")
                return None
            applied.append((student, before_bytes))

        before_payload = exam.to_dict()
        for student, _bytes in applied:
            student.stats_report_appended = False

        exam_file = self._save_exam_guarded(exam)
        if exam_file is None:
            _rollback_applied()
            return None
        updated = self._deps.exam_repository.load_exam(exam_file)
        after_payload = updated.to_dict()

        pdf_filenames = [student.pdf_filename for student, _b in applied]
        removed_entries = [(student.pdf_filename, before_bytes) for student, before_bytes in applied]

        def _undo() -> None:
            self._app.invalidate_doc_cache(pdf_filenames)
            for pdf_filename, page_bytes in removed_entries:
                pdf_path = Path(exam.folder_path) / pdf_filename
                append_marked_stats_page(pdf_path, page_bytes, replace_existing=False)
            self._write_exam_payload(exam_file, before_payload)

        def _redo() -> None:
            self._app.invalidate_doc_cache(pdf_filenames)
            for pdf_filename, _page_bytes in removed_entries:
                pdf_path = Path(exam.folder_path) / pdf_filename
                remove_trailing_page(pdf_path)
            self._write_exam_payload(exam_file, after_payload)

        description = (
            f"Statistikseite entfernt: {applied[0][0].display_name}"
            if len(applied) == 1
            else f"Statistikseite aus {len(applied)} PDFs entfernt"
        )
        self._record_history_action(description=description, undo=_undo, redo=_redo)
        self._app.set_status(description)
        return updated
