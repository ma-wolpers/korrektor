from __future__ import annotations

from pathlib import Path

import fitz

from app.adapters.gui.dialog_services import messagebox
from app.core.domain.mark_labels import mark_label, mark_location_line
from app.core.domain.models import PdfAnnotation
from app.infrastructure.pdf.mark_stamps import add_mark_stamp, remove_marker_stamps
from app.infrastructure.pdf.pdf_document_writer import rewrite_pdf_atomically


class MainWindowCorrectionMarkersExportMixin:
    """"Alle PDFs überschreiben": burn every mark into its student's PDF as an image stamp.

    The stamps are the same images the correction preview shows
    (``app/infrastructure/pdf/mark_stamps.py``); earlier Korrektor marks on a page
    are removed first, so re-running replaces instead of duplicating. Marks outside
    their region are not burnt in; afterwards one question names each of them
    (person, page, sub-task, symbol - `mark_labels.mark_location_line`) and offers to
    delete them in one undo step.

    Punkte-/Prozent-/Noten-Superpositionen are brought to the current points
    first (`refresh_live_contents`, after saving the points field
    still being typed in); one whose value is missing now keeps its last
    text and is named afterwards (`_report_stale_live_marks`).
    """

    _OUTSIDE_PREVIEW_LINES = 12

    def _save_correction_annotations_to_pdfs(self) -> None:
        if self._current_exam is None or self._controller is None:
            return

        self._save_current_correction_score()
        self._save_current_correction_comment()
        self._current_exam, stale_live_marks = self._controller.refresh_live_contents(exam=self._current_exam)

        grouped: dict[str, list[PdfAnnotation]] = {}
        for annotation in self._current_exam.pdf_annotations:
            grouped.setdefault(annotation.student_pdf, []).append(annotation)

        templates = self._build_correction_templates(self._current_exam)

        if not grouped:
            messagebox.showinfo("Hinweis", "Keine Markierungen zum Speichern vorhanden.")
            return

        failures: list[str] = []
        skipped_annotations: list[PdfAnnotation] = []
        for student_pdf, annotations in grouped.items():
            pdf_path = Path(self._current_exam.folder_path) / student_pdf
            if not pdf_path.exists():
                failures.append(f"Datei fehlt: {student_pdf}")
                continue

            exportable_annotations: list[PdfAnnotation] = []
            for annotation in annotations:
                clip_box = self._resolve_annotation_clip_box(annotation, templates)
                if clip_box is None or not self._point_in_box(annotation.x, annotation.y, clip_box):
                    skipped_annotations.append(annotation)
                    continue
                exportable_annotations.append(annotation)

            cached_document = self._doc_cache.pop(student_pdf, None)
            if cached_document is not None:
                try:
                    cached_document.close()
                except Exception:
                    pass

            def _mutate(document: fitz.Document) -> None:
                for page_index in range(document.page_count):
                    remove_marker_stamps(document.load_page(page_index))
                for annotation in exportable_annotations:
                    if annotation.page_number < 1 or annotation.page_number > document.page_count:
                        continue
                    add_mark_stamp(document.load_page(annotation.page_number - 1), annotation)

            try:
                rewrite_pdf_atomically(pdf_path, _mutate)
            except Exception as exc:
                failures.append(f"{student_pdf}: {exc}")

        if failures:
            messagebox.showerror("PDF-Speichern fehlgeschlagen", "\n".join(failures))
            return

        self._apply_detail_labels(self._current_exam)
        self._render_correction_preview()
        self._status_var.set("Original-PDF mit Markierungen überschrieben")
        if stale_live_marks:
            self._report_stale_live_marks(stale_live_marks)
        if skipped_annotations:
            self._offer_to_delete_outside_marks(skipped_annotations)

    def _report_stale_live_marks(self, stale: list[tuple[PdfAnnotation, str]]) -> None:
        """Name every Superposition mark that kept its last text because its value is missing now, and why."""
        names = {student.pdf_filename: student.display_name for student in self._current_exam.students}
        lines = [
            f"• {names.get(item.student_pdf, item.student_pdf)}, S. {item.page_number}: {mark_label(item)} – {problem}"
            for item, problem in stale
        ]
        shown = lines[: self._OUTSIDE_PREVIEW_LINES]
        if len(lines) > len(shown):
            shown.append(f"… und {len(lines) - len(shown)} weitere")
        messagebox.showwarning(
            "Exporthinweis",
            "Diese eingefügten Werte ließen sich nicht neu berechnen und stehen mit dem zuletzt bekannten Wert in der PDF:\n\n"
            + "\n".join(shown),
        )

    def _offer_to_delete_outside_marks(self, annotations: list[PdfAnnotation]) -> None:
        """Name every mark that was not burnt in (person, page, sub-task, symbol) and ask to delete them.

        "Ja" deletes exactly these marks in one undo step (`delete_annotations_immediate`);
        "Nein" keeps them - they stay in the exam and in the preview, just not in the PDF.
        """
        names = {student.pdf_filename: student.display_name for student in self._current_exam.students}
        lines = [f"• {mark_location_line(item, names.get(item.student_pdf, item.student_pdf))}" for item in annotations]
        shown = lines[: self._OUTSIDE_PREVIEW_LINES]
        if len(lines) > len(shown):
            shown.append(f"… und {len(lines) - len(shown)} weitere")
        count = len(annotations)
        subject = "Diese Markierung liegt" if count == 1 else f"Diese {count} Markierungen liegen"
        question = "Markierung löschen?" if count == 1 else f"Alle {count} löschen?"
        if not messagebox.askyesno(
            "Exporthinweis",
            f"{subject} außerhalb ihres Bereichs und wurde{'' if count == 1 else 'n'} nicht in die PDF übernommen:\n\n"
            + "\n".join(shown)
            + f"\n\n{question} (Rückgängig mit Strg+Z)",
        ):
            return
        updated = self._controller.delete_annotations_immediate(
            exam=self._current_exam, annotation_ids=[item.annotation_id for item in annotations]
        )
        if updated is None:
            return
        self._current_exam = updated
        self._render_correction_preview()
        self._status_var.set("Original-PDF überschrieben, Markierungen außerhalb gelöscht")
