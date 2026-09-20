from __future__ import annotations

from app.core.domain.models import ExamProject
from app.core.domain.student_result import StudentResult, compute_student_result


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
