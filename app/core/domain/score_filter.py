from __future__ import annotations

from typing import Literal, Sequence

FilterOperator = Literal["<", "<=", "==", ">=", ">"]

# Points are persisted with 2 decimal places (CsvScoreRepository.save_score:
# f"{points:.2f}") - this is the system's actual points precision, so "=="
# rounds both sides to it instead of using an arbitrary epsilon.
_POINTS_PRECISION = 2


def compute_student_value(points_by_task: dict[str, float], task_codes: Sequence[str]) -> float | None:
    """Resolve one student's filter value: a single task's points, or their sum.

    Returns `None` (never 0) if any of `task_codes` has no recorded points
    for this student - a missing component must exclude the student from
    the filter, not be silently treated as a zero score.
    """
    values: list[float] = []
    for task_code in task_codes:
        value = points_by_task.get(task_code)
        if value is None:
            return None
        values.append(value)
    return sum(values) if values else None


def matches_condition(value: float, operator: FilterOperator, target: float) -> bool:
    """Evaluate one comparison, at the system's actual points precision for "=="."""
    if operator == "==":
        return round(value, _POINTS_PRECISION) == round(target, _POINTS_PRECISION)
    if operator == "<":
        return value < target
    if operator == "<=":
        return value <= target
    if operator == ">=":
        return value >= target
    if operator == ">":
        return value > target
    raise ValueError(f"Unbekannter Operator: {operator}")


def filter_matching_student_ids(
    values_by_student: dict[str, float | None],
    operator: FilterOperator,
    target: float,
) -> list[str]:
    """Return the student_ids whose value satisfies the condition.

    Students with a `None` value (see `compute_student_value`) are always
    excluded, never coerced to 0. This is also the operation the UI must use
    to check "does this filter value have >= 1 match?" before proceeding -
    there is deliberately no separate "list all matchable values" API that
    would conflate value discovery with match-existence checking.
    """
    return [
        student_id
        for student_id, value in values_by_student.items()
        if value is not None and matches_condition(value, operator, target)
    ]
