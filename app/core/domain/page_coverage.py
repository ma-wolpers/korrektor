"""Which student pages are covered by a Superseiten-Bereich - basis of Zuschnitt Schritt 2 ("Einzelseiten").

Page numbers are 1-based within each student's PDF. Two different sets
(binding, A6 of the plan):

- `compute_uncovered_pages` is the **navigation set** of Schritt 2: every
  page whose page number carries no Superseiten-Bereich (``regions`` with
  ``student_pdf == ""``) - *including* pages already handled, so decisions
  can be reviewed and changed.
- `open_pages` are the uncovered pages that still need a decision: no
  Einzelseiten-Bereich of that student on the page and not "ohne
  Bewertung" (``unscored_pages``). Only these make the overview flag open.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.core.domain.models import ExamProject

MixedState = Literal["on", "off", "mixed"]


def template_page_numbers(exam: ExamProject) -> set[int]:
    """Page numbers that carry at least one template region."""
    return {region.page_number for region in exam.regions if not region.student_pdf}


def compute_uncovered_pages(exam: ExamProject) -> dict[str, list[int]]:
    """``{pdf_filename: [uncovered pages]}`` for every student (handled pages included).

    Step 2 walks all of them, so a decision ("ohne Bewertung") can be
    reviewed and toggled back.
    """
    covered = template_page_numbers(exam)
    return {
        student.pdf_filename: [page for page in range(1, student.page_count + 1) if page not in covered]
        for student in exam.students
    }


def unscored_set(exam: ExamProject) -> set[tuple[str, int]]:
    """``{(pdf, page)}`` marked "ohne Bewertung"."""
    return {(item.student_pdf, item.page_number) for item in exam.unscored_pages}


def assigned_set(exam: ExamProject) -> set[tuple[str, int]]:
    """``{(pdf, page)}`` carrying at least one Einzelseiten-Bereich."""
    return {(region.student_pdf, region.page_number) for region in exam.regions if region.student_pdf}


def all_pages(exam: ExamProject) -> dict[str, list[int]]:
    """``{pdf_filename: [1..page_count]}`` - Schritt 2 navigation with "Auch Seiten mit Superseiten-Bereich"."""
    return {student.pdf_filename: list(range(1, student.page_count + 1)) for student in exam.students}


def open_pages(exam: ExamProject) -> list[tuple[str, int]]:
    """Uncovered pages that are neither assigned nor "ohne Bewertung" (they make the overview flag open)."""
    handled = unscored_set(exam) | assigned_set(exam)
    return [
        (pdf, page)
        for pdf, pages in compute_uncovered_pages(exam).items()
        for page in pages
        if (pdf, page) not in handled
    ]


def single_pages_with_regions(exam: ExamProject, pdf_filename: str) -> list[int]:
    """Pages of one student that carry an Einzelseiten-Bereich (what "Einzelseiten ansehen" shows)."""
    return sorted({region.page_number for region in exam.regions if region.student_pdf == pdf_filename})


def uncovered_for_all(exam: ExamProject) -> list[int]:
    """Page numbers that exist in every student's PDF and are uncovered (e.g. a Deckblatt)."""
    if not exam.students:
        return []
    shortest = min(student.page_count for student in exam.students)
    covered = template_page_numbers(exam)
    return [page for page in range(1, shortest + 1) if page not in covered]


def pages_missing_markings(exam: ExamProject) -> list[int]:
    """Standard page numbers without a template region that still have an open page for someone.

    Replaces the old "every standard page needs a region" rule: a Deckblatt
    marked "ohne Bewertung" for everybody is complete, not missing.
    """
    open_numbers = {page for _pdf, page in open_pages(exam)}
    covered = template_page_numbers(exam)
    return [page for page in range(1, exam.standard_page_count + 1) if page not in covered and page in open_numbers]


@dataclass(frozen=True)
class PageForAllPlan:
    """Who "Seite N bei allen ohne Bewertung" changes and who it deliberately leaves alone.

    ``excluded`` are students whose page N already carries an
    Einzelseiten-Bereich - conscious individual decisions are never
    overwritten. ``unchanged`` are already "ohne Bewertung".
    """

    page_number: int
    affected: tuple[str, ...]
    excluded: tuple[str, ...]
    unchanged: tuple[str, ...]


def plan_page_for_all(exam: ExamProject, page_number: int) -> PageForAllPlan:
    """Plan "Seite N bei allen ohne Bewertung" ("Bereich für alle zuordnen" was dropped: draw a Superseiten-Bereich instead).

    Only meaningful for ``page_number in uncovered_for_all(exam)``; other
    pages yield an empty plan.
    """
    if page_number not in uncovered_for_all(exam):
        return PageForAllPlan(page_number, (), (), ())
    assigned = assigned_set(exam)
    unscored = unscored_set(exam)
    affected, excluded, unchanged = [], [], []
    for student in exam.students:
        key = (student.pdf_filename, page_number)
        if key in assigned:
            excluded.append(student.pdf_filename)
        elif key in unscored:
            unchanged.append(student.pdf_filename)
        else:
            affected.append(student.pdf_filename)
    return PageForAllPlan(page_number, tuple(affected), tuple(excluded), tuple(unchanged))


def unscored_state_for_all(exam: ExamProject, page_number: int) -> MixedState:
    """State of the "Seite N bei allen ohne Bewertung" switch over the non-assigned students."""
    plan = plan_page_for_all(exam, page_number)
    if not plan.unchanged:
        return "off"
    return "on" if not plan.affected else "mixed"
