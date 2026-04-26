from __future__ import annotations

from dataclasses import dataclass

from app.core.domain.progress import ExamProgress, ProgressCalculator
from app.core.ports.repositories import ExamRepository


@dataclass(slots=True)
class ExamOverview:
    exam_id: str
    exam_name: str
    reading_percent: float
    correction_percent: float
    region_count: int
    corrected_region_count: int
    reading_complete: bool
    has_unassigned_extra_pages: bool
    has_missing_page_markings: bool


class ListExamsUseCase:
    def __init__(self, exam_repo: ExamRepository, progress_calculator: ProgressCalculator) -> None:
        self._exam_repo = exam_repo
        self._progress_calculator = progress_calculator

    def execute(self) -> list[ExamOverview]:
        items: list[ExamOverview] = []
        for exam_file in self._exam_repo.list_exam_files():
            exam = self._exam_repo.load_exam(exam_file)
            progress: ExamProgress = self._progress_calculator.compute(exam)
            items.append(
                ExamOverview(
                    exam_id=exam.exam_id,
                    exam_name=exam.exam_name,
                    reading_percent=progress.reading_percent,
                    correction_percent=progress.correction_percent,
                    region_count=progress.region_count,
                    corrected_region_count=progress.corrected_region_count,
                    reading_complete=exam.is_reading_complete,
                    has_unassigned_extra_pages=progress.has_unassigned_extra_pages,
                    has_missing_page_markings=progress.has_missing_page_markings,
                )
            )
        return sorted(items, key=lambda item: item.exam_name.lower())
