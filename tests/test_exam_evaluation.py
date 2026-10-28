"""Class-wide evaluation contracts: population, scored vs. 0 vs. missing, grades, class profile."""

from __future__ import annotations

import pytest

from app.core.domain.exam_evaluation import (
    AVERAGE_NO_GRADES,
    AVERAGE_NOT_NUMERIC,
    REASON_BELOW_LOWEST,
    REASON_INCOMPLETE,
    REASON_NO_REQUIRED,
    REASON_NO_SCALE,
    category_class_averages,
    compute_exam_evaluation,
    grade_distribution,
    points_histogram,
    task_rows,
)
from app.core.domain.grading_scale import SCALE_TYPE_POINTS_0_15, SCALE_TYPE_SCHOOL_1_6, GradeThreshold, GradingScaleSnapshot
from app.core.domain.models import PersonTaskCompletion, TaskCategory, TaskDefinition
from app.core.domain.student_result import compute_student_result

TASKS = [TaskDefinition("1A", "1A", 2.0), TaskDefinition("1B", "1B", 8.0)]
CATEGORIES = [TaskCategory("cat-a", "Algebra"), TaskCategory("cat-b", "Beweise")]


def _snapshot(labels_min=(("1", 80.0), ("2", 50.0), ("3", 20.0)), scale_type=SCALE_TYPE_SCHOOL_1_6) -> GradingScaleSnapshot:
    return GradingScaleSnapshot(
        "s", "Mathe", "Mathe", "8", "Schule", scale_type,
        thresholds=[GradeThreshold(min_percent=minimum, grade_label=label) for label, minimum in labels_min],
    )


def _results(scores: dict[str, dict[str, float]], snapshot=None, assignments=None):
    return [
        compute_student_result(
            student_id=sid, display_name=sid.title(), scores_by_task=values, all_tasks=TASKS, categories=CATEGORIES,
            category_assignments=assignments or {}, grading_scale_snapshot=snapshot,
        )
        for sid, values in scores.items()
    ]


def test_empty_exam_and_no_scores():
    empty = compute_exam_evaluation([], TASKS, [], None)
    assert [stat.total_count for stat in empty.task_statistics] == [0, 0]
    unscored = compute_exam_evaluation(_results({"anna": {}, "ben": {}}), TASKS, [], None)
    first = unscored.task_statistics[0]
    assert (first.scored_count, first.total_count, first.average, first.minimum, first.maximum) == (0, 2, None, None, None)


def test_zero_points_count_as_scored_missing_does_not():
    results = _results({"anna": {"1A": 0.0}, "ben": {}, "cara": {"1A": 2.0}})
    stat = compute_exam_evaluation(results, TASKS, [], None).task_statistics[0]
    assert (stat.scored_count, stat.total_count) == (2, 3)
    assert (stat.average, stat.minimum, stat.maximum, stat.average_percent) == (1.0, 0.0, 2.0, 50.0)
    rows = task_rows(results, set(), "1A")
    assert [row.achieved_points for row in rows] == [0.0, None, 2.0]
    assert [row.percent for row in rows] == [0.0, None, 100.0]
    assert points_histogram(rows) == [("0", 1), ("2", 1)]


def test_finished_and_scored_are_independent():
    results = _results({"anna": {"1A": 1.0}, "ben": {}})
    completions = [PersonTaskCompletion("ben", "1A"), PersonTaskCompletion("anna", "1B", is_finished=False)]
    evaluation = compute_exam_evaluation(results, TASKS, completions, None)
    assert evaluation.task_statistics[0].finished_count == 1 and evaluation.task_statistics[0].scored_count == 1
    assert evaluation.task_statistics[1].finished_count == 0
    rows = task_rows(results, {("ben", "1A")}, "1A")
    assert [(row.student_id, row.finished) for row in rows] == [("anna", False), ("ben", True)]


def test_grade_reasons_in_order_and_rows_with_zero_counts():
    snapshot = _snapshot()
    results = _results({"full": {"1A": 2.0, "1B": 8.0}, "part": {"1A": 2.0}, "low": {"1A": 0.0, "1B": 1.0}}, snapshot)
    evaluation = compute_exam_evaluation(results, TASKS, [], snapshot)
    assert evaluation.grades.rows == [("1", 1), ("2", 0), ("3", 0)]
    assert evaluation.grades.ungraded == [(REASON_INCOMPLETE, 1), (REASON_BELOW_LOWEST, 1)]
    assert evaluation.grades.graded_count + sum(count for _r, count in evaluation.grades.ungraded) == 3
    assert evaluation.grade_reasons == {"part": REASON_INCOMPLETE, "low": REASON_BELOW_LOWEST}


