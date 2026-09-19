from __future__ import annotations

from uuid import uuid4

from app.adapters.gui.dialog_services import messagebox
from app.adapters.gui.main_window_types import CorrectionTemplate
from app.core.domain.annotation_sync import build_annotation_clones
from app.core.domain.models import PdfAnnotation

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui, widgets


class MainWindowCorrectionMarkersClipboardMixin:
    def _build_correction_view_form_markers_transform(self) -> None:
        marker_controls = self._correction_marker_controls_frame
        transform_row = widgets.Frame(marker_controls, style="Surface.TFrame")
        transform_row.pack(fill=ui.X, pady=(6, 0))

        shrink_button = widgets.Button(
            transform_row,
            text="A-",
            style="SecondaryAction.TButton",
            width=4,
            command=lambda: self._resize_selected_correction_annotation(-2.0),
        )
        shrink_button.pack(side=ui.LEFT, padx=(0, 4))
        self._attach_hover_help(shrink_button, label="Ausgewaehlte Markierung verkleinern")

        grow_button = widgets.Button(
            transform_row,
            text="A+",
            style="SecondaryAction.TButton",
            width=4,
            command=lambda: self._resize_selected_correction_annotation(2.0),
        )
        grow_button.pack(side=ui.LEFT, padx=(0, 4))
        self._attach_hover_help(grow_button, label="Ausgewaehlte Markierung vergroessern")

        rotate_left_button = widgets.Button(
            transform_row,
            text="↺",
            style="SecondaryAction.TButton",
            width=4,
            command=lambda: self._rotate_selected_correction_annotation(90.0),
        )
        rotate_left_button.pack(side=ui.LEFT, padx=(8, 4))
        self._attach_hover_help(rotate_left_button, label="Ausgewaehlte Markierung nach links drehen")

        rotate_right_button = widgets.Button(
            transform_row,
            text="↻",
            style="SecondaryAction.TButton",
            width=4,
            command=lambda: self._rotate_selected_correction_annotation(-90.0),
        )
        rotate_right_button.pack(side=ui.LEFT, padx=(0, 4))
        self._attach_hover_help(rotate_right_button, label="Ausgewaehlte Markierung nach rechts drehen")

        sync_button = widgets.Button(
            transform_row,
            text="Durchdruecken",
            style="SecondaryAction.TButton",
            command=self._toggle_selected_annotation_sync,
        )
        sync_button.pack(side=ui.LEFT, padx=(12, 0))
        self._attach_hover_help(sync_button, label="Auswahl auf alle Personen spiegeln oder wieder lokal machen")

        widgets.Label(
            marker_controls,
            textvariable=self._correction_marker_info_var,
            style="Muted.TLabel",
        ).pack(anchor=ui.W, pady=(4, 0))
        widgets.Label(
            marker_controls,
            textvariable=self._correction_sync_info_var,
            style="Muted.TLabel",
        ).pack(anchor=ui.W, pady=(2, 0))
        widgets.Label(
            marker_controls,
            text="Zwischenablage: Strg+C kopieren, Strg+X ausschneiden, Strg+V einfuegen",
            style="Muted.TLabel",
        ).pack(anchor=ui.W, pady=(2, 0))

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

    def _sync_group_members(self, annotation: PdfAnnotation, *, include_detached: bool) -> list[PdfAnnotation]:
        if self._current_exam is None or not annotation.sync_group_id:
            return [annotation]

        members = [item for item in self._current_exam.pdf_annotations if item.sync_group_id == annotation.sync_group_id]
        if include_detached:
            return members
        return [item for item in members if not item.position_detached]

    def _delete_annotation_or_group(self, annotation: PdfAnnotation) -> int:
        if self._current_exam is None:
            return 0

        before = len(self._current_exam.pdf_annotations)
        if annotation.sync_group_id:
            self._current_exam.pdf_annotations = [
                item for item in self._current_exam.pdf_annotations if item.sync_group_id != annotation.sync_group_id
            ]
        else:
            self._current_exam.pdf_annotations = [
                item for item in self._current_exam.pdf_annotations if item.annotation_id != annotation.annotation_id
            ]
        removed = before - len(self._current_exam.pdf_annotations)
        if removed > 0:
            self._correction_selected_annotation_id = None
        return removed

    def _refresh_correction_sync_info(self) -> None:
        annotation = self._selected_correction_annotation()
        if annotation is None:
            self._correction_sync_info_var.set("Sync: keine Auswahl")
            return

        if not annotation.sync_group_id:
            self._correction_sync_info_var.set("Sync: lokal")
            return

        members = self._sync_group_members(annotation, include_detached=True)
        detached_suffix = " | Position lokal geloest (Alt-Drag)" if annotation.position_detached else ""
        self._correction_sync_info_var.set(f"Sync: aktiv ({len(members)} Kopien){detached_suffix}")

    def _toggle_selected_annotation_sync(self) -> None:
        annotation = self._selected_correction_annotation()
        if annotation is None:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Markierung auswaehlen.")
            return

        if annotation.sync_group_id:
            removed = self._disable_selected_annotation_sync(annotation)
            if removed <= 0:
                return
            self._render_correction_annotations()
            self._status_var.set("Durchdruecken deaktiviert: Kopien bei anderen Personen entfernt")
            return

        created = self._enable_selected_annotation_sync(annotation)
        if created <= 0:
            return
        self._render_correction_annotations()
        self._status_var.set(f"Durchgedrueckt: {created} Kopien erzeugt")

    def _enable_selected_annotation_sync(self, annotation: PdfAnnotation) -> int:
        """"Durchdruecken": clone the annotation for every other correction student.

        Uses the shared `build_annotation_clones` mechanism (also used by the
        Supersymbol bulk apply) with `self._correction_student_indices` minus
        the already-annotated student as the target set.
        """
        if self._current_exam is None:
            return 0

        template = self._current_correction_template()
        if template is None:
            return 0

        sync_group_id = f"sg-{uuid4().hex[:12]}"
        annotation.sync_group_id = sync_group_id
        annotation.position_detached = False

        other_students = [
            self._current_exam.students[student_index]
            for student_index in self._correction_student_indices
            if self._current_exam.students[student_index].pdf_filename != annotation.student_pdf
        ]
        clones = build_annotation_clones(annotation, other_students, sync_group_id)
        self._current_exam.pdf_annotations.extend(clones)
        return len(clones)

    def _disable_selected_annotation_sync(self, annotation: PdfAnnotation) -> int:
        if self._current_exam is None or not annotation.sync_group_id:
            return 0

        before = len(self._current_exam.pdf_annotations)
        sync_group_id = annotation.sync_group_id
        self._current_exam.pdf_annotations = [
            item
            for item in self._current_exam.pdf_annotations
            if item.sync_group_id != sync_group_id or item.annotation_id == annotation.annotation_id
        ]
        annotation.sync_group_id = ""
        annotation.position_detached = False
        return before - len(self._current_exam.pdf_annotations)

    def _copy_selected_correction_annotation(self) -> bool:
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
        if not self._copy_selected_correction_annotation():
            return False
        annotation = self._selected_correction_annotation()
        if annotation is None:
            return False

        removed = self._delete_annotation_or_group(annotation)
        if removed <= 0:
            return False
        self._render_correction_annotations()
        if annotation.sync_group_id:
            self._status_var.set(f"Sync-Gruppe ausgeschnitten ({removed} Markierungen)")
        else:
            self._status_var.set("Markierung ausgeschnitten")
        return True

    def _paste_correction_annotation(self) -> bool:
        """Paste the clipboard annotation into the currently selected region."""
        if self._current_exam is None:
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
        self._upsert_annotation(annotation)
        self._correction_selected_annotation_id = annotation.annotation_id
        self._render_correction_annotations()
        self._status_var.set("Markierung eingefuegt")
        return True

    def _annotation_by_id(self, annotation_id: str) -> PdfAnnotation | None:
        if self._current_exam is None:
            return None
        return next((item for item in self._current_exam.pdf_annotations if item.annotation_id == annotation_id), None)

    def _upsert_annotation(self, annotation: PdfAnnotation) -> None:
        if self._current_exam is None:
            return
        for index, existing in enumerate(self._current_exam.pdf_annotations):
            if existing.annotation_id == annotation.annotation_id:
                self._current_exam.pdf_annotations[index] = annotation
                return
        self._current_exam.pdf_annotations.append(annotation)

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

    def _delete_selected_correction_annotation(self) -> bool:
        annotation = self._selected_correction_annotation()
        if annotation is None:
            return False
        removed = self._delete_annotation_or_group(annotation)
        if removed <= 0:
            return False
        self._render_correction_annotations()
        if annotation.sync_group_id:
            self._status_var.set(f"Sync-Gruppe geloescht ({removed} Markierungen)")
        else:
            self._status_var.set("Markierung geloescht")
        return True

    def _resize_selected_correction_annotation(self, delta: float) -> None:
        annotation = self._selected_correction_annotation()
        if annotation is None:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Markierung auswaehlen.")
            return
        next_size = max(8.0, min(96.0, float(annotation.font_size) + delta))
        for item in self._sync_group_members(annotation, include_detached=True):
            item.font_size = next_size
        self._render_correction_annotations()
        self._status_var.set(f"Markierungsgroesse: {next_size:.0f}pt")

    def _rotate_selected_correction_annotation(self, delta_deg: float) -> None:
        annotation = self._selected_correction_annotation()
        if annotation is None:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Markierung auswaehlen.")
            return
        current = self._normalize_rotation_deg(annotation.rotation_deg)
        next_rotation = self._normalize_rotation_deg(current + delta_deg)
        for item in self._sync_group_members(annotation, include_detached=True):
            item.rotation_deg = next_rotation
        self._render_correction_annotations()
        self._status_var.set(f"Markierungswinkel: {next_rotation:.0f}°")

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

    def _insert_current_comment_into_preview_center(self) -> None:
        if not self._correction_mode_active:
            return
        comment = self._correction_comment_var.get().strip()
        if not comment:
            messagebox.showinfo("Hinweis", "Bitte zuerst einen Kommentar eintragen.")
            return
        self._save_current_correction_comment()
        if self._correction_canvas is None:
            return
        center_x = float(self._correction_canvas.canvasx(self._correction_canvas.winfo_width() / 2.0))
        center_y = float(self._correction_canvas.canvasy(self._correction_canvas.winfo_height() / 2.0))
        created = self._place_annotation_from_canvas(
            canvas_x=center_x,
            canvas_y=center_y,
            annotation_type="text",
            content=comment,
        )
        if created:
            self._status_var.set("Kommentar in Vorschau-Mitte eingefuegt")

    def _place_annotation_from_canvas(
        self,
        *,
        canvas_x: float,
        canvas_y: float,
        annotation_type: str,
        content: str,
    ) -> bool:
        """Place a new correction mark at the clicked canvas position."""
        if self._current_exam is None:
            return False
        student = self._current_correction_student()
        template = self._current_correction_template()
        if student is None or template is None:
            return False
        pdf_pos = self._canvas_to_pdf_coords(canvas_x, canvas_y)
        if pdf_pos is None:
            return False

        task_code, _max_points = self._selected_correction_task()
        default_font_size = self._default_annotation_font_size
        annotation = PdfAnnotation(
            annotation_id=f"ann-{uuid4().hex[:12]}",
            student_pdf=student.pdf_filename,
            page_number=template.page_number,
            annotation_type=annotation_type,
            content=content,
            color_hex=self._current_marker_color_hex(),
            x=pdf_pos[0],
            y=pdf_pos[1],
            task_code=task_code or "",
            region_id=template.region_id,
            font_size=default_font_size,
            rotation_deg=0.0,
            sync_group_id="",
            position_detached=False,
        )
        self._upsert_annotation(annotation)
        self._correction_selected_annotation_id = annotation.annotation_id
        self._render_correction_annotations()
        return True
