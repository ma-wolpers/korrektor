"""Read-only class evaluation queries for the "Auswertung" window (no mutation, no HistoryAction).

Resolves the plain inputs of ``app/core/domain/exam_evaluation.py`` and
``app/core/domain/symbol_usage.py`` from an ``ExamProject`` plus its already-loaded scores.
Per-person results come from ``compute_student_result_for_exam`` - the one definition of
a person's totals, categories and grade - so the class overview can never disagree with
the per-person view.
"""

from __future__ import annotations

from app.core.domain.exam_evaluation import ExamEvaluation, compute_exam_evaluation
from app.core.domain.models import ExamProject
from app.core.domain.symbol_usage import SymbolUsage, symbols_for_task, used_symbols


class UiIntentControllerExamEvaluationMixin:
    """Class-wide evaluation and symbol usage of the current exam."""

    def compute_exam_evaluation_for_exam(self, *, exam: ExamProject, scores: dict[str, dict[str, float]]) -> ExamEvaluation:
        """Overview data for ``exam``: one ``StudentResult`` per person (``exam.students`` order) plus statistics.

        Args:
            exam: The open exam.
            scores: ``load_scores_for_exam`` result, loaded once per window refresh.
        """
        results = []
        for student in exam.students:
            result = self.compute_student_result_for_exam(exam=exam, student_id=student.student_id, scores=scores)
            if result is not None:
                results.append(result)
        return compute_exam_evaluation(results, exam.tasks, exam.person_task_completions, exam.grading_scale_snapshot)

    def used_symbols_for_exam(self, *, exam: ExamProject) -> list[SymbolUsage]:
        """Every symbol used in at least one current submission (see ``symbol_usage.used_symbols``)."""
        return used_symbols(
            exam.pdf_annotations,
            [student.pdf_filename for student in exam.students],
            [task.code for task in exam.tasks],
        )

    def frequent_symbols_for_task(self, *, exam: ExamProject, task_code: str, limit: int = 5) -> list[SymbolUsage]:
        """The ``limit`` most frequent symbols of ``task_code`` (see ``symbol_usage.symbols_for_task``)."""
        return symbols_for_task(exam.pdf_annotations, [student.pdf_filename for student in exam.students], task_code, limit)
