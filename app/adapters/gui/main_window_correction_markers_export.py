from __future__ import annotations

from pathlib import Path

import fitz

from app.adapters.gui.dialog_services import messagebox
from app.adapters.gui.main_window_constants import (
    CORRECTION_EXPORT_SYMBOL_HEIGHT_EM,
    CORRECTION_EXPORT_SYMBOL_ROT90_X_SHIFT_EM,
    CORRECTION_EXPORT_SYMBOL_ROT180_Y_CORRECTION_EM,
    CORRECTION_EXPORT_SYMBOL_Y_SHIFT_EM,
    CORRECTION_EXPORT_TEXT_HEIGHT_EM,
    CORRECTION_EXPORT_TEXT_ROT90_Y_CORRECTION_EM,
    CORRECTION_EXPORT_TEXT_ROT180_Y_CORRECTION_EM,
    CORRECTION_EXPORT_TEXT_ROT_X_SHIFT_FACTOR,
    CORRECTION_EXPORT_TEXT_WIDTH_PADDING_EM,
    CORRECTION_EXPORT_TEXT_Y_SHIFT_EM,
)
from app.core.domain.models import PdfAnnotation
from app.infrastructure.pdf.pdf_document_writer import rewrite_pdf_atomically


class MainWindowCorrectionMarkersExportMixin:
    @classmethod
    def _estimate_annotation_rect(cls, annotation: PdfAnnotation, fontsize: int) -> fitz.Rect:
        fontsize_f = max(8.0, float(fontsize))
        lines = annotation.content.splitlines() or [annotation.content or " "]
        longest_line = max(lines, key=len)
        text_width = fitz.get_text_length(longest_line, fontname="helv", fontsize=fontsize_f)
        rotation_deg = int(cls._normalize_rotation_deg(annotation.rotation_deg))

        width = max(24.0, text_width + (fontsize_f * CORRECTION_EXPORT_TEXT_WIDTH_PADDING_EM))
        center_x = annotation.x
        if annotation.annotation_type == "symbol":
            height = max(12.0, fontsize_f * CORRECTION_EXPORT_SYMBOL_HEIGHT_EM)
            center_y = annotation.y + (fontsize_f * CORRECTION_EXPORT_SYMBOL_Y_SHIFT_EM)
            if rotation_deg == 90:
                center_x += fontsize_f * CORRECTION_EXPORT_SYMBOL_ROT90_X_SHIFT_EM
            elif rotation_deg == 270:
                center_x -= fontsize_f * CORRECTION_EXPORT_SYMBOL_ROT90_X_SHIFT_EM
            elif rotation_deg == 180:
                center_y -= fontsize_f * CORRECTION_EXPORT_SYMBOL_ROT180_Y_CORRECTION_EM
        else:
            line_count = max(1, len(lines))
            height = max(12.0, fontsize_f * CORRECTION_EXPORT_TEXT_HEIGHT_EM * line_count)
            center_y = annotation.y + (fontsize_f * CORRECTION_EXPORT_TEXT_Y_SHIFT_EM)
            if rotation_deg == 90:
                center_x += width * CORRECTION_EXPORT_TEXT_ROT_X_SHIFT_FACTOR
                center_y -= fontsize_f * CORRECTION_EXPORT_TEXT_ROT90_Y_CORRECTION_EM
            elif rotation_deg == 270:
                center_x -= width * CORRECTION_EXPORT_TEXT_ROT_X_SHIFT_FACTOR
                center_y -= fontsize_f * CORRECTION_EXPORT_TEXT_ROT90_Y_CORRECTION_EM
            elif rotation_deg == 180:
                center_y -= fontsize_f * CORRECTION_EXPORT_TEXT_ROT180_Y_CORRECTION_EM
        return fitz.Rect(
            center_x - (width / 2.0),
            center_y - (height / 2.0),
            center_x + (width / 2.0),
            center_y + (height / 2.0),
        )

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
                    page = document.load_page(page_index)
                    existing = list(page.annots() or [])
                    for existing_annot in existing:
                        info = existing_annot.info or {}
                        subject = str(info.get("subject", ""))
                        if subject.startswith("KORREKTOR_MARKER:"):
                            page.delete_annot(existing_annot)

                for annotation in exportable_annotations:
                    if annotation.page_number < 1 or annotation.page_number > document.page_count:
                        continue
                    page = document.load_page(annotation.page_number - 1)
                    fontsize = max(8, int(round(float(annotation.font_size))))
                    rect = self._estimate_annotation_rect(annotation, fontsize)
                    annot = page.add_freetext_annot(
                        rect,
                        annotation.content,
                        fontsize=fontsize,
                        fontname="helv",
                        text_color=self._hex_to_rgb_fraction(annotation.color_hex),
                        rotate=int(self._normalize_rotation_deg(annotation.rotation_deg)),
                        align=1,
                    )
                    annot.set_info(
                        title="Korrektor",
                        subject=f"KORREKTOR_MARKER:{annotation.annotation_id}",
                        content=annotation.content,
                    )
                    annot.update()

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
                "Markierungen ausserhalb des aktiven Vorschau-Bereichs wurden beim PDF-Ueberschreiben ignoriert:\n"
                + preview
                + suffix,
            )
        self._status_var.set("Original-PDF mit Markierungen ueberschrieben")
