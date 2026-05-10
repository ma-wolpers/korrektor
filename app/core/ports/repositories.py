from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.core.domain.models import ExamProject, RegionAssignment


class ExamRepository(Protocol):
    def list_exam_files(self) -> list[Path]:
        ...

    def load_exam(self, exam_file: Path) -> ExamProject:
        ...

    def save_exam(self, exam: ExamProject) -> Path:
        ...

    def delete_exam(self, exam_file: Path) -> None:
        ...


class ScoreRepository(Protocol):
    def save_score(
        self,
        *,
        exam: ExamProject,
        student_id: str,
        task_code: str,
        points: float,
        max_points: float,
    ) -> None:
        ...


class PdfScanRepository(Protocol):
    def scan_exam_folder(self, folder_path: Path) -> list[tuple[str, int]]:
        ...


class RegionRepository(Protocol):
    def upsert_region(self, exam: ExamProject, region: RegionAssignment) -> ExamProject:
        ...
