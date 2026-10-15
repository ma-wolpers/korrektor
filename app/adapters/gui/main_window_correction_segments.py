from __future__ import annotations

from pathlib import Path

import fitz

from app.adapters.gui.main_window_types import CorrectionSegment, CorrectionTemplate
from app.core.domain.annotation_move import MoveTarget
from app.core.domain.models import ExamProject, PdfAnnotation, TaskDefinition
from app.core.domain.task_regions import regions_for_task, tasks_of_region

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui

_HEADER_HEIGHT = 20.0
_GAP = 12.0
_TARGET_WIDTH = 560.0


class MainWindowCorrectionSegmentsMixin:
    """Task-centric correction view: every region of the current (sub)task, stacked as segments.

    For the current person and task, `regions_for_task` yields the
    Superseiten-Bereiche plus that person's Einzelseiten-Bereiche (by page
    and top edge); each is rendered as a crop with a small header
    ("Seite 2" / "Seite 5 · Einzelseite") into one scrollable canvas.
    Coordinates are always converted through exactly one segment:
    `_segment_at` (a click), `_segment_for_annotation` (drawing a mark), or
    the remembered drag segment (a drag moves the mark into the region under
    the cursor, see `_drag_target_segment`).
    The full-page Supersymbol/Superposition previews install a single
    segment the same way (`_install_single_segment`).
    """

    # --- templates (all regions, keyed by region_id) ---------------------------------

    @staticmethod
    def _build_correction_templates(exam: ExamProject) -> dict[str, CorrectionTemplate]:
        """One `CorrectionTemplate` per region (Superseiten and Einzelseiten), keyed by ``region_id``.

        Used to resolve a mark's region box (copy, PDF writeback). Assumes
        ``exam`` passed `validate_regions` (unique ids and labels).
        """
        return {
            region.region_id: CorrectionTemplate(
                region_id=region.region_id,
                area_code=(region.assigned_area_codes[0].strip().upper() if region.assigned_area_codes else ""),
                page_number=region.page_number,
                box=(region.box.x0, region.box.y0, region.box.x1, region.box.y1),
                tasks=[TaskDefinition(task.code, task.name, task.max_points) for task in tasks_of_region(exam, region)],
            )
            for region in exam.regions
        }

    def _current_correction_template(self) -> CorrectionTemplate | None:
        """Primary region of the current task: its first Superseiten-Bereich, reduced to that one task.

        Supersymbol and Punkte-/Noten-Superposition need a page all persons
        share, so they work on this region; ``None`` if the task lives only
        in Einzelseiten-Bereiche (those features are then unavailable).
        """
        code, _max_points = self._selected_correction_task()
        if code is None or self._current_exam is None:
            return None
        for region in regions_for_task(self._current_exam, code, pdf_filename=""):
            template = self._correction_templates.get(region.region_id)
            if template is not None and not region.student_pdf:
                task = next((task for task in template.tasks if task.code == code), None)
                return CorrectionTemplate(template.region_id, template.area_code, template.page_number, template.box, [task] if task else [])
        return None

    def _current_correction_task_scope(self) -> CorrectionTemplate | None:
        """The current task as a one-task scope for "Fertig" and "alle bewertet" (independent of its regions)."""
        code, max_points = self._selected_correction_task()
        if code is None:
            return None
        return CorrectionTemplate(region_id="", area_code=code, page_number=0, box=(0.0, 0.0, 0.0, 0.0), tasks=[TaskDefinition(code, code, max_points)])

    # --- segments --------------------------------------------------------------------

    def _segment_at(self, y: float) -> CorrectionSegment | None:
        """Segment whose image contains canvas height ``y`` (``None`` on a header/gap)."""
        return next((segment for segment in self._correction_segments if segment.y_offset <= y <= segment.y_offset + segment.height), None)

    def _segment_for_annotation(self, annotation: PdfAnnotation) -> CorrectionSegment | None:
        """Segment a mark belongs to: same region, or (legacy, no region) same page and inside the crop."""
        for segment in self._correction_segments:
            if segment.page_number != annotation.page_number:
                continue
            if annotation.region_id:
                if annotation.region_id == segment.region_id or not segment.region_id:
                    return segment
            elif self._point_in_box(annotation.x, annotation.y, segment.clip_box):
                return segment
        return None

    def _nearest_segment_point(self, canvas_x: float, canvas_y: float) -> tuple[float, float] | None:
        """Canvas point on the image of the segment nearest to ``(canvas_x, canvas_y)``, or ``None`` without segments.

        A point on a segment's image is returned unchanged. On a header, a
        gap, beside a narrow image or past the last one, it moves to the
        nearest point of the vertically nearest segment's image, so a mark
        placed there ("Kommentar einfügen" uses the preview centre) always
        lands inside a region instead of being silently dropped.
        """
        if not self._correction_segments:
            return None
        segment = min(
            self._correction_segments,
            key=lambda item: max(item.y_offset - canvas_y, 0.0, canvas_y - (item.y_offset + item.height)),
        )
        image_width = (segment.clip_box[2] - segment.clip_box[0]) * segment.scale
        return min(max(canvas_x, 0.0), image_width), min(max(canvas_y, segment.y_offset), segment.y_offset + segment.height)

    def _drag_target_segment(self, canvas_y: float, *, moves_whole_group: bool, is_synced: bool) -> CorrectionSegment | None:
        """Segment a dragged mark belongs to now: the region under the cursor, or the one it is in.

        The mark switches region as soon as the cursor is over another
        region's crop (symbol and text alike). It keeps its current segment
        (``_correction_drag_segment``) while the cursor is over a header, a
        gap, outside every crop, or over a segment without ``region_id``.
        A synced mark may only switch if its whole group moves along
        (``moves_whole_group``) and only into a Superseiten-Bereich: group
        members share one region, and "Durchdrücken" exists only there. An
        Alt-dragged or position-detached member therefore stays in its region.
        """
        current = self._correction_drag_segment
        candidate = self._segment_at(canvas_y)
        if candidate is None or candidate == current or not candidate.region_id:
            return current
        if is_synced and (not moves_whole_group or candidate.is_single_page):
            return current
        return candidate

    def _move_target_for_segment(self, segment: CorrectionSegment) -> MoveTarget:
        """`MoveTarget` of ``segment``: its region, page, rendered crop and the region's tasks."""
        region = next((item for item in self._current_exam.regions if item.region_id == segment.region_id), None)
        task_codes = tuple(region.task_codes) if region is not None else ()
        return MoveTarget(segment.region_id, segment.page_number, segment.clip_box, task_codes)

    def _canvas_to_pdf_coords(self, x: float, y: float, segment: CorrectionSegment | None = None) -> tuple[float, float] | None:
        """Canvas point -> PDF point of ``segment`` (default: the segment under ``y``)."""
        segment = segment or self._segment_at(y)
        if segment is None or segment.scale <= 0:
            return None
        return segment.clip_box[0] + x / segment.scale, segment.clip_box[1] + (y - segment.y_offset) / segment.scale

    def _pdf_to_canvas_coords(self, x: float, y: float, segment: CorrectionSegment | None) -> tuple[float, float] | None:
        """PDF point of ``segment`` -> canvas point."""
        if segment is None or segment.scale <= 0:
            return None
        return (x - segment.clip_box[0]) * segment.scale, segment.y_offset + (y - segment.clip_box[1]) * segment.scale

    def _install_single_segment(self, *, region_id: str, page_number: int, clip_box, scale: float, height: float) -> None:
        """Full-page/one-crop previews (Supersymbol, Superposition): exactly one segment at the canvas top."""
        self._correction_segments = [CorrectionSegment(region_id, page_number, tuple(map(float, clip_box)), scale, 0.0, height)]

    def _render_correction_preview(self) -> None:
        """Render every region of the current task for the current person, stacked, and refresh the status line."""
        self._correction_canvas.delete("all")
        self._correction_segments = []
        self._correction_photos = []
        student = self._current_correction_student()
        code, _max_points = self._selected_correction_task()
        if self._current_exam is None or student is None or code is None:
            self._correction_info_var.set("Korrektur: keine Daten")
            return
        position = f"{student.display_name} ({self._correction_cursor + 1}/{len(self._correction_student_indices)})"
        regions = regions_for_task(self._current_exam, code, student.pdf_filename, student.page_count)
        if not regions:
            self._correction_canvas.create_text(12, 12, anchor=ui.NW, text=f"Für diese Person gibt es keinen Bereich zu {code}.", fill="#6b7280")
            self._correction_info_var.set(f"Aufgabe {code} | {position} | kein Bereich")
            self._render_correction_annotations()
            return
        try:
            document = self._correction_document(student.pdf_filename)
            y, width = 0.0, 0.0
            for region in regions:
                page = document.load_page(region.page_number - 1)
                clip = fitz.Rect(region.box.x0, region.box.y0, region.box.x1, region.box.y1).intersect(page.rect)
                if clip.is_empty:
                    clip = page.rect
                scale = (_TARGET_WIDTH / max(clip.width, 1.0)) * (self._correction_zoom_percent / 100.0)
                pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=clip, alpha=False, annots=False)
                header = f"Seite {region.page_number}" + (" · Einzelseite" if region.student_pdf else "")
                self._correction_canvas.create_text(2, y + 2, anchor=ui.NW, text=header, fill="#6b7280", tags=("segment_header",))
                y += _HEADER_HEIGHT
                photo = ui.PhotoImage(data=pix.tobytes("ppm"), format="ppm")
                self._correction_photos.append(photo)
                self._correction_canvas.create_image(0, y, anchor=ui.NW, image=photo)
                self._correction_segments.append(
                    CorrectionSegment(region.region_id, region.page_number, (clip.x0, clip.y0, clip.x1, clip.y1), scale, y, float(pix.height), bool(region.student_pdf))
                )
                y += pix.height + _GAP
                width = max(width, float(pix.width))
            self._correction_canvas.configure(scrollregion=(0, 0, width, y))
            self._render_correction_annotations()
            pages = ", ".join(str(region.page_number) for region in regions)
            self._correction_info_var.set(f"Aufgabe {code} | {position} | Seite {pages}" + (f" | {len(regions)} Bereiche" if len(regions) > 1 else ""))
        except Exception as exc:
            self._correction_canvas.delete("all")
            self._correction_segments = []
            self._correction_info_var.set(f"Fehler beim Korrektur-Rendering: {exc}")

    def _correction_document(self, pdf_filename: str) -> fitz.Document:
        """Open (and cache) a student's PDF; raises if the file is missing."""
        document = self._doc_cache.get(pdf_filename)
        if document is None:
            path = Path(self._current_exam.folder_path) / pdf_filename
            if not path.exists():
                raise FileNotFoundError(f"Datei fehlt: {pdf_filename}")
            document = fitz.open(path)
            self._doc_cache[pdf_filename] = document
        return document
