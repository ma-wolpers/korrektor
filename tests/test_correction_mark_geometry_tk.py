"""Canvas geometry of image marks: bbox centre = anchor, selection frame, hit test, drag, rotation."""

from __future__ import annotations

import pytest
from test_correction_segments_tk import _add_marks, _drag_mark, _saved_mark, correction  # noqa: F401  (fixture)

from app.core.domain.models import PdfAnnotation

MARKS = [
    PdfAnnotation("g-sym", "Anna.pdf", 1, "symbol", "✓", "#d62828", 120, 120, task_code="1A", region_id="sup"),
    PdfAnnotation("g-arrow", "Anna.pdf", 1, "symbol", "sym:arrow_straight", "#d62828", 200, 150, task_code="1A", region_id="sup", rotation_deg=90.0),
    PdfAnnotation("g-mirror", "Anna.pdf", 1, "symbol", "sym:arrow_curved", "#d62828", 260, 200, task_code="1A", region_id="sup", mirrored=True),
    PdfAnnotation("g-text", "Anna.pdf", 1, "text", "Gut $x^2$", "#1d4ed8", 150, 250, task_code="1A", region_id="sup"),
]


def _centre(window, annotation_id: str) -> tuple[float, float]:
    left, top, right, bottom = window._correction_canvas.bbox(window._correction_annotation_items[annotation_id])
    return (left + right) / 2.0, (top + bottom) / 2.0


def _anchor(window, annotation_id: str) -> tuple[float, float]:
    mark = window._annotation_by_id(annotation_id)
    return window._pdf_to_canvas_coords(mark.x, mark.y, window._segment_for_annotation(mark))


@pytest.fixture
def marks(correction):
    _add_marks(correction, *[PdfAnnotation(**{slot: getattr(m, slot) for slot in PdfAnnotation.__slots__}) for m in MARKS])
    return correction


@pytest.mark.parametrize("annotation_id", [m.annotation_id for m in MARKS])
def test_image_centre_is_the_anchor_point(marks, annotation_id):
    window = marks
    assert window._correction_canvas.type(window._correction_annotation_items[annotation_id]) == "image"
    assert _centre(window, annotation_id) == pytest.approx(_anchor(window, annotation_id), abs=1.0)


def test_selection_frame_surrounds_the_image_and_a_click_on_the_centre_hits_it(marks):
    window = marks
    canvas = window._correction_canvas
    window._correction_selected_annotation_id = "g-arrow"
    window._render_correction_annotations()
    item = window._correction_annotation_items["g-arrow"]
    left, top, right, bottom = canvas.bbox(item)
    frames = [i for i in canvas.find_withtag("correction_annotation") if canvas.type(i) == "rectangle"]
    assert len(frames) == 1
    assert canvas.coords(frames[0]) == pytest.approx([left - 4, top - 2, right + 4, bottom + 2])
    centre_x, centre_y = _centre(window, "g-arrow")
    assert item in canvas.find_overlapping(centre_x, centre_y, centre_x, centre_y)
    assert canvas.find_overlapping(centre_x, centre_y, centre_x, centre_y)[-1] == item  # topmost = "current"


def test_dragging_moves_the_centre_by_the_drag_delta(marks):
    window = marks
    start = _anchor(window, "g-text")
    target = (start[0] + 30.0, start[1] + 20.0)
    _drag_mark(window, "g-text", target)
    assert _centre(window, "g-text") == pytest.approx(target, abs=1.0)
    saved = _saved_mark(window, "g-text")
    assert (saved.x, saved.y) != (150, 250)


def test_rotating_keeps_the_centre(marks):
    window = marks
    before = _centre(window, "g-sym")
    window._correction_selected_annotation_id = "g-sym"
    window._rotate_selected_correction_annotation(-90.0)
    assert _centre(window, "g-sym") == pytest.approx(before, abs=1.0)
