from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.core.domain.progress import ExamProgress, ProgressCalculator
from app.core.domain.validation import ExamStructureError
from app.core.ports.repositories import ExamRepository


@dataclass(slots=True)
class ExamOverview:
    exam_id: str
    exam_name: str
    exam_file: Path
    reading_percent: float
    correction_percent: float
    region_count: int
    corrected_region_count: int
    reading_complete: bool
    has_unassigned_extra_pages: bool
    has_missing_page_markings: bool


@dataclass(slots=True)
class ExamLoadError:
    """One exam file that failed to load, so it can be skipped instead of
    aborting the whole overview (see `ListExamsUseCase.execute`)."""

    exam_file: Path
    message: str


class ListExamsUseCase:
    def __init__(self, exam_repo: ExamRepository, progress_calculator: ProgressCalculator) -> None:
        self._exam_repo = exam_repo
        self._progress_calculator = progress_calculator

    def execute(self) -> tuple[list[ExamOverview], list[ExamLoadError]]:
        """Load every exam file once and compute its overview row.

        Carries `exam_file` on each result so callers (e.g. the GUI overview
        refresh) can resolve the source path without loading every exam file
        a second time. A file that fails to load (unsupported legacy schema,
        or an `ExamStructureError` from `validate_regions`) is skipped and
        reported in the second return value instead of aborting the whole
        listing — one broken exam must not hide every other, valid one.
        """
        items: list[ExamOverview] = []
        errors: list[ExamLoadError] = []
        for exam_file in self._exam_repo.list_exam_files():
            try:
                exam = self._exam_repo.load_exam(exam_file)
            except (ValueError, ExamStructureError) as exc:
                errors.append(ExamLoadError(exam_file=exam_file, message=str(exc)))
                continue
            progress: ExamProgress = self._progress_calculator.compute(exam)
            items.append(
                ExamOverview(
                    exam_id=exam.exam_id,
                    exam_name=exam.exam_name,
                    exam_file=exam_file,
                    reading_percent=progress.reading_percent,
                    correction_percent=progress.correction_percent,
                    region_count=progress.region_count,
                    corrected_region_count=progress.corrected_region_count,
                    reading_complete=exam.is_reading_complete,
                    has_unassigned_extra_pages=progress.has_unassigned_extra_pages,
                    has_missing_page_markings=progress.has_missing_page_markings,
                )
            )
        return sorted(items, key=lambda item: item.exam_name.lower()), errors
