from app.core.domain.grading_scale import SCALE_TYPE_SCHOOL_1_6, GradeThreshold, GradingScaleSnapshot
from app.core.domain.models import TaskCategory, TaskDefinition
from app.core.domain.student_result import (
    category_competency_percentages,
    compute_student_result,
    task_competency_percentages,
)


def _tasks() -> list[TaskDefinition]:
    return [
        TaskDefinition(code="1A", name="1A", max_points=5.0),
        TaskDefinition(code="1B", name="1B", max_points=5.0),
        TaskDefinition(code="2A", name="2A", max_points=10.0),
    ]


def _categories() -> list[TaskCategory]:
    return [TaskCategory(category_id="cat-geo", name="Geometrie"), TaskCategory(category_id="cat-alg", name="Algebra")]


def _snapshot() -> GradingScaleSnapshot:
    return GradingScaleSnapshot(
        source_scale_id="scale-1",
        name="Mathe 8",
        subject="Mathe",
        year="8",
        school="Musterschule",
        scale_type=SCALE_TYPE_SCHOOL_1_6,
        thresholds=[GradeThreshold(min_percent=80.0, grade_label="1"), GradeThreshold(min_percent=50.0, grade_label="2")],
        assigned_at="2026-09-20T10:00:00.000000Z",
    )


def test_compute_student_result_full_scores_and_grade() -> None:
    result = compute_student_result(
        student_id="alice",
        display_name="Alice",
        scores_by_task={"1A": 5.0, "1B": 4.0, "2A": 9.0},
        all_tasks=_tasks(),
        categories=_categories(),
        category_assignments={"1A": "cat-geo", "1B": "cat-geo", "2A": "cat-alg"},
        grading_scale_snapshot=_snapshot(),
    )

    assert result.total_max_points == 20.0
    assert result.total_achieved_points == 18.0
    assert result.grade_label == "1"
    assert result.grade_percentage == 90.0

    by_category = {c.name: c for c in result.category_results}
    assert by_category["Geometrie"].achieved_points == 9.0
    assert by_category["Geometrie"].max_points == 10.0
    assert by_category["Algebra"].achieved_points == 9.0
    assert by_category["Algebra"].max_points == 10.0

    category_name_by_task = {t.task_code: t.category_name for t in result.task_results}
    assert category_name_by_task["1A"] == "Geometrie"
    assert category_name_by_task["1B"] == "Geometrie"
    assert category_name_by_task["2A"] == "Algebra"


def test_task_result_category_name_falls_back_to_unkategorisiert() -> None:
    """A task with no assignment, and one assigned to a stray/unknown category id, both fall back."""
    result = compute_student_result(
        student_id="bob",
        display_name="Bob",
        scores_by_task={"1A": 5.0, "1B": 5.0},
        all_tasks=[TaskDefinition(code="1A", name="1A", max_points=5.0), TaskDefinition(code="1B", name="1B", max_points=5.0)],
        categories=_categories(),
        category_assignments={"1B": "cat-unknown"},  # "1A" has no entry at all
        grading_scale_snapshot=None,
    )

    category_name_by_task = {t.task_code: t.category_name for t in result.task_results}
    assert category_name_by_task["1A"] == "Unkategorisiert"
    assert category_name_by_task["1B"] == "Unkategorisiert"


def test_compute_student_result_missing_score_keeps_totals_none_not_zero() -> None:
    result = compute_student_result(
        student_id="alice",
        display_name="Alice",
        scores_by_task={"1A": 5.0, "1B": 4.0},  # 2A not scored
        all_tasks=_tasks(),
        categories=_categories(),
        category_assignments={"1A": "cat-geo", "1B": "cat-geo", "2A": "cat-alg"},
        grading_scale_snapshot=_snapshot(),
    )

    assert result.total_achieved_points is None
    assert result.grade_label is None
    task_by_code = {t.task_code: t for t in result.task_results}
    assert task_by_code["2A"].achieved_points is None
    by_category = {c.name: c for c in result.category_results}
    assert by_category["Geometrie"].achieved_points == 9.0  # fully scored category still resolves
    assert by_category["Algebra"].achieved_points is None  # its only task is unscored


def test_compute_student_result_without_grading_scale_has_no_grade() -> None:
    result = compute_student_result(
        student_id="alice",
        display_name="Alice",
        scores_by_task={"1A": 5.0, "1B": 5.0, "2A": 10.0},
        all_tasks=_tasks(),
        categories=[],
        category_assignments={},
        grading_scale_snapshot=None,
    )

    assert result.grade_label is None
    assert result.total_achieved_points == 20.0


def test_compute_student_result_below_lowest_threshold_has_no_grade() -> None:
    result = compute_student_result(
        student_id="alice",
        display_name="Alice",
        scores_by_task={"1A": 0.0, "1B": 0.0, "2A": 0.0},
        all_tasks=_tasks(),
        categories=[],
        category_assignments={},
        grading_scale_snapshot=_snapshot(),
    )

    assert result.total_achieved_points == 0.0
    assert result.grade_label is None


def test_compute_student_result_unassigned_tasks_form_uncategorized_bucket() -> None:
    result = compute_student_result(
        student_id="alice",
        display_name="Alice",
        scores_by_task={"1A": 3.0, "1B": 2.0, "2A": 7.0},
        all_tasks=_tasks(),
        categories=_categories(),
        category_assignments={"1A": "cat-geo"},  # 1B, 2A unassigned
        grading_scale_snapshot=None,
    )

    names = {c.name for c in result.category_results}
    assert "Unkategorisiert" in names
    uncategorized = next(c for c in result.category_results if c.name == "Unkategorisiert")
    assert uncategorized.achieved_points == 9.0
    assert uncategorized.max_points == 15.0


