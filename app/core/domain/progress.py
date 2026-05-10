from __future__ import annotations

from dataclasses import dataclass

from app.core.domain.models import ExamProject


@dataclass(slots=True)
class ExamProgress:
    reading_percent: float
    correction_percent: float
    region_count: int
    corrected_region_count: int
    has_unassigned_extra_pages: bool
    has_missing_page_markings: bool


class ProgressCalculator:
    def compute(self, exam: ExamProject) -> ExamProgress:
        region_count = len(exam.regions) + len(exam.extra_page_assignments)
        corrected_region_count = (
            sum(1 for region in exam.regions if region.is_corrected)
            + sum(1 for assignment in exam.extra_page_assignments if assignment.is_corrected)
        )

        read_complete_count = (
            sum(1 for region in exam.regions if region.is_read_complete)
            + sum(1 for assignment in exam.extra_page_assignments if assignment.is_read_complete)
        )
        reading_percent = 100.0 if region_count == 0 else (read_complete_count / region_count) * 100.0
        correction_percent = 100.0 if region_count == 0 else (corrected_region_count / region_count) * 100.0

        expected_extra_pages = {
            (student.pdf_filename, page)
            for student in exam.students
            for page in student.extra_pages
        }
        assigned_extra_pages = {
            (assignment.student_pdf, assignment.page_number)
            for assignment in exam.extra_page_assignments
        }
        has_unassigned_extra_pages = bool(expected_extra_pages - assigned_extra_pages)

        marked_standard_pages = {
            region.page_number
            for region in exam.regions
            if 1 <= region.page_number <= exam.standard_page_count
        }
        expected_standard_pages = set(range(1, exam.standard_page_count + 1))
        has_missing_page_markings = not expected_standard_pages.issubset(marked_standard_pages)

        return ExamProgress(
            reading_percent=reading_percent,
            correction_percent=correction_percent,
            region_count=region_count,
            corrected_region_count=corrected_region_count,
            has_unassigned_extra_pages=has_unassigned_extra_pages,
            has_missing_page_markings=has_missing_page_markings,
        )
