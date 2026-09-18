import pytest

from app.core.domain.score_filter import (
    compute_student_value,
    filter_matching_student_ids,
    matches_condition,
)


def test_compute_student_value_single_task() -> None:
    assert compute_student_value({"1a": 3.0, "1b": 2.0}, ["1a"]) == 3.0


def test_compute_student_value_sums_multiple_tasks() -> None:
    assert compute_student_value({"1a": 3.0, "1b": 2.0}, ["1a", "1b"]) == 5.0


def test_compute_student_value_returns_none_when_a_task_is_missing() -> None:
    # Sum semantics: one missing component excludes the student entirely,
    # rather than silently summing only the tasks that are present.
    assert compute_student_value({"1a": 3.0}, ["1a", "1b"]) is None


def test_compute_student_value_returns_none_for_missing_single_task() -> None:
    assert compute_student_value({}, ["1a"]) is None


@pytest.mark.parametrize(
    "operator, value, target, expected",
    [
        ("<", 2.0, 3.0, True),
        ("<", 3.0, 3.0, False),
        ("<=", 3.0, 3.0, True),
        (">=", 3.0, 3.0, True),
        (">", 3.0, 2.0, True),
        (">", 2.0, 3.0, False),
        ("==", 3.0, 3.0, True),
        ("==", 3.0, 3.1, False),
    ],
)
def test_matches_condition(operator, value, target, expected) -> None:
    assert matches_condition(value, operator, target) is expected


def test_matches_condition_equality_uses_points_precision_not_float_epsilon() -> None:
    # 0.1 + 0.2 != 0.3 in raw float - must still match at 2-decimal precision,
    # the precision points are actually persisted at (CsvScoreRepository).
    assert matches_condition(0.1 + 0.2, "==", 0.3) is True


def test_matches_condition_rejects_unknown_operator() -> None:
    with pytest.raises(ValueError):
        matches_condition(1.0, "!=", 1.0)  # type: ignore[arg-type]


def test_filter_matching_student_ids_excludes_none_values() -> None:
    values = {"alice": 5.0, "bob": None, "carla": 2.0}
    assert filter_matching_student_ids(values, "<", 4.0) == ["carla"]


def test_filter_matching_student_ids_returns_empty_list_for_no_matches() -> None:
    values = {"alice": 5.0, "bob": 6.0}
    assert filter_matching_student_ids(values, "<", 1.0) == []
