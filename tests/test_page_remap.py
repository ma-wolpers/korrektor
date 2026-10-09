"""Scan-Werkstatt re-mapping of page-bound exam data - one test per inventory row (see `page_remap`)."""

import pytest

from app.core.domain.models import ExamProject, PdfAnnotation, RegionAssignment, RegionBox, StudentExam, TaskDefinition, UnscoredPage
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
        regions=[
            RegionAssignment("sup", "", 1, RegionBox(0.0, 0.0, 100.0, 100.0), ["1A"], ["A"]),
            RegionAssignment("e1", "a.pdf", 1, RegionBox(100.0, 200.0, 300.0, 250.0), ["1A"], ["B"]),
            RegionAssignment("e2", "a.pdf", 2, RegionBox(0.0, 0.0, *_A4), ["2A"], ["C"]),
        ],
        tasks=[TaskDefinition("1A", "1A", 2.0), TaskDefinition("2A", "2A", 1.0)],
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


def test_einzelseiten_region_moves_with_its_page_and_its_box_is_transformed():
    result = remap_exam(_exam(), _plan())
    by_id = {region.region_id: region for region in result.exam.regions}

    assert set(by_id) == {"sup", "e1"}  # e2 lay on the deleted page 2
    assert by_id["sup"].page_number == 1  # Superseiten-Bereiche stay
    moved = by_id["e1"]
    transform = PageTransform(*_A4, 90.0)
    corners = [transform.map_point(x, y) for x in (100.0, 300.0) for y in (200.0, 250.0)]
    assert moved.page_number == 2
    assert (moved.box.x0, moved.box.y0, moved.box.x1, moved.box.y1) == pytest.approx(
        (min(c[0] for c in corners), min(c[1] for c in corners), max(c[0] for c in corners), max(c[1] for c in corners))
    )
    assert [task.code for task in result.exam.tasks] == ["1A"]  # 2A only had the deleted region
    assert any("Aufgabe 2A" in item for item in result.dropped)


def test_superseiten_region_on_a_page_someone_loses_is_rejected():
    """Rule A4: deleting Anna's only page 1 would leave Superseiten-Bereich A on a page she no longer has."""
    exam = _exam()
    transforms = {page: PageTransform(*_A4, 0.0) for page in (1, 2, 3)}
    plan = {"a.pdf": PdfPagePlan(mapping={1: None, 2: None, 3: None}, transforms=transforms, new_page_count=0)}

    with pytest.raises(ValueError, match="Bereich A liegt auf Seite 1, die Anna nicht hat"):
        remap_exam(exam, plan)


def test_unscored_pages_are_renumbered_or_dropped():
    result = remap_exam(_exam(), _plan())

    assert [(page.student_pdf, page.page_number) for page in result.exam.unscored_pages] == [("a.pdf", 1), ("b.pdf", 3)]


def test_page_count_and_dropped_report():
    original = _exam()
    result = remap_exam(original, _plan())

    assert [student.page_count for student in result.exam.students] == [2, 3]
    anna = [item for item in result.dropped if item.startswith("Anna: ")]
    assert len(anna) == 3 and all("Seite 2" in item for item in anna)
    assert original.students[0].page_count == 3 and len(original.pdf_annotations) == 3  # input untouched
