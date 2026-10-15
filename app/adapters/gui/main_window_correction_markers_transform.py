from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

from app.adapters.gui.dialog_services import messagebox
from app.core.domain.annotation_move import clamp_into_box
from app.core.domain.mark_transform import Orientation, flipped_horizontally, flipped_vertically, rotated
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
        self._attach_hover_help(shrink_button, label="Ausgewählte Markierung verkleinern")

        grow_button = widgets.Button(
            transform_row,
            text="A+",
            style="SecondaryAction.TButton",
            width=4,
            command=lambda: self._resize_selected_correction_annotation(2.0),
        )
        grow_button.pack(side=ui.LEFT, padx=(0, 4))
        self._attach_hover_help(grow_button, label="Ausgewählte Markierung vergrößern")

        for text, label, change, mirrors, padx in (
            ("↺", "Ausgewählte Markierung um 45° nach links drehen", lambda o: rotated(o, 45.0), False, (8, 4)),
            ("↻", "Ausgewählte Markierung um 45° nach rechts drehen", lambda o: rotated(o, -45.0), False, (0, 4)),
            ("↔", "Ausgewähltes Symbol horizontal spiegeln (links/rechts tauschen)", flipped_horizontally, True, (8, 4)),
            ("↕", "Ausgewähltes Symbol vertikal spiegeln (oben/unten tauschen)", flipped_vertically, True, (0, 4)),
        ):
            button = widgets.Button(
                transform_row,
                text=text,
                style="SecondaryAction.TButton",
                width=4,
                command=lambda change=change, mirrors=mirrors: self._reorient_selected_correction_annotation(
                    change, mirrors=mirrors
                ),
            )
            button.pack(side=ui.LEFT, padx=padx)
            self._attach_hover_help(button, label=label)

        sync_row = widgets.Frame(marker_controls, style="Surface.TFrame")
        sync_row.pack(fill=ui.X, pady=(4, 0))
        sync_button = widgets.Button(
            sync_row,
            text="Durchdrücken",
            style="SecondaryAction.TButton",
            command=self._toggle_selected_annotation_sync,
        )
        sync_button.pack(side=ui.LEFT)
        self._attach_hover_help(sync_button, label="Auswahl auf alle Personen spiegeln oder wieder lokal machen")

        detach_button = widgets.Button(
            sync_row,
            text="Entkoppeln",
            style="SecondaryAction.TButton",
            command=self._detach_selected_annotation_from_sync,
        )
        detach_button.pack(side=ui.LEFT, padx=(8, 0))
        self._attach_hover_help(
            detach_button,
            label="Nur dieses Symbol aus der Sync-Gruppe lösen - bei allen anderen Personen bleibt es gesynct",
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
            text="Zwischenablage: Strg+C kopieren, Strg+X ausschneiden, Strg+V einfügen",
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
            self._status_var.set("Sync-Gruppe gelöscht")
        else:
            self._status_var.set("Markierung gelöscht")
        return True

    def _resize_selected_correction_annotation(self, delta: float) -> None:
        if self._current_exam is None or self._controller is None:
            return
        annotation = self._selected_correction_annotation()
        if annotation is None:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Markierung auswählen.")
            return
        updated = self._controller.resize_annotation_immediate(
            exam=self._current_exam, annotation_id=annotation.annotation_id, delta=delta
        )
        if updated is None:
            return
        self._current_exam = updated
        self._render_correction_annotations()
        self._status_var.set("Markierungsgröße aktualisiert")

    def _reorient_selected_correction_annotation(
        self, change: Callable[[Orientation], Orientation], *, mirrors: bool
    ) -> None:
        """Rotate or mirror the selected mark (and its sync group) through `mark_transform`.

        Args:
            change: Maps the current orientation to the new one (``rotated``,
                ``flipped_horizontally``, ``flipped_vertically``).
            mirrors: ``True`` for the mirror buttons - refused for comments, which
                would turn into mirror writing.
        """
        if self._current_exam is None or self._controller is None:
            return
        annotation = self._selected_correction_annotation()
        if annotation is None:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Markierung auswählen.")
            return
        if mirrors and annotation.annotation_type == "text":
            messagebox.showinfo("Hinweis", "Kommentare lassen sich nicht spiegeln (das wäre Spiegelschrift).")
            return
        target = change(Orientation.of(annotation.rotation_deg, annotation.mirrored))
        updated = self._controller.set_annotation_orientation_immediate(
            exam=self._current_exam,
            annotation_id=annotation.annotation_id,
            rotation_deg=target.rotation_deg,
            mirrored=target.mirrored,
        )
        if updated is None:
            return
        self._current_exam = updated
        self._render_correction_annotations()
        mirror_text = ", gespiegelt" if target.mirrored else ""
        self._status_var.set(f"Markierungswinkel: {target.rotation_deg:.0f}°{mirror_text}")

    def _insert_current_comment_into_preview_center(self) -> None:
        """Place the typed comment as a text mark at the preview centre, or in the nearest crop.

        If the centre is on a header, a gap or beside the image, the comment
        goes to the nearest point of the nearest crop (`_nearest_segment_point`)
        instead of being silently dropped; without any crop (the person has
        no region for this task) a hint says so.
        """
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
        point = self._nearest_segment_point(center_x, center_y)
        if point is None:
            messagebox.showinfo("Hinweis", "Kommentar nicht eingefügt: Hier ist kein Ausschnitt, in den er gesetzt werden kann.")
            return
        # A failed save is already reported by the controller.
        if self._place_annotation_from_canvas(canvas_x=point[0], canvas_y=point[1], annotation_type="text", content=comment):
            self._status_var.set("Kommentar eingefügt")

    def _place_annotation_from_canvas(
        self,
        *,
        canvas_x: float,
        canvas_y: float,
        annotation_type: str,
        content: str,
    ) -> bool:
        """Place a new correction mark at the clicked canvas position and persist it immediately.

        The point is clamped into the segment's crop (`clamp_into_box`): a
        click beside a narrow image (same height, but right of it) would
        otherwise create a mark outside its region - drawn on no crop and
        skipped by the PDF export (see `app.core.domain.annotation_move`).
        """
        if self._current_exam is None or self._controller is None:
            return False
        student = self._current_correction_student()
        segment = self._segment_at(canvas_y)
        if student is None or segment is None or not segment.region_id:
            return False
        pdf_pos = self._canvas_to_pdf_coords(canvas_x, canvas_y, segment)
        if pdf_pos is None:
            return False
        pdf_pos = clamp_into_box(pdf_pos[0], pdf_pos[1], segment.clip_box)

        task_code, _max_points = self._selected_correction_task()
        default_font_size = self._default_annotation_font_size
        annotation = PdfAnnotation(
            annotation_id=f"ann-{uuid4().hex[:12]}",
            student_pdf=student.pdf_filename,
            page_number=segment.page_number,
            annotation_type=annotation_type,
            content=content,
            color_hex=self._current_marker_color_hex(),
            x=pdf_pos[0],
            y=pdf_pos[1],
            task_code=task_code or "",
            region_id=segment.region_id,
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
