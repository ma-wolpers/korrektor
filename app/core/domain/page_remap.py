"""Re-map page-bound exam data after Scan-Werkstatt edits (pure, on a copy of the exam).

Inventory (binding, see the Scan-Werkstatt plan): per edited student PDF

- ``pdf_annotations``: page renumbered; position mapped with the same
  `PageTransform` as the page content; the mark's own rotation (counter-
  clockwise degrees, like Tk/PDF) loses 90° per clockwise quarter turn of
  the page; on a deleted page the mark is dropped (reported).
- Einzelseiten-Bereiche (``regions`` with ``student_pdf``): page renumbered;
  box = hull of its four corners mapped with the page's `PageTransform`
  (clipped to the page); dropped on a deleted page (reported). Tasks that
  then have no region left are removed (reported); marks/"Fertig" entries
  are cleaned up by `task_regions.cleanup_after_region_change`.
- ``unscored_pages``: renumbered; dropped on a deleted page (reported).
- ``StudentExam.page_count``: new page count.

Superseiten-Bereiche, comments, scores, categories, the name field and the
grading snapshot are not page-bound per student and stay. Rule A4: if the
edits would leave a Superseiten-Bereich on a page some student no longer
has, `remap_exam` raises `ValueError` naming region, page and person.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from app.core.domain.models import ExamProject, RegionBox
from app.core.domain.page_geometry import PageTransform, quarter_turns
from app.core.domain.task_regions import cleanup_after_region_change, prune_orphan_tasks, superseiten_page_violations


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

    regions = []
    for region in result.regions:
        plan = plans.get(region.student_pdf) if region.student_pdf else None
        if plan is None:
            regions.append(region)
            continue
        new_page = plan.mapping.get(region.page_number)
        label = region.assigned_area_codes[0] if region.assigned_area_codes else region.region_id
        if new_page is None:
            dropped.append(f"{names.get(region.student_pdf, region.student_pdf)}: Einzelseiten-Bereich {label} auf Seite {region.page_number}")
            continue
        box = _transformed_box(plan.transforms[region.page_number], region.box)
        regions.append(replace(region, page_number=new_page, box=box))
    result.regions = regions
    for code in prune_orphan_tasks(result):
        dropped.append(f"Aufgabe {code} (hatte nur Bereiche auf gelöschten Seiten)")
    cleanup_after_region_change(result)

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
    before = set(superseiten_page_violations(exam))
    introduced = [problem for problem in superseiten_page_violations(result) if problem not in before]
    if introduced:
        raise ValueError(
            "Danach lägen Superseiten-Bereiche auf Seiten, die nicht alle Personen haben:\n"
            + "\n".join(f"• {problem}" for problem in introduced)
            + "\nBitte diese Seiten nicht löschen oder den Bereich im Zuschnitt vorher verschieben."
        )
    return RemapResult(exam=result, dropped=tuple(dropped))


def _transformed_box(transform: PageTransform, box: RegionBox) -> RegionBox:
    """Axis-aligned hull of the four mapped corners, clipped to the edited page."""
    corners = [transform.map_point(x, y) for x in (box.x0, box.x1) for y in (box.y0, box.y1)]
    width, height = transform.target_size
    xs = [min(max(x, 0.0), width) for x, _ in corners]
    ys = [min(max(y, 0.0), height) for _, y in corners]
    return RegionBox(min(xs), min(ys), max(xs), max(ys))
