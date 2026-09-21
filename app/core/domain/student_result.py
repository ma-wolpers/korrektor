from __future__ import annotations

from dataclasses import dataclass, field

from app.core.domain.grading import GradingError, resolve_grade
from app.core.domain.grading_scale import GradingScaleSnapshot
from app.core.domain.models import TaskCategory, TaskDefinition


@dataclass(slots=True)
class TaskResult:
    """One task's result for one student. `achieved_points is None` means "not yet scored" - never 0."""

    task_code: str
    max_points: float
    achieved_points: float | None
    category_name: str
    """The task's category name, resolved once here so renderers/GUI never re-derive it.

    Always a concrete display string, never `None` - mirrors `CategoryResult.name`'s
    "Unkategorisiert" convention for tasks with no (or a stray/unknown) category assignment.
    """


@dataclass(slots=True)
class CategoryResult:
    """One category's aggregated result for one student.

    `category_id` is `None` for the synthetic "Unkategorisiert" bucket
    (tasks with no category assignment) - only present in
    `StudentResult.category_results` when at least one such task exists.
    `achieved_points is None` if any task in this category is unscored -
    a category total is only meaningful once every task in it has a value,
    same "no silent 0" rule as `TaskResult`.
    """

    category_id: str | None
    name: str
    max_points: float
    achieved_points: float | None


@dataclass(slots=True)
class StudentResult:
    """Full per-student Auswertung: overall, per task, per category, and (if possible) a grade."""

    student_id: str
    display_name: str
    task_results: list[TaskResult] = field(default_factory=list)
    category_results: list[CategoryResult] = field(default_factory=list)
    total_max_points: float = 0.0
    total_achieved_points: float | None = None
    grade_label: str | None = None
    grade_percentage: float | None = None


def task_competency_percentages(result: StudentResult) -> list[tuple[str, float]]:
    """Normalized (0-100) competency per task, as `(task_code, percent)` pairs.

    Only scored tasks with a positive `max_points` are included - an
    unscored task has no competency value yet (not 0%), and a
    zero-`max_points` task cannot be normalized. Normalizing lets
    tasks/Kategorien of different `max_points` be compared on the same
    scale (Meilenstein 6 der Korrektor-Wunschliste) - this stays a Domain-
    level computation; the matplotlib rendering layer (Infrastructure)
    only ever receives these finished percentages, it never computes any
    fachliche Werte itself.
    """
    return [
        (task.task_code, (task.achieved_points / task.max_points) * 100.0)
        for task in result.task_results
        if task.achieved_points is not None and task.max_points > 0
    ]


def category_competency_percentages(result: StudentResult) -> list[tuple[str, float]]:
    """Normalized (0-100) competency per category, as `(name, percent)` pairs. See `task_competency_percentages`."""
    return [
        (category.name, (category.achieved_points / category.max_points) * 100.0)
        for category in result.category_results
        if category.achieved_points is not None and category.max_points > 0
    ]


def _summarize(task_results: list[TaskResult]) -> tuple[float, float | None]:
    max_points = sum(task.max_points for task in task_results)
    if any(task.achieved_points is None for task in task_results):
        return max_points, None
    return max_points, sum(task.achieved_points for task in task_results)  # type: ignore[misc]


def compute_student_result(
    *,
    student_id: str,
    display_name: str,
    scores_by_task: dict[str, float],
    all_tasks: list[TaskDefinition],
    categories: list[TaskCategory],
    category_assignments: dict[str, str],
    grading_scale_snapshot: GradingScaleSnapshot | None,
) -> StudentResult:
    """Assemble one student's complete Auswertung from already-loaded, primitive inputs.

    Deliberately takes plain data (not `ExamProject`) like `score_filter.py`'s
    functions - callers (usecase/controller) resolve these from the exam
    once and can reuse them across all students instead of re-deriving
    per call. A task without a recorded score stays visibly "not yet
    scored" (`achieved_points=None`) throughout - it is never coerced to
    0, all the way up to `total_achieved_points` and the grade: an
    incomplete result shows as incomplete, not as a possibly-misleading
    partial percentage. The grade is computed only when a Notenschluessel
    is assigned, every task has a value, and `resolve_grade` does not
    raise `GradingError` (e.g. below the lowest threshold) - any of those
    missing simply leaves `grade_label`/`grade_percentage` as `None`,
    never a silent fallback grade.
    """
    category_name_by_id = {category.category_id: category.name for category in categories}
    task_results = [
        TaskResult(
            task_code=task.code,
            max_points=task.max_points,
            achieved_points=scores_by_task.get(task.code),
            category_name=category_name_by_id.get(category_assignments.get(task.code), "Unkategorisiert"),
        )
        for task in all_tasks
    ]

    buckets: dict[str | None, list[TaskResult]] = {}
    for task_result in task_results:
        category_id = category_assignments.get(task_result.task_code)
        buckets.setdefault(category_id, []).append(task_result)

    category_results: list[CategoryResult] = []
    for category in categories:
        bucket = buckets.get(category.category_id)
        if not bucket:
            continue
        max_points, achieved_points = _summarize(bucket)
        category_results.append(
            CategoryResult(category_id=category.category_id, name=category.name, max_points=max_points, achieved_points=achieved_points)
        )
    uncategorized_bucket = buckets.get(None)
    if uncategorized_bucket:
        max_points, achieved_points = _summarize(uncategorized_bucket)
        category_results.append(
            CategoryResult(category_id=None, name="Unkategorisiert", max_points=max_points, achieved_points=achieved_points)
        )

    total_max_points, total_achieved_points = _summarize(task_results)

    grade_label: str | None = None
    grade_percentage: float | None = None
    if grading_scale_snapshot is not None and total_achieved_points is not None and total_max_points > 0:
        try:
            result = resolve_grade(total_achieved_points, total_max_points, grading_scale_snapshot)
        except GradingError:
            pass
        else:
            grade_label = result.grade_label
            grade_percentage = result.percentage

    return StudentResult(
        student_id=student_id,
        display_name=display_name,
        task_results=task_results,
        category_results=category_results,
        total_max_points=total_max_points,
        total_achieved_points=total_achieved_points,
        grade_label=grade_label,
        grade_percentage=grade_percentage,
    )
