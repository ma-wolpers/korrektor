"""Write correction marks into a PDF page as image stamp annotations.

Each mark becomes one PDF Stamp annotation whose image is the ``mark_renderer``
output at export resolution (600 dpi) - the very pixels the correction preview
shows. The stamp rectangle is centred on the mark's anchor ``(x, y)`` and sized
from the rendered image, so a rotated or mirrored mark needs no position fix-ups.
Stamps carry the Print flag (PyMuPDF default for new annotations), so they print.

Each stamp carries ``subject = "KORREKTOR_MARKER:<annotation_id>"``; re-exporting
first removes every annotation with that prefix, so "Alle PDFs überschreiben" replaces
the marks instead of piling them up (also the FreeText marks of older versions).

Pages with a ``/Rotate`` entry: the mark's anchor is in coordinates of the *visible*
page (what the preview shows), but PyMuPDF reads annotation rectangles in unrotated
page coordinates and draws the image unrotated. So the rectangle is converted with
``page.derotation_matrix`` and the image is turned by ``page.rotation`` beforehand
(`_upright_on_page`) - the mark then looks exactly as on an unrotated page
(``test_stamp_on_rotated_page_*``). Pages rewritten by the Scan-Werkstatt have
``/Rotate 0`` and take the plain path.
"""

from __future__ import annotations

import io

import fitz
from PIL import Image

from app.core.domain.mark_symbols import SYMBOL_BY_CONTENT
from app.core.domain.models import PdfAnnotation
from app.infrastructure.rendering.mark_renderer import EXPORT_PX_PER_PT, MarkStyle, render_mark

MARKER_SUBJECT_PREFIX = "KORREKTOR_MARKER:"


def remove_marker_stamps(page: fitz.Page) -> int:
    """Delete every annotation written by Korrektor on ``page``; returns how many."""
    removed = 0
    for annot in list(page.annots() or []):
        subject = str((annot.info or {}).get("subject", ""))
        if subject.startswith(MARKER_SUBJECT_PREFIX):
            page.delete_annot(annot)
            removed += 1
    return removed


def stamp_rect(annotation: PdfAnnotation, width_pt: float, height_pt: float) -> fitz.Rect:
    """Rectangle of ``width_pt × height_pt`` centred on the mark's anchor point."""
    return fitz.Rect(
        annotation.x - width_pt / 2.0,
        annotation.y - height_pt / 2.0,
        annotation.x + width_pt / 2.0,
        annotation.y + height_pt / 2.0,
    )


def _upright_on_page(png: bytes, page_rotation: int) -> bytes:
    """Turn the stamp image so it looks upright on a page shown rotated by ``page_rotation`` degrees.

    PIL rotates counter-clockwise, the viewer turns the page clockwise - the two cancel
    (checked pixel for pixel against an unrotated page for 90°, 180° and 270°).
    """
    image = Image.open(io.BytesIO(png)).rotate(page_rotation, expand=True)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def add_mark_stamp(page: fitz.Page, annotation: PdfAnnotation) -> fitz.Annot:
    """Add ``annotation`` to ``page`` as an image stamp (see module docstring).

    The annotation's info text is the symbol label (e.g. "Richtig") or the comment,
    so PDF viewers listing annotations show something readable.
    """
    rendered = render_mark(MarkStyle.of(annotation), EXPORT_PX_PER_PT)
    rect = stamp_rect(annotation, rendered.width_pt, rendered.height_pt)
    png = rendered.png
    if page.rotation:
        rect = rect * page.derotation_matrix
        png = _upright_on_page(png, page.rotation)
    annot = page.add_stamp_annot(rect, stamp=png)
    symbol = SYMBOL_BY_CONTENT.get(annotation.content) if annotation.annotation_type == "symbol" else None
    annot.set_info(
        title="Korrektor",
        subject=f"{MARKER_SUBJECT_PREFIX}{annotation.annotation_id}",
        content=symbol.label if symbol is not None else annotation.content,
    )
    return annot
