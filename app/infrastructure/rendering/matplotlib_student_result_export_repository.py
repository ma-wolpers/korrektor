from __future__ import annotations

from pathlib import Path

from app.core.domain.student_result import StudentResult
from app.infrastructure.rendering.competency_chart_renderer import save_figure
from app.infrastructure.rendering.student_result_report_renderer import render_student_result_report


class MatplotlibStudentResultExportRepository:
    """`StudentResultExportRepository` implementation backed by the matplotlib report renderer.

    Thin adapter: composes the full-page report (`render_student_result_report`)
    and writes it to `output_path` (`save_figure`, format inferred from the
    file extension) - no fachliche Logik of its own, matching the existing
    `CsvScoreExportRepository`/`ExportScoresUseCase` pattern for the CSV
    export path.
    """

    def export_student_result(
        self, *, result: StudentResult, chart_type: str, chart_scope: str, output_path: Path
    ) -> None:
        figure = render_student_result_report(result, chart_type=chart_type, chart_scope=chart_scope)
        save_figure(figure, output_path)