def test_without_scale_rows_are_empty_and_everybody_has_the_reason():
    results = _results({"anna": {"1A": 2.0, "1B": 8.0}, "ben": {}})
    grades = grade_distribution(results, None)
    assert grades.rows == [] and grades.ungraded == [(REASON_NO_SCALE, 2)]
    assert grades.average_grade is None


@pytest.mark.parametrize(
    ("labels", "scale_type", "expected", "note"),
    [
        ((("1", 80.0), ("2", 50.0), ("3", 0.0)), SCALE_TYPE_SCHOOL_1_6, 1.5, ""),
        ((("15", 95.0), ("10", 50.0), ("0", 0.0)), SCALE_TYPE_POINTS_0_15, 12.5, ""),
        ((("1,5", 80.0), ("2", 50.0), ("3", 0.0)), SCALE_TYPE_SCHOOL_1_6, 1.8, ""),
        ((("1+", 80.0), ("2", 50.0), ("3", 0.0)), SCALE_TYPE_SCHOOL_1_6, None, AVERAGE_NOT_NUMERIC),
        ((("sehr gut", 80.0), ("gut", 50.0), ("befriedigend", 0.0)), SCALE_TYPE_SCHOOL_1_6, None, AVERAGE_NOT_NUMERIC),
        ((("1", 80.0), ("2", 50.0), ("3", 0.0)), "eigene_skala", None, AVERAGE_NOT_NUMERIC),
    ],
)
def test_average_grade_only_for_plain_numeric_scales(labels, scale_type, expected, note):
    snapshot = _snapshot(labels, scale_type)
    results = _results({"top": {"1A": 2.0, "1B": 8.0}, "mid": {"1A": 1.0, "1B": 5.0}}, snapshot)
    grades = grade_distribution(results, snapshot)
    assert grades.average_grade == expected and grades.average_note == note


def test_numeric_scale_without_graded_persons():
    snapshot = _snapshot()
    grades = grade_distribution(_results({"anna": {}}, snapshot), snapshot)
    assert grades.average_grade is None and grades.average_note == AVERAGE_NO_GRADES


def test_class_profile_averages_person_percentages_not_pooled_points():
    """Anna 1A 2/2 = 100 % (only Algebra), Ben 1A 0/2 + ... - the per-person mean, not pooled points."""
    assignments = {"1A": "cat-a", "1B": "cat-b"}
    results = _results({"anna": {"1A": 2.0, "1B": 8.0}, "ben": {"1A": 0.0, "1B": 2.0}, "cara": {"1A": 1.0}}, None, assignments)
    profile = dict((name, (percent, n)) for name, percent, n in category_class_averages(results))
    assert profile["Algebra"] == (pytest.approx(50.0), 3)  # (100 + 0 + 50) / 3
    assert profile["Beweise"] == (pytest.approx(62.5), 2)  # cara incomplete -> left out: (100 + 25) / 2


def test_class_profile_weighting_with_different_maxima():
    """Category of two tasks with different maxima: person-weighted, points-weighted within the person."""
    assignments = {"1A": "cat-a", "1B": "cat-a"}
    results = _results({"anna": {"1A": 2.0, "1B": 0.0}, "ben": {"1A": 0.0, "1B": 8.0}}, None, assignments)
    (name, percent, n), = category_class_averages(results)
    assert (name, n) == ("Algebra", 2) and percent == pytest.approx((20.0 + 80.0) / 2)


def test_only_bonus_tasks_name_their_own_reason_instead_of_below_lowest():
    snapshot = _snapshot()
    bonus_only = [TaskDefinition("9A", "9A", 2.0, is_bonus=True)]
    results = [
        compute_student_result(
            student_id=sid, display_name=sid.title(), scores_by_task=values, all_tasks=bonus_only, categories=[],
            category_assignments={}, grading_scale_snapshot=snapshot,
        )
        for sid, values in {"anna": {"9A": 2.0}, "ben": {}}.items()
    ]
    grades = grade_distribution(results, snapshot)
    assert grades.ungraded == [(REASON_INCOMPLETE, 1), (REASON_NO_REQUIRED, 1)]
