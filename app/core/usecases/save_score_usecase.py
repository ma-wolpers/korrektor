from __future__ import annotations

from app.core.domain.models import ExamProject
from app.core.ports.repositories import ScoreRepository


class SaveScoreUseCase:
    """Store one person's points for one task - or, with ``points=None``, make the task unscored again."""

    def __init__(self, score_repo: ScoreRepository) -> None:
        self._score_repo = score_repo

    def execute(
        self,
        *,
        exam: ExamProject,
        student_id: str,
        task_code: str,
        points: float | None,
        max_points: float,
    ) -> None:
        """``points=None`` (an emptied field) deletes the stored value - never a silent 0."""
        if points is None:
            self._score_repo.delete_score(exam=exam, student_id=student_id, task_code=task_code)
            return
        self._score_repo.save_score(
            exam=exam,
            student_id=student_id,
            task_code=task_code,
            points=points,
            max_points=max_points,
        )
