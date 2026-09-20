from __future__ import annotations

from pathlib import Path

from app.core.domain.models import ExamProject
from app.core.domain.student_result import StudentResult, compute_student_result
from app.infrastructure.repositories.file_utils import sanitize_filename_stem


class UiIntentControllerStudentResultMixin:
    """Read-only Auswertungs-Abfrage (Meilenstein 5): kein Exam-Mutator, keine HistoryAction.

    Resolves the plain-data inputs `compute_student_result` needs
    (`app/core/domain/student_result.py`) from an `ExamProject` plus its
    already-loaded scores, once per call - callers computing results for
    several/all students should load `scores` once (`load_scores_for_exam`)
    and pass it in rather than re-reading the CSV per student.
    """

    def compute_student_result_for_exam(
        self, *, exam: ExamProject, student_id: str, scores: dict[str, dict[str, float]]
    ) -> StudentResult | None:
        student = next((item for item in exam.students if item.student_id == student_id), None)
        if student is None:
            return None
        all_tasks = [task for region in exam.regions for task in region.tasks]
        return compute_student_result(
            student_id=student.student_id,
            display_name=student.display_name,
            scores_by_task=scores.get(student_id, {}),
            all_tasks=all_tasks,
            categories=exam.task_categories,
            category_assignments=exam.task_category_assignments,
            grading_scale_snapshot=exam.grading_scale_snapshot,
        )

    def export_student_results(
        self,
        *,
        exam: ExamProject,
        student_ids: list[str],
        scores: dict[str, dict[str, float]],
        chart_type: str,
        chart_scope: str,
        output_dir: Path,
        file_extension: str,
    ) -> tuple[list[str], list[str]]:
        """Export one report file per selected student (Meilenstein 7); never raises on a per-file failure.

        Returns `(exported_display_names, failed_display_names)` so the
        caller can report a precise summary. One student's export failing
        (I/O error, or an unsanitizable empty display name) does not stop
        the others - unlike the Superposition bulk actions, this is a
        read-only export with independent per-file outputs, not a single
        shared mutation where partial application would be misleading.
        """
        exported: list[str] = []
        failed: list[str] = []
        for student_id in student_ids:
            result = self.compute_student_result_for_exam(exam=exam, student_id=student_id, scores=scores)
            if result is None:
                continue
            stem = sanitize_filename_stem(result.display_name, replace_spaces_with=None)
            if stem is None:
                failed.append(result.display_name)
                continue
            output_path = output_dir / f"{stem}.{file_extension}"
            try:
                self._deps.export_student_result_usecase.execute(
                    result=result, chart_type=chart_type, chart_scope=chart_scope, output_path=output_path
                )
            except Exception:
                failed.append(result.display_name)
            else:
                exported.append(result.display_name)
        return exported, failed
