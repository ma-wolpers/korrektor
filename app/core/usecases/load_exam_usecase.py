from __future__ import annotations

from pathlib import Path

from app.core.domain.models import ExamProject
from app.core.ports.repositories import ExamRepository


class LoadExamUseCase:
    def __init__(self, exam_repo: ExamRepository) -> None:
        self._exam_repo = exam_repo

    def execute(self, *, exam_file: Path) -> ExamProject:
        return self._exam_repo.load_exam(exam_file)
