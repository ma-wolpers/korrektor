"""Class-wide evaluation of one exam: per-task statistics, grade distribution, class competency profile.

Pure functions on already-computed ``StudentResult``s (``student_result.compute_student_result``
is the single source of the per-person rules); nothing here re-derives a person's total,
category or grade differently.

Contracts (see ``docs/ARCHITEKTUR.md`` "Auswertung"):

* **Population** is always every person of the exam (``exam.students``); every person has
  a PDF. ``total_count`` = number of persons.
* **Scored** means a value exists in the score CSV (``TaskResult.achieved_points is not None``);
  **0 points are scored**. A missing value is "unscored" and never becomes 0.
* **Finished** ("fertig korrigiert") is a separate fact (``PersonTaskCompletion``); a task
  can be scored but not finished and vice versa.
* Averages, minimum and maximum run over scored values only; with none they are ``None``.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

from app.core.domain.grading_scale import SCALE_TYPE_POINTS_1_15, SCALE_TYPE_SCHOOL_1_6, GradingScaleSnapshot
from app.core.domain.models import PersonTaskCompletion, TaskDefinition
from app.core.domain.student_result import StudentResult, category_competency_percentages

REASON_NO_SCALE = "kein Notenschlüssel"
REASON_INCOMPLETE = "unvollständig bewertet"
REASON_NO_REQUIRED = "keine Pflichtaufgaben (nur Bonus)"
REASON_BELOW_LOWEST = "unter der niedrigsten Stufe"
AVERAGE_NOT_NUMERIC = "Notenlabels nicht rein numerisch"
AVERAGE_NO_GRADES = "noch keine Noten"
_NUMERIC_LABEL = re.compile(r"^\d+([.,]\d+)?$")
_NUMERIC_SCALE_TYPES = frozenset({SCALE_TYPE_SCHOOL_1_6, SCALE_TYPE_POINTS_1_15})


@dataclass(frozen=True)
class TaskStatistics:
    """Statistics of one task over all persons (see module contracts)."""

    task_code: str
    max_points: float
    scored_count: int
    total_count: int
    finished_count: int
    average: float | None
    average_percent: float | None
    minimum: float | None
    maximum: float | None


@dataclass(frozen=True)
class GradeDistribution:
    """Grade counts in scale order plus why persons have no grade.

    ``rows``: every threshold label of the snapshot (highest ``min_percent`` first), also
    with 0 persons; empty without a snapshot. ``ungraded``: ``(reason, count)`` for the
    reasons ``REASON_NO_SCALE``, ``REASON_INCOMPLETE``, ``REASON_NO_REQUIRED``, ``REASON_BELOW_LOWEST`` (only
    non-zero ones, in that order). ``graded_count + sum(ungraded) == total_count``.
    ``average_grade`` is set only for numeric scales (see ``grade_distribution``);
    otherwise ``average_note`` says why.
    """

    rows: list[tuple[str, int]] = field(default_factory=list)
    ungraded: list[tuple[str, int]] = field(default_factory=list)
    graded_count: int = 0
    average_grade: float | None = None
    average_note: str = ""


@dataclass(frozen=True)
class TaskRow:
    """One person's line in the per-task view."""

    student_id: str
    display_name: str
    achieved_points: float | None
    max_points: float
    percent: float | None
    finished: bool


@dataclass(frozen=True)
class ExamEvaluation:
    """Everything the overview shows, computed once."""

    results: list[StudentResult]
    task_statistics: list[TaskStatistics]
    grades: GradeDistribution
    category_averages: list[tuple[str, float, int]]
    grade_reasons: dict[str, str]


def finished_pairs(completions: Sequence[PersonTaskCompletion]) -> set[tuple[str, str]]:
    """``{(student_id, task_code)}`` of every finished person/task."""
    return {(item.student_id, item.task_code) for item in completions if item.is_finished}


def task_statistics(
    results: Sequence[StudentResult], tasks: Sequence[TaskDefinition], finished: set[tuple[str, str]]
) -> list[TaskStatistics]:
    """One ``TaskStatistics`` per task, in the order of ``tasks`` (``exam.tasks``)."""
    statistics = []
    for task in tasks:
        values = [
            item.achieved_points
            for result in results
            for item in result.task_results
            if item.task_code == task.code and item.achieved_points is not None
        ]
        average = sum(values) / len(values) if values else None
        statistics.append(
            TaskStatistics(
                task_code=task.code,
                max_points=float(task.max_points),
                scored_count=len(values),
                total_count=len(results),
                finished_count=sum(1 for result in results if (result.student_id, task.code) in finished),
                average=average,
                average_percent=(average / task.max_points * 100.0) if average is not None and task.max_points > 0 else None,
                minimum=min(values) if values else None,
                maximum=max(values) if values else None,
            )
        )
    return statistics


