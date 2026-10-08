from __future__ import annotations

from pathlib import Path
from typing import Sequence

import fitz

from app.core.domain.models import StudentExam

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui


class MainWindowPageRenderMixin:
    """Page rendering shared by Zuschnitt, Extraseiten and Namen: single page, Superseite composite, wheel direction.

    Moved out of `main_window_region_editor.py` (file-size rule) without changes;
    `_build_superposed_pixmap` stays the pure computation and the display functions
    keep their own coordinate conventions (see docs/ARCHITEKTUR.md).
    """

    def _build_superposed_pixmap(
        self,
        *,
        students: Sequence[StudentExam],
        page_number: int,
        target_width: float = 520.0,
        clip: fitz.Rect | None = None,
    ) -> tuple[fitz.Pixmap, fitz.Rect, int] | None:
        """Composite one page across many students' PDFs into a dark-wins grayscale pixmap.

        The shared technical mechanism behind every Superseite use (Einlesemodus,
        Namenmodus region alignment, Supersymbol's filtered view, Punkte-
        Superposition's Bereich-cropped preview): pure computation over
        "which students, which page" with no canvas/Tkinter side effects,
        so each caller can display the result on its own canvas with its
        own coordinate/scale convention (see `_render_superposed_page`
        for the Einlesemodus/Namenmodus reading-canvas display, and
        `_render_supersymbol_filtered_page` for the Korrekturmodus
        correction-canvas display - the two already use different coordinate
        systems and must not be forced to share display code, only this math).

        `clip`, if given, crops every student's page to that box (same
        intersect-with-page-and-fall-back-to-full-page defensiveness as
        the normal single-student Korrektur-Vorschau,
        `main_window_correction_core.py`) instead of rendering the whole
        page - used by the Punkte-Superposition preview to show only the
        current Bereich.

        Returns `None` if no page of any student could be rendered.
        """
        if self._current_exam is None:
            return None

        pixmaps: list[fitz.Pixmap] = []
        reference_rect: fitz.Rect | None = None

        for student in students:
            if page_number > student.page_count:
                continue
            pdf_path = Path(self._current_exam.folder_path) / student.pdf_filename
            if not pdf_path.exists():
                continue

            document = self._doc_cache.get(student.pdf_filename)
            if document is None:
                try:
                    document = fitz.open(pdf_path)
                except Exception:
                    continue
                self._doc_cache[student.pdf_filename] = document

            try:
                page = document.load_page(page_number - 1)
            except Exception:
                continue

            effective_clip: fitz.Rect | None = None
            if clip is not None:
                effective_clip = clip.intersect(page.rect)
                if effective_clip.is_empty:
                    effective_clip = None

            if reference_rect is None:
                reference_rect = effective_clip if effective_clip is not None else page.rect
            scale = target_width / max(reference_rect.width, 1.0)

            try:
                pix = page.get_pixmap(
                    matrix=fitz.Matrix(scale, scale), clip=effective_clip, colorspace=fitz.csGRAY, alpha=False
                )
            except Exception:
                continue

            if not pixmaps:
                pixmaps.append(pix)
                continue

            first = pixmaps[0]
            if pix.width == first.width and pix.height == first.height and pix.n == first.n:
                pixmaps.append(pix)

        if not pixmaps or reference_rect is None:
            return None

        first = pixmaps[0]
        merged = bytearray(first.width * first.height)
        for y in range(first.height):
            source_start = y * first.stride
            target_start = y * first.width
            merged[target_start : target_start + first.width] = first.samples[source_start : source_start + first.width]

        for pix in pixmaps[1:]:
            for y in range(pix.height):
                source_start = y * pix.stride
                target_start = y * pix.width
                row = pix.samples[source_start : source_start + pix.width]
                for x, value in enumerate(row):
                    index = target_start + x
                    if value < merged[index]:
                        merged[index] = value

        merged_pixmap = fitz.Pixmap(fitz.csGRAY, first.width, first.height, bytes(merged), False)
        # Keep the PPM/PhotoImage encoding local to callers (each targets a
        # different Tkinter Canvas) - return the raw merged pixmap, the
        # reference page rect callers need for their own scale-factor math,
        # and the number of students actually merged into it (for "Quellen: N").
        return merged_pixmap, reference_rect, len(pixmaps)

    @staticmethod
    def _wheel_direction(event: ui.Event[ui.Misc]) -> int:
        if getattr(event, "num", None) == 4:
            return 1
        if getattr(event, "num", None) == 5:
            return -1
        delta = getattr(event, "delta", 0)
        if delta > 0:
            return 1
        if delta < 0:
            return -1
        return 0

    def _render_pdf_page(self, *, student: StudentExam, page_number: int) -> None:
        if self._current_exam is None:
            return

        pdf_path = Path(self._current_exam.folder_path) / student.pdf_filename
        if not pdf_path.exists():
            self._reading_info_var.set(f"Datei fehlt: {student.pdf_filename}")
            self._reading_canvas.delete("all")
            return

        document = self._doc_cache.get(student.pdf_filename)
        if document is None:
            document = fitz.open(pdf_path)
            self._doc_cache[student.pdf_filename] = document

        try:
            page = document.load_page(page_number - 1)
            page_rect = page.rect
            target_width = 520.0
            scale = target_width / max(page_rect.width, 1.0)
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)

            self._x_factor = page_rect.width / max(pix.width, 1)
            self._y_factor = page_rect.height / max(pix.height, 1)

            self._render_photo = ui.PhotoImage(data=pix.tobytes("ppm"), format="ppm")
            self._reading_canvas.configure(width=pix.width, height=pix.height)
            self._reading_canvas.delete("all")
            self._canvas_image_id = self._reading_canvas.create_image(0, 0, anchor=ui.NW, image=self._render_photo)
            self._reading_canvas.configure(scrollregion=(0, 0, pix.width, pix.height))
        except Exception as exc:
            self._reading_canvas.delete("all")
            self._reading_info_var.set(f"Fehler beim PDF-Rendering: {exc}")
            return

        self._draw_existing_regions(student.pdf_filename, page_number)
