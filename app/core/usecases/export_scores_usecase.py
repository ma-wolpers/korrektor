from __future__ import annotations

from pathlib import Path

from app.core.domain.models import ExamProject
from app.core.ports.repositories import ScoreExportRepository


class ExportScoresUseCase:
    def __init__(self, export_repo: ScoreExportRepository) -> None:
        self._export_repo = export_repo

    def execute(self, *, exam: ExamProject, output_csv: Path) -> None:
        self._export_repo.export_scores(exam=exam, output_csv=output_csv)
