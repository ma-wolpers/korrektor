from __future__ import annotations

from app.core.domain.models import ExamProject, RegionAssignment
from app.core.ports.repositories import RegionRepository


class InMemoryRegionRepository(RegionRepository):
    def upsert_region(self, exam: ExamProject, region: RegionAssignment) -> ExamProject:
        replaced = False
        for index, item in enumerate(exam.regions):
            if item.region_id == region.region_id:
                exam.regions[index] = region
                replaced = True
                break
        if not replaced:
            exam.regions.append(region)
        return exam
