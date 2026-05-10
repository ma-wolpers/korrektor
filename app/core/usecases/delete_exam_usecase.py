from __future__ import annotations

from pathlib import Path

from app.core.ports.repositories import ExamRepository


class DeleteExamUseCase:
    def __init__(self, exam_repo: ExamRepository) -> None:
        self._exam_repo = exam_repo

    def execute(self, *, exam_file: Path) -> None:
        self._exam_repo.delete_exam(exam_file)
