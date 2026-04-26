from __future__ import annotations

from app.core.domain.models import ExamProject
from app.core.ports.repositories import ScoreRepository


class SaveScoreUseCase:
    def __init__(self, score_repo: ScoreRepository) -> None:
        self._score_repo = score_repo

    def execute(
        self,
        *,
        exam: ExamProject,
        student_id: str,
        task_code: str,
        points: float,
        max_points: float,
    ) -> None:
        self._score_repo.save_score(
            exam=exam,
            student_id=student_id,
            task_code=task_code,
            points=points,
            max_points=max_points,
        )
