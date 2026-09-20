from __future__ import annotations

from pathlib import Path

from app.core.domain.student_result import StudentResult
from app.core.ports.repositories import StudentResultExportRepository


class ExportStudentResultUseCase:
    def __init__(self, export_repo: StudentResultExportRepository) -> None:
        self._export_repo = export_repo

    def execute(self, *, result: StudentResult, chart_type: str, chart_scope: str, output_path: Path) -> None:
        self._export_repo.export_student_result(
            result=result, chart_type=chart_type, chart_scope=chart_scope, output_path=output_path
        )
