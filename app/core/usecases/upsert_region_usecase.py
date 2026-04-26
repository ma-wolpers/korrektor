from __future__ import annotations

from app.core.domain.models import ExamProject, RegionAssignment
from app.core.ports.repositories import ExamRepository, RegionRepository


class UpsertRegionUseCase:
    def __init__(self, exam_repo: ExamRepository, region_repo: RegionRepository) -> None:
        self._exam_repo = exam_repo
        self._region_repo = region_repo

    def execute(self, *, exam: ExamProject, region: RegionAssignment) -> ExamProject:
        updated = self._region_repo.upsert_region(exam, region)
        self._exam_repo.save_exam(updated)
        return updated
