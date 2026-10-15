"""PDF export as image stamps: rasterized position and orientation, print flag, replace on re-export, /Rotate."""

from __future__ import annotations

import fitz
import numpy
import pytest
from PIL import Image

from app.core.domain.mark_symbols import MARK_SYMBOLS
from app.core.domain.models import PdfAnnotation
from app.infrastructure.pdf.mark_stamps import MARKER_SUBJECT_PREFIX, add_mark_stamp, remove_marker_stamps

ZOOM = 3.0


def _annotation(content: str, *, rotation: float = 0.0, mirrored: bool = False, kind: str = "symbol") -> PdfAnnotation:
    annotation = PdfAnnotation(
        annotation_id="a1", student_pdf="S.pdf", page_number=1, annotation_type=kind, content=content,
        color_hex="#d62828", x=150.0, y=120.0, font_size=20.0, rotation_deg=rotation, mirrored=mirrored,
    )
    return annotation


def _raster(page: fitz.Page) -> Image.Image:
    pix = page.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), alpha=False)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def _red(image: Image.Image) -> numpy.ndarray:
    """Boolean mask of the red ink in a white page raster."""
    rgb = numpy.asarray(image).astype(int)
    return (rgb[..., 0] > 150) & (rgb[..., 1] < 140) & (rgb[..., 2] < 140)


def _ink_box(image: Image.Image) -> tuple[int, int, int, int] | None:
    """Bounding box ``(left, top, right, bottom)`` of the red ink, or ``None``."""
    mask = _red(image)
    rows, cols = numpy.nonzero(mask.any(axis=1))[0], numpy.nonzero(mask.any(axis=0))[0]
    if rows.size == 0:
        return None
    return int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1


def _page(rotation: int = 0) -> tuple[fitz.Document, fitz.Page]:
    document = fitz.open()
    page = document.new_page(width=300, height=240)
    if rotation:
        page.set_rotation(rotation)
    return document, page


@pytest.mark.parametrize("symbol", MARK_SYMBOLS, ids=lambda s: s.key)
@pytest.mark.parametrize(("rotation", "mirrored"), [(0.0, False), (90.0, False), (180.0, False), (0.0, True)])
def test_stamp_is_centred_on_the_anchor(symbol, rotation, mirrored):
    document, page = _page()
    add_mark_stamp(page, _annotation(symbol.content, rotation=rotation, mirrored=mirrored))
    box = _ink_box(_raster(page))
    document.close()
    assert box is not None
    center_x = (box[0] + box[2]) / 2 / ZOOM
    center_y = (box[1] + box[3]) / 2 / ZOOM
    assert abs(center_x - 150.0) <= 1.5
    assert abs(center_y - 120.0) <= 1.5


@pytest.mark.parametrize(
    ("rotation", "mirrored", "tip"),
    [(0.0, False, "right"), (90.0, False, "top"), (0.0, True, "left"), (90.0, True, "bottom")],
)
def test_rasterized_arrow_points_where_expected(rotation, mirrored, tip):
    document, page = _page()
    add_mark_stamp(page, _annotation("sym:arrow_straight", rotation=rotation, mirrored=mirrored))
    image = _raster(page)
    box = _ink_box(image)
    document.close()
    crop = image.crop(box)
    width, height = crop.size

    mask = _red(crop)

    def ink(region):
        left, top, right, bottom = region
        return int(mask[top:bottom, left:right].sum())

    halves = {
        "left": ink((0, 0, width // 2, height)), "right": ink((width - width // 2, 0, width, height)),
        "top": ink((0, 0, width, height // 2)), "bottom": ink((0, height - height // 2, width, height)),
    }
    opposite = {"right": "left", "left": "right", "top": "bottom", "bottom": "top"}[tip]
    assert halves[tip] > halves[opposite] * 1.2


def test_stamp_prints_and_carries_subject_and_label():
    document, page = _page()
    annot = add_mark_stamp(page, _annotation("✓"))
    assert annot.flags & fitz.PDF_ANNOT_IS_PRINT
    assert annot.info["subject"] == f"{MARKER_SUBJECT_PREFIX}a1"
    assert annot.info["content"] == "Richtig"
    document.close()


def test_reexport_replaces_old_marks_including_legacy_freetext():
    document, page = _page()
    legacy = page.add_freetext_annot(fitz.Rect(10, 10, 60, 30), "✓")
    legacy.set_info(subject=f"{MARKER_SUBJECT_PREFIX}old")
    foreign = page.add_text_annot((200, 200), "fremde Notiz")
    add_mark_stamp(page, _annotation("✓"))
    assert remove_marker_stamps(page) == 2
    remaining = [str((annot.info or {}).get("subject", "")) for annot in page.annots()]
    assert remaining == [str((foreign.info or {}).get("subject", ""))]
    document.close()


@pytest.mark.xfail(
    strict=True,
    reason="Bestehender Fehler (auch beim alten FreeText-Export): Rechteck in Koordinaten der sichtbaren Seite, "
    "PyMuPDF erwartet ungedrehte Koordinaten - separat auf der Wunschliste gemeldet.",
)
def test_stamp_on_rotated_page_lands_at_visible_position():
    document, page = _page(rotation=90)
    add_mark_stamp(page, _annotation("✓"))
    box = _ink_box(_raster(page))
    document.close()
    assert box is not None
    assert abs((box[0] + box[2]) / 2 / ZOOM - 150.0) <= 1.5
    assert abs((box[1] + box[3]) / 2 / ZOOM - 120.0) <= 1.5
