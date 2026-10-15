from __future__ import annotations

from pathlib import Path

import fitz

from app.adapters.gui.dialog_services import messagebox
from app.core.domain.models import PdfAnnotation
from app.infrastructure.pdf.mark_stamps import add_mark_stamp, remove_marker_stamps
from app.infrastructure.pdf.pdf_document_writer import rewrite_pdf_atomically


class MainWindowCorrectionMarkersExportMixin:
    """"Alle PDFs überschreiben": burn every mark into its student's PDF as an image stamp.

    The stamps are the same images the correction preview shows
    (``app/infrastructure/pdf/mark_stamps.py``); earlier Korrektor marks on a page
    are removed first, so re-running replaces instead of duplicating.
    """

    def _save_correction_annotations_to_pdfs(self) -> None:
        if self._current_exam is None or self._controller is None:
            return

        self._save_current_correction_comment()

        grouped: dict[str, list[PdfAnnotation]] = {}
        for annotation in self._current_exam.pdf_annotations:
            grouped.setdefault(annotation.student_pdf, []).append(annotation)

        templates = self._build_correction_templates(self._current_exam)

        if not grouped:
            messagebox.showinfo("Hinweis", "Keine Markierungen zum Speichern vorhanden.")
            return

        failures: list[str] = []
        skipped_annotations: list[str] = []
        for student_pdf, annotations in grouped.items():
            pdf_path = Path(self._current_exam.folder_path) / student_pdf
            if not pdf_path.exists():
                failures.append(f"Datei fehlt: {student_pdf}")
                continue

            exportable_annotations: list[PdfAnnotation] = []
            for annotation in annotations:
                clip_box = self._resolve_annotation_clip_box(annotation, templates)
                if clip_box is None or not self._point_in_box(annotation.x, annotation.y, clip_box):
                    skipped_annotations.append(
                        f"{student_pdf} S{annotation.page_number}: {annotation.content} ({annotation.annotation_id})"
                    )
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
        if skipped_annotations:
            preview = "\n".join(skipped_annotations[:8])
            remaining = len(skipped_annotations) - 8
            suffix = f"\n... und {remaining} weitere" if remaining > 0 else ""
            messagebox.showwarning(
                "Exporthinweis",
                "Markierungen außerhalb des aktiven Vorschau-Bereichs wurden beim PDF-Überschreiben ignoriert:\n"
                + preview
                + suffix,
            )
        self._status_var.set("Original-PDF mit Markierungen überschrieben")
