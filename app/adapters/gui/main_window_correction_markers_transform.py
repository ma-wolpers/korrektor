from __future__ import annotations

from uuid import uuid4

from app.adapters.gui.dialog_services import messagebox
from app.core.domain.models import PdfAnnotation

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui, widgets


class MainWindowCorrectionMarkersTransformMixin:
    """Groesse/Rotation/Loeschen/Platzieren einzelner Korrektur-Annotationen.

    Ausgelagert aus `main_window_correction_markers_clipboard.py`
    (Meilenstein 0.3 der Korrektor-Wunschliste), das mit 343 Zeilen
    ausfuehrbarem Code ueber der projektweiten ~300-Zeilen-Konvention lag
    (siehe `docs/ARCHITEKTUR.md` "Datei-Organisation"). Jede Mutation hier
    persistiert sofort ueber die passende `UiIntentControllerAnnotationsMixin`-
    Methode statt nur `self._current_exam` in-memory zu aendern.
    """

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

        detach_button = widgets.Button(
            transform_row,
            text="Entkoppeln",
            style="SecondaryAction.TButton",
            command=self._detach_selected_annotation_from_sync,
        )
        detach_button.pack(side=ui.LEFT, padx=(8, 0))
        self._attach_hover_help(
            detach_button,
            label="Nur dieses Symbol aus der Sync-Gruppe loesen - bei allen anderen Personen bleibt es gesynct",
        )

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

    def _delete_selected_correction_annotation(self) -> bool:
        if self._current_exam is None or self._controller is None:
            return False
        annotation = self._selected_correction_annotation()
        if annotation is None:
            return False
        is_group = bool(annotation.sync_group_id)
        updated = self._controller.delete_annotation_immediate(
            exam=self._current_exam, annotation_id=annotation.annotation_id
        )
        if updated is None:
            return False
        self._current_exam = updated
        self._render_correction_annotations()
        if is_group:
            self._status_var.set("Sync-Gruppe geloescht")
        else:
            self._status_var.set("Markierung geloescht")
        return True

    def _resize_selected_correction_annotation(self, delta: float) -> None:
        if self._current_exam is None or self._controller is None:
            return
        annotation = self._selected_correction_annotation()
        if annotation is None:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Markierung auswaehlen.")
            return
        updated = self._controller.resize_annotation_immediate(
            exam=self._current_exam, annotation_id=annotation.annotation_id, delta=delta
        )
        if updated is None:
            return
        self._current_exam = updated
        self._render_correction_annotations()
        self._status_var.set("Markierungsgroesse aktualisiert")

    def _rotate_selected_correction_annotation(self, delta_deg: float) -> None:
        if self._current_exam is None or self._controller is None:
            return
        annotation = self._selected_correction_annotation()
        if annotation is None:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Markierung auswaehlen.")
            return
        current = self._normalize_rotation_deg(annotation.rotation_deg)
        next_rotation = self._normalize_rotation_deg(current + delta_deg)
        updated = self._controller.rotate_annotation_immediate(
            exam=self._current_exam, annotation_id=annotation.annotation_id, next_rotation_deg=next_rotation
        )
        if updated is None:
            return
        self._current_exam = updated
        self._render_correction_annotations()
        self._status_var.set(f"Markierungswinkel: {next_rotation:.0f}°")

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
        """Place a new correction mark at the clicked canvas position and persist it immediately."""
        if self._current_exam is None or self._controller is None:
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
        updated = self._controller.place_annotation_immediate(exam=self._current_exam, annotation=annotation)
        if updated is None:
            return False
        self._current_exam = updated
        self._correction_selected_annotation_id = annotation.annotation_id
        self._render_correction_annotations()
        return True
