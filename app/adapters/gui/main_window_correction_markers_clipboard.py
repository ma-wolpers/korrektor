from __future__ import annotations

from uuid import uuid4

from app.adapters.gui.dialog_services import messagebox
from app.adapters.gui.main_window_types import CorrectionTemplate
from app.core.domain.models import PdfAnnotation

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui


class MainWindowCorrectionMarkersClipboardMixin:
    def _current_correction_annotations(self) -> list[PdfAnnotation]:
        """List annotations for the current student/page, filtered by region_id."""
        if self._current_exam is None:
            return []
        student = self._current_correction_student()
        template = self._current_correction_template()
        if student is None or template is None:
            return []
        return [
            item
            for item in self._current_exam.pdf_annotations
            if item.student_pdf == student.pdf_filename and item.page_number == template.page_number
            and (not item.region_id or item.region_id == template.region_id)
        ]

    def _selected_correction_annotation(self) -> PdfAnnotation | None:
        if self._correction_selected_annotation_id is None:
            return None
        annotation = self._annotation_by_id(self._correction_selected_annotation_id)
        if annotation is None:
            return None

        visible_ids = {item.annotation_id for item in self._current_correction_annotations()}
        if annotation.annotation_id not in visible_ids:
            return None
        return annotation

    def _copy_selected_correction_annotation(self) -> bool:
        """Copy the selected annotation's style/content to the local clipboard - pure UI state, no exam mutation.

        Deliberately does not touch `self._current_exam` or the undo
        history (Meilenstein 0.3): copying changes nothing about the exam,
        only `self._annotation_clipboard`.
        """
        annotation = self._selected_correction_annotation()
        if annotation is None:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Markierung auswaehlen.")
            return False

        clip_box = self._resolve_annotation_clip_box(annotation, self._correction_templates)
        if clip_box is None:
            messagebox.showinfo("Hinweis", "Die Markierung liegt ausserhalb eines gueltigen Bereichs.")
            return False

        width = max(1e-6, clip_box[2] - clip_box[0])
        height = max(1e-6, clip_box[3] - clip_box[1])
        rel_x = (annotation.x - clip_box[0]) / width
        rel_y = (annotation.y - clip_box[1]) / height

        self._annotation_clipboard = {
            "annotation_type": annotation.annotation_type,
            "content": annotation.content,
            "color_hex": self._normalize_marker_color_hex(annotation.color_hex),
            "font_size": self._normalize_marker_font_size(annotation.font_size),
            "rotation_deg": self._normalize_rotation_deg(annotation.rotation_deg),
            "task_code": annotation.task_code,
            "rel_x": rel_x,
            "rel_y": rel_y,
        }
        self._status_var.set("Markierung kopiert")
        return True

    def _cut_selected_correction_annotation(self) -> bool:
        """Copy (clipboard-only) then delete the selection - the deletion is the one Exam-mutating step.

        Copying itself never becomes a `HistoryAction` (see
        `_copy_selected_correction_annotation`); only the delete that
        follows (`MainWindowCorrectionMarkersTransformMixin._delete_selected_correction_annotation`)
        persists and pushes one.
        """
        if not self._copy_selected_correction_annotation():
            return False
        return self._delete_selected_correction_annotation()

    def _paste_correction_annotation(self) -> bool:
        """Paste the clipboard annotation into the currently selected region and persist immediately."""
        if self._current_exam is None or self._controller is None:
            return False
        if not self._annotation_clipboard:
            messagebox.showinfo("Hinweis", "Zwischenablage ist leer.")
            return False

        student = self._current_correction_student()
        template = self._current_correction_template()
        if student is None or template is None:
            return False

        rel_x = float(self._annotation_clipboard.get("rel_x", 0.5))
        rel_y = float(self._annotation_clipboard.get("rel_y", 0.5))
        x0, y0, x1, y1 = template.box
        target_x = x0 + rel_x * (x1 - x0)
        target_y = y0 + rel_y * (y1 - y0)

        annotation = PdfAnnotation(
            annotation_id=f"ann-{uuid4().hex[:12]}",
            student_pdf=student.pdf_filename,
            page_number=template.page_number,
            annotation_type=str(self._annotation_clipboard.get("annotation_type", "symbol")),
            content=str(self._annotation_clipboard.get("content", "")).strip(),
            color_hex=self._normalize_marker_color_hex(self._annotation_clipboard.get("color_hex")),
            x=target_x,
            y=target_y,
            task_code=str(self._annotation_clipboard.get("task_code", "")).strip().upper(),
            region_id=template.region_id,
            font_size=self._normalize_marker_font_size(self._annotation_clipboard.get("font_size", 14.0)),
            rotation_deg=self._normalize_rotation_deg(float(self._annotation_clipboard.get("rotation_deg", 0.0))),
            sync_group_id="",
            position_detached=False,
        )
        updated = self._controller.place_annotation_immediate(exam=self._current_exam, annotation=annotation)
        if updated is None:
            return False
        self._current_exam = updated
        self._correction_selected_annotation_id = annotation.annotation_id
        self._render_correction_annotations()
        self._status_var.set("Markierung eingefuegt")
        return True

    def _annotation_by_id(self, annotation_id: str) -> PdfAnnotation | None:
        if self._current_exam is None:
            return None
        return next((item for item in self._current_exam.pdf_annotations if item.annotation_id == annotation_id), None)

    @staticmethod
    def _point_in_box(x: float, y: float, box: tuple[float, float, float, float]) -> bool:
        x0, y0, x1, y1 = box
        return x0 <= x <= x1 and y0 <= y <= y1

    def _resolve_annotation_clip_box(
        self,
        annotation: PdfAnnotation,
        templates: dict[str, CorrectionTemplate],
    ) -> tuple[float, float, float, float] | None:
        """Find the region box an annotation belongs to, by region_id or position."""
        if annotation.region_id:
            template = templates.get(annotation.region_id)
            if template is None or template.page_number != annotation.page_number:
                return None
            return template.box

        for template in templates.values():
            if template.page_number != annotation.page_number:
                continue
            if self._point_in_box(annotation.x, annotation.y, template.box):
                return template.box
        return None

    def _render_correction_annotations(self) -> None:
        if self._correction_canvas is None:
            return
        self._correction_canvas.delete("correction_annotation")
        self._correction_annotation_items.clear()
        annotations = self._current_correction_annotations()
        visible_ids = {item.annotation_id for item in annotations}
        if self._correction_selected_annotation_id not in visible_ids:
            self._correction_selected_annotation_id = None
        if not annotations:
            self._refresh_correction_sync_info()
            return

        for annotation in annotations:
            canvas_pos = self._pdf_to_canvas_coords(annotation.x, annotation.y)
            if canvas_pos is None:
                continue
            canvas_x, canvas_y = canvas_pos
            font_size = max(8, int(round(float(annotation.font_size) * self._correction_scale)))
            item_id = self._correction_canvas.create_text(
                canvas_x,
                canvas_y,
                text=annotation.content,
                fill=annotation.color_hex,
                font=("Segoe UI", font_size, "bold"),
                anchor=ui.CENTER,
                angle=self._normalize_rotation_deg(annotation.rotation_deg),
                tags=("correction_annotation", f"annotation:{annotation.annotation_id}"),
            )
            self._correction_annotation_items[annotation.annotation_id] = item_id
            if annotation.annotation_id == self._correction_selected_annotation_id:
                bbox = self._correction_canvas.bbox(item_id)
                if bbox is not None:
                    self._correction_canvas.create_rectangle(
                        bbox[0] - 4,
                        bbox[1] - 2,
                        bbox[2] + 4,
                        bbox[3] + 2,
                        outline="#f4a261",
                        width=2,
                        tags=("correction_annotation",),
                    )
                    self._correction_canvas.tag_raise(item_id)
                self._refresh_correction_sync_info()
