"""Re-map page-bound exam data after Scan-Werkstatt edits (pure, on a copy of the exam).

Inventory (binding, see the Scan-Werkstatt plan): per edited student PDF

- ``pdf_annotations``: page renumbered; position mapped with the same
  `PageTransform` as the page content; the mark's own rotation (counter-
  clockwise degrees, like Tk/PDF) loses 90° per clockwise quarter turn of
  the page; on a deleted page the mark is dropped (reported).
- ``extra_page_assignments``: page renumbered; the box model is "whole
  visible page", so the box becomes the full edited page; dropped on a
  deleted page (reported).
- ``unscored_pages``: renumbered; dropped on a deleted page (reported).
- ``StudentExam.page_count``: new page count.

Template ``regions``, completions, comments, scores, categories, the name
field and the grading snapshot are not page-bound per student and stay.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from app.core.domain.models import ExamProject, RegionBox
from app.core.domain.page_geometry import PageTransform, quarter_turns


@dataclass(frozen=True)
class PdfPagePlan:
    """Edits of one student PDF: ``mapping`` old -> new page (``None`` = deleted), transform per old page."""

    mapping: dict[int, int | None]
    transforms: dict[int, PageTransform]
    new_page_count: int


@dataclass(frozen=True)
class RemapResult:
    """The re-mapped exam copy and a German description of everything that is dropped."""

    exam: ExamProject
    dropped: tuple[str, ...]


def remap_exam(exam: ExamProject, plans: dict[str, PdfPagePlan]) -> RemapResult:
    """Return a copy of ``exam`` with all page-bound data of the PDFs in ``plans`` re-mapped."""
    result = ExamProject.from_dict(exam.to_dict())
    names = {student.pdf_filename: student.display_name for student in result.students}
    dropped: list[str] = []

    annotations = []
    for annotation in result.pdf_annotations:
        plan = plans.get(annotation.student_pdf)
        if plan is None:
            annotations.append(annotation)
            continue
        new_page = plan.mapping.get(annotation.page_number)
        if new_page is None:
            dropped.append(f"{names.get(annotation.student_pdf, annotation.student_pdf)}: Symbol „{annotation.content}“ auf Seite {annotation.page_number}")
            continue
        transform = plan.transforms[annotation.page_number]
        x, y = transform.map_point(annotation.x, annotation.y)
        rotation = (annotation.rotation_deg - 90.0 * quarter_turns(transform.rotation_deg)) % 360.0
        annotations.append(replace(annotation, page_number=new_page, x=x, y=y, rotation_deg=rotation))
    result.pdf_annotations = annotations

    assignments = []
    for assignment in result.extra_page_assignments:
        plan = plans.get(assignment.student_pdf)
        if plan is None:
            assignments.append(assignment)
            continue
        new_page = plan.mapping.get(assignment.page_number)
        if new_page is None:
            dropped.append(f"{names.get(assignment.student_pdf, assignment.student_pdf)}: Bereichszuordnung auf Seite {assignment.page_number}")
            continue
        width, height = plan.transforms[assignment.page_number].target_size
        assignments.append(replace(assignment, page_number=new_page, box=RegionBox(0.0, 0.0, width, height)))
    result.extra_page_assignments = assignments

    unscored = []
    for page in result.unscored_pages:
        plan = plans.get(page.student_pdf)
        if plan is None:
            unscored.append(page)
            continue
        new_page = plan.mapping.get(page.page_number)
        if new_page is None:
            dropped.append(f"{names.get(page.student_pdf, page.student_pdf)}: „ohne Bewertung“ auf Seite {page.page_number}")
            continue
        unscored.append(replace(page, page_number=new_page))
    result.unscored_pages = unscored

    for student in result.students:
        if student.pdf_filename in plans:
            student.page_count = plans[student.pdf_filename].new_page_count
    return RemapResult(exam=result, dropped=tuple(dropped))
