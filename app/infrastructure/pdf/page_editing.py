"""Scan-Werkstatt PDF I/O: build edited pages from a source PDF (order, deletion, rotation, shift).

`render_edited_page` (preview) and `write_edited_pdf` (result) share
`_append_edited_page`, so what the preview shows is exactly what gets
written. Page numbers in the API are 1-based within the PDF; PyMuPDF's
0-based indices appear only in `_append_edited_page`. Only page content
and order are guaranteed (no links, form fields or annotations - also not
Korrektor's own markers, which "Alle PDFs überschreiben" writes again).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import fitz

from app.core.domain.page_geometry import PageTransform, normalize_rotation
from app.infrastructure.pdf.pdf_sources import close_quietly


@dataclass(frozen=True)
class PageEdit:
    """Edit of one *original* page (keyed by its original number): rotation, deletion and shift, independent.

    ``rotation_deg`` clockwise around the page center; ``offset_x_pt``/
    ``offset_y_pt`` shift the (rotated) content in points on the edited page,
    positive = right/down; ``deleted`` drops the page. The default instance
    means "unchanged".
    """

    rotation_deg: float = 0.0
    deleted: bool = False
    offset_x_pt: float = 0.0
    offset_y_pt: float = 0.0

    @property
    def is_shifted(self) -> bool:
        """True if the content is moved."""
        return abs(self.offset_x_pt) > 1e-9 or abs(self.offset_y_pt) > 1e-9


def source_transform(source: fitz.Document, page_number: int, edit: PageEdit) -> PageTransform:
    """`PageTransform` of original page ``page_number`` (1-based) under ``edit``."""
    rect = source.load_page(page_number - 1).rect
    return PageTransform(float(rect.width), float(rect.height), normalize_rotation(edit.rotation_deg), edit.offset_x_pt, edit.offset_y_pt)


def _append_edited_page(target: fitz.Document, source: fitz.Document, page_number: int, edit: PageEdit) -> None:
    """Append original page ``page_number`` (1-based) of ``source`` to ``target`` as edited.

    Pages neither rotated nor shifted are copied as they are (``/Rotate``
    kept, annotations dropped). Otherwise a new page of the target size
    shows the visible source content rotated clockwise around the center at
    scale 1:1 (`show_pdf_page` rotates counter-clockwise, hence the sign)
    and shifted by the offset; what lies outside the page is clipped.
    """
    rotation = normalize_rotation(edit.rotation_deg)
    if rotation == 0.0 and not edit.is_shifted:
        target.insert_pdf(source, from_page=page_number - 1, to_page=page_number - 1, links=False, annots=False, widgets=False)
        return
    transform = source_transform(source, page_number, edit)
    width, height = transform.target_size
    page = target.new_page(width=width, height=height)
    page.show_pdf_page(fitz.Rect(*transform.bounding_box_of_rotated_source()), source, page_number - 1, rotate=-rotation)


def render_edited_page(source: fitz.Document, page_number: int, edit: PageEdit, zoom: float) -> fitz.Pixmap:
    """Pixmap of original page ``page_number`` as it will look after editing (Scan-Werkstatt preview)."""
    single = fitz.open()
    try:
        _append_edited_page(single, source, page_number, edit)
        return single.load_page(0).get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    finally:
        close_quietly(single)


def write_edited_pdf(
    source_path: Path, order: Sequence[int], edits: Mapping[int, PageEdit], target_path: Path
) -> int:
    """Write the edited PDF to ``target_path`` and return its page count.

    ``order`` lists original page numbers (1-based) in the new order;
    ``edits`` is keyed by original page number. Deleted pages are skipped.
    The source is opened read-only and always closed; ``target_path`` is
    written in one ``save`` (callers write to a temporary name first).
    """
    source = fitz.open(source_path)
    target = fitz.open()
    try:
        for page_number in order:
            edit = edits.get(page_number, PageEdit())
            if not edit.deleted:
                _append_edited_page(target, source, page_number, edit)
        if target.page_count == 0:
            raise ValueError(f"{source_path.name}: alle Seiten wären gelöscht")
        target.save(target_path)
        return target.page_count
    finally:
        close_quietly(target)
        close_quietly(source)