def test_task_competency_percentages_normalizes_and_skips_unscored() -> None:
    result = compute_student_result(
        student_id="alice",
        display_name="Alice",
        scores_by_task={"1A": 5.0, "1B": 2.5},  # 2A unscored
        all_tasks=_tasks(),
        categories=[],
        category_assignments={},
        grading_scale_snapshot=None,
    )

    percentages = dict(task_competency_percentages(result))

    assert percentages["1A"] == 100.0
    assert percentages["1B"] == 50.0
    assert "2A" not in percentages


def test_category_competency_percentages_normalizes_and_skips_incomplete() -> None:
    result = compute_student_result(
        student_id="alice",
        display_name="Alice",
        scores_by_task={"1A": 5.0, "1B": 5.0},  # 2A unscored -> Algebra bucket incomplete
        all_tasks=_tasks(),
        categories=_categories(),
        category_assignments={"1A": "cat-geo", "1B": "cat-geo", "2A": "cat-alg"},
        grading_scale_snapshot=None,
    )

    percentages = dict(category_competency_percentages(result))

    assert percentages["Geometrie"] == 100.0
    assert "Algebra" not in percentages


def test_compute_student_result_omits_empty_categories() -> None:
    """A category with no tasks assigned to it (an empty category is a valid state) doesn't appear in results."""
    result = compute_student_result(
        student_id="alice",
        display_name="Alice",
        scores_by_task={"1A": 5.0, "1B": 5.0, "2A": 10.0},
        all_tasks=_tasks(),
        categories=_categories(),
        category_assignments={"1A": "cat-geo", "1B": "cat-geo", "2A": "cat-geo"},
        grading_scale_snapshot=None,
    )

    names = {c.name for c in result.category_results}
    assert names == {"Geometrie"}


def _bonus_tasks() -> list[TaskDefinition]:
    return _tasks() + [TaskDefinition(code="3A", name="3A", max_points=4.0, is_bonus=True)]


def _bonus_result(scores: dict[str, float], assignments: dict[str, str] | None = None):
    return compute_student_result(
        student_id="alice",
        display_name="Alice",
        scores_by_task=scores,
        all_tasks=_bonus_tasks(),
        categories=_categories(),
        category_assignments=assignments if assignments is not None else {"1A": "cat-geo", "1B": "cat-geo", "2A": "cat-alg", "3A": "cat-geo"},
        grading_scale_snapshot=_snapshot(),
    )


def test_bonus_task_adds_to_achieved_points_but_not_to_the_maximum() -> None:
    result = _bonus_result({"1A": 5.0, "1B": 0.0, "2A": 5.0, "3A": 4.0})

    assert result.total_max_points == 20.0
    assert result.total_achieved_points == 14.0
    assert result.grade_label == "2" and result.grade_percentage == 70.0
    assert [task.is_bonus for task in result.task_results] == [False, False, False, True]


def test_bonus_allows_more_than_100_percent_and_reaches_the_highest_grade() -> None:
    result = _bonus_result({"1A": 5.0, "1B": 5.0, "2A": 10.0, "3A": 2.0})

    assert (result.total_achieved_points, result.total_max_points) == (22.0, 20.0)
    assert result.grade_label == "1" and result.grade_percentage == 110.0


def test_unscored_bonus_task_leaves_total_and_grade_open() -> None:
    result = _bonus_result({"1A": 5.0, "1B": 5.0, "2A": 10.0})

    assert result.total_achieved_points is None and result.grade_label is None
    geometry = next(category for category in result.category_results if category.name == "Geometrie")
    assert geometry.achieved_points is None


def test_category_with_bonus_may_exceed_100_percent_and_a_bonus_only_category_has_no_percentage() -> None:
    result = _bonus_result(
        {"1A": 5.0, "1B": 5.0, "2A": 10.0, "3A": 4.0}, assignments={"1A": "cat-geo", "1B": "cat-geo", "2A": "cat-alg", "3A": "cat-geo"}
    )
    geometry = next(category for category in result.category_results if category.name == "Geometrie")
    assert (geometry.achieved_points, geometry.max_points) == (14.0, 10.0)
    assert dict(category_competency_percentages(result))["Geometrie"] == 140.0

    only_bonus = _bonus_result({"1A": 5.0, "1B": 5.0, "2A": 10.0, "3A": 4.0}, assignments={"3A": "cat-alg", "1A": "cat-geo"})
    algebra = next(category for category in only_bonus.category_results if category.name == "Algebra")
    assert (algebra.achieved_points, algebra.max_points) == (4.0, 0.0)
    assert "Algebra" not in dict(category_competency_percentages(only_bonus))


def test_exam_with_only_bonus_tasks_has_no_grade() -> None:
    result = compute_student_result(
        student_id="alice",
        display_name="Alice",
        scores_by_task={"3A": 4.0},
        all_tasks=[TaskDefinition(code="3A", name="3A", max_points=4.0, is_bonus=True)],
        categories=[],
        category_assignments={},
        grading_scale_snapshot=_snapshot(),
    )

    assert (result.total_achieved_points, result.total_max_points) == (4.0, 0.0)
    assert result.grade_label is None