def grade_reason(result: StudentResult, snapshot: GradingScaleSnapshot | None) -> str | None:
    """Why ``result`` has no grade (checked in this order), or ``None`` if it has one."""
    if result.grade_label is not None:
        return None
    if snapshot is None:
        return REASON_NO_SCALE
    if result.total_achieved_points is None:
        return REASON_INCOMPLETE
    if result.total_max_points <= 0:
        return REASON_NO_REQUIRED
    return REASON_BELOW_LOWEST


def grade_distribution(results: Sequence[StudentResult], snapshot: GradingScaleSnapshot | None) -> GradeDistribution:
    """Grade counts, reasons for missing grades and - for numeric scales only - the average grade.

    The average exists only if the scale type is "Schulnoten 1-6" or "Punktnoten 1-15"
    **and** every threshold label is a plain number (``^\\d+([.,]\\d+)?$``, comma = point)
    **and** at least one person is graded. No further guessing (e.g. "2+" is not 2).
    """
    reasons = Counter(reason for result in results if (reason := grade_reason(result, snapshot)) is not None)
    ungraded = [(reason, reasons[reason]) for reason in (REASON_NO_SCALE, REASON_INCOMPLETE, REASON_NO_REQUIRED, REASON_BELOW_LOWEST) if reasons[reason]]
    graded = [result.grade_label for result in results if result.grade_label is not None]
    if snapshot is None:
        return GradeDistribution(ungraded=ungraded, average_note=AVERAGE_NO_GRADES)
    counts = Counter(graded)
    ordered = sorted(snapshot.thresholds, key=lambda item: item.min_percent, reverse=True)
    rows = [(threshold.grade_label, counts[threshold.grade_label]) for threshold in ordered]
    labels = [threshold.grade_label.strip() for threshold in ordered]
    numeric = snapshot.scale_type in _NUMERIC_SCALE_TYPES and all(_NUMERIC_LABEL.match(label) for label in labels)
    if not numeric:
        return GradeDistribution(rows, ungraded, len(graded), None, AVERAGE_NOT_NUMERIC)
    if not graded:
        return GradeDistribution(rows, ungraded, 0, None, AVERAGE_NO_GRADES)
    average = sum(float(label.strip().replace(",", ".")) for label in graded) / len(graded)
    return GradeDistribution(rows, ungraded, len(graded), round(average, 1), "")


def category_class_averages(results: Sequence[StudentResult]) -> list[tuple[str, float, int]]:
    """Class competency profile: ``(category, mean percent, n)``.

    The mean of each person's category percentage (``category_competency_percentages``) -
    the same weighting as the per-person view: every person counts equally, within a
    person the points weigh. Persons whose category is incomplete are left out (``n``
    says how many count); categories with ``n == 0`` are omitted. Order of first
    appearance (= category order of ``compute_student_result``).
    """
    collected: dict[str, list[float]] = {}
    for result in results:
        for name, percent in category_competency_percentages(result):
            collected.setdefault(name, []).append(percent)
    return [(name, sum(values) / len(values), len(values)) for name, values in collected.items()]


def task_rows(results: Sequence[StudentResult], finished: set[tuple[str, str]], task_code: str) -> list[TaskRow]:
    """Every person's line for ``task_code`` in the order of ``results`` (= ``exam.students``)."""
    rows = []
    for result in results:
        item = next((task for task in result.task_results if task.task_code == task_code), None)
        if item is None:
            continue
        percent = (item.achieved_points / item.max_points * 100.0) if item.achieved_points is not None and item.max_points > 0 else None
        rows.append(
            TaskRow(result.student_id, result.display_name, item.achieved_points, item.max_points, percent,
                    (result.student_id, task_code) in finished)
        )
    return rows


def points_histogram(rows: Sequence[TaskRow]) -> list[tuple[str, int]]:
    """How many persons reached which points (scored only), ascending: ``[("0", 2), ("1,5", 3), …]``."""
    counts = Counter(row.achieved_points for row in rows if row.achieved_points is not None)
    return [(f"{points:g}".replace(".", ","), counts[points]) for points in sorted(counts)]


def compute_exam_evaluation(
    results: Sequence[StudentResult],
    tasks: Sequence[TaskDefinition],
    completions: Sequence[PersonTaskCompletion],
    snapshot: GradingScaleSnapshot | None,
) -> ExamEvaluation:
    """Bundle the overview data.

    Args:
        results: One ``StudentResult`` per person, in ``exam.students`` order.
        tasks: ``exam.tasks`` (natural order, as in the correction view).
        completions: ``exam.person_task_completions``.
        snapshot: ``exam.grading_scale_snapshot`` - the same snapshot ``compute_student_result``
            graded with; gives the order of the grade rows and the scale type.
    """
    finished = finished_pairs(completions)
    return ExamEvaluation(
        results=list(results),
        task_statistics=task_statistics(results, tasks, finished),
        grades=grade_distribution(results, snapshot),
        category_averages=category_class_averages(results),
        grade_reasons={result.student_id: reason for result in results if (reason := grade_reason(result, snapshot))},
    )
