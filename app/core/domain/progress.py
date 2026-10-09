from __future__ import annotations

from dataclasses import dataclass

from app.core.domain.models import ExamProject
from app.core.domain.page_coverage import open_pages, pages_missing_markings


@dataclass(slots=True)
class ExamProgress:
    """Overview numbers of one exam (schema v2: correction progress counts tasks, not regions)."""

    reading_percent: float
    correction_percent: float
    region_count: int
    corrected_task_count: int
    total_task_count: int
    has_unassigned_extra_pages: bool
    has_missing_page_markings: bool


class ProgressCalculator:
    def compute(self, exam: ExamProject) -> ExamProgress:
        """Compute Zuschnitt/correction progress metrics for one exam.

        Zuschnitt: share of regions (Superseiten and Einzelseiten) flagged
        ``is_read_complete``. Correction: a task counts as finished when every
        student has a finished `PersonTaskCompletion` for its code - the only
        correction signal the app maintains (``RegionAssignment.is_corrected``
        is a legacy field nothing sets).
        """
        region_count = len(exam.regions)
        read_complete_count = sum(1 for region in exam.regions if region.is_read_complete)
        reading_percent = 100.0 if region_count == 0 else (read_complete_count / region_count) * 100.0

        # Einzelseiten are computed (pages without a Superseiten-Bereich, see
        # page_coverage); a page is open unless it has an Einzelseiten-Bereich or is "ohne Bewertung".
        has_unassigned_extra_pages = bool(open_pages(exam))
        has_missing_page_markings = bool(pages_missing_markings(exam))

        student_ids = {student.student_id for student in exam.students}
        finished_pairs = {
            (item.student_id, item.task_code)
            for item in exam.person_task_completions
            if item.is_finished and item.student_id.strip() and item.task_code.strip()
        }
        corrected_task_count = sum(
            1
            for task in exam.tasks
            if student_ids and all((student_id, task.code) in finished_pairs for student_id in student_ids)
        )
        total_task_count = len(exam.tasks)
        correction_percent = 100.0 if total_task_count == 0 else (corrected_task_count / total_task_count) * 100.0
        return ExamProgress(
            reading_percent=reading_percent,
            correction_percent=correction_percent,
            region_count=region_count,
            corrected_task_count=corrected_task_count,
            total_task_count=total_task_count,
            has_unassigned_extra_pages=has_unassigned_extra_pages,
            has_missing_page_markings=has_missing_page_markings,
        )
