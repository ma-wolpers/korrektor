"""Scan-Werkstatt re-mapping of page-bound exam data - one test per inventory row (see `page_remap`)."""

import pytest

from app.core.domain.models import ExamProject, ExtraPageAssignment, PdfAnnotation, RegionBox, StudentExam, UnscoredPage
from app.core.domain.page_geometry import PageTransform
from app.core.domain.page_remap import PdfPagePlan, remap_exam

_A4 = (595.0, 842.0)


def _exam() -> ExamProject:
    """Two persons with 3 pages each; marks, an assignment and unscored pages on both."""
    def mark(mark_id, pdf, page, x=100.0, y=200.0, rotation=0.0):
        return PdfAnnotation(mark_id, pdf, page, "symbol", "✓", "#ff0000", x, y, rotation_deg=rotation)

    return ExamProject(
        exam_id="x",
        exam_name="Mathe",
        folder_path="unused",
        created_at="t",
        updated_at="t",
        standard_page_count=3,
        students=[
            StudentExam(student_id="a", display_name="Anna", pdf_filename="a.pdf", page_count=3),
            StudentExam(student_id="b", display_name="Ben", pdf_filename="b.pdf", page_count=3),
        ],
        pdf_annotations=[mark("m1", "a.pdf", 1, rotation=10.0), mark("m2", "a.pdf", 2), mark("m3", "b.pdf", 2)],
        extra_page_assignments=[
            ExtraPageAssignment("e1", "a.pdf", 1, RegionBox(0.0, 0.0, *_A4), ["A1"]),
            ExtraPageAssignment("e2", "a.pdf", 2, RegionBox(0.0, 0.0, *_A4), ["A2"]),
        ],
        unscored_pages=[UnscoredPage("a.pdf", 3), UnscoredPage("a.pdf", 2), UnscoredPage("b.pdf", 3)],
    )


def _plan() -> dict[str, PdfPagePlan]:
    """a.pdf: order [3, 1, 2], page 2 deleted, page 1 turned 90° clockwise."""
    transforms = {page: PageTransform(*_A4, 0.0) for page in (1, 2, 3)}
    transforms[1] = PageTransform(*_A4, 90.0)
    return {"a.pdf": PdfPagePlan(mapping={1: 2, 2: None, 3: 1}, transforms=transforms, new_page_count=2)}


def test_annotations_move_with_their_page_and_turn_with_it():
    result = remap_exam(_exam(), _plan())
    by_id = {mark.annotation_id: mark for mark in result.exam.pdf_annotations}

    assert by_id["m1"].page_number == 2
    assert (by_id["m1"].x, by_id["m1"].y) == pytest.approx(PageTransform(*_A4, 90.0).map_point(100.0, 200.0))
    assert by_id["m1"].rotation_deg == pytest.approx(280.0)  # 10° ccw minus one clockwise quarter turn
    assert "m2" not in by_id
    assert by_id["m3"].page_number == 2  # other person untouched


def test_extra_assignment_box_becomes_the_full_new_page():
    result = remap_exam(_exam(), _plan())
    (assignment,) = result.exam.extra_page_assignments

    assert assignment.assignment_id == "e1" and assignment.page_number == 2
    assert (assignment.box.x0, assignment.box.y0, assignment.box.x1, assignment.box.y1) == pytest.approx((0, 0, 842, 595))


def test_unscored_pages_are_renumbered_or_dropped():
    result = remap_exam(_exam(), _plan())

    assert [(page.student_pdf, page.page_number) for page in result.exam.unscored_pages] == [("a.pdf", 1), ("b.pdf", 3)]


def test_page_count_and_dropped_report():
    original = _exam()
    result = remap_exam(original, _plan())

    assert [student.page_count for student in result.exam.students] == [2, 3]
    assert len(result.dropped) == 3 and all(item.startswith("Anna: ") and "Seite 2" in item for item in result.dropped)
    assert original.students[0].page_count == 3 and len(original.pdf_annotations) == 3  # input untouched
