from __future__ import annotations

from app.core.domain.models import ExamProject
from app.core.ports.repositories import ExamRepository


class SetReadingCompleteUseCase:
    def __init__(self, exam_repo: ExamRepository) -> None:
        self._exam_repo = exam_repo

    def execute(self, *, exam: ExamProject, is_complete: bool) -> ExamProject:
        exam.is_reading_complete = is_complete
        self._exam_repo.save_exam(exam)
        return exam
