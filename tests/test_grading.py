import pytest

from app.core.domain.grading import GradingError, resolve_grade
from app.core.domain.grading_scale import SCALE_TYPE_SCHOOL_1_6, GradeThreshold, GradingScale, GradingScaleSnapshot
from app.core.domain.models import ExamProject, utc_now_iso


def _snapshot(*thresholds: tuple[float, str]) -> GradingScaleSnapshot:
    return GradingScaleSnapshot(
        source_scale_id="scale-1",
        name="Mathe 8",
        subject="Mathe",
        year="8",
        school="Musterschule",
        scale_type="schulnoten_1_6",
        thresholds=[GradeThreshold(min_percent=percent, grade_label=label) for percent, label in thresholds],
        assigned_at="2026-09-19T10:00:00.000000Z",
    )


def test_resolve_grade_picks_matching_threshold() -> None:
    snapshot = _snapshot((80.0, "1"), (65.0, "2"), (50.0, "3"))

    result = resolve_grade(70.0, 100.0, snapshot)

    assert result.grade_label == "2"
    assert result.percentage == 70.0


def test_resolve_grade_exact_boundary_wins_the_higher_threshold() -> None:
    """percentage == min_percent counts as reaching that (higher) threshold, not the next-lower one."""
    snapshot = _snapshot((80.0, "1"), (65.0, "2"))

    result = resolve_grade(80.0, 100.0, snapshot)

    assert result.grade_label == "1"


def test_resolve_grade_is_independent_of_threshold_order_in_the_list() -> None:
    snapshot = _snapshot((50.0, "3"), (80.0, "1"), (65.0, "2"))

    result = resolve_grade(90.0, 100.0, snapshot)

    assert result.grade_label == "1"


def test_resolve_grade_below_lowest_threshold_raises() -> None:
    snapshot = _snapshot((80.0, "1"), (65.0, "2"))

    with pytest.raises(GradingError):
        resolve_grade(10.0, 100.0, snapshot)


def test_resolve_grade_rejects_non_positive_max_points() -> None:
    snapshot = _snapshot((80.0, "1"))

    with pytest.raises(GradingError):
        resolve_grade(5.0, 0.0, snapshot)


def test_resolve_grade_rounds_percentage_to_two_decimals() -> None:
    snapshot = _snapshot((33.33, "1"))

    result = resolve_grade(1.0, 3.0, snapshot)

    assert result.percentage == 33.33
    assert result.grade_label == "1"


def test_grade_snapshot_end_to_end_is_immune_to_later_global_scale_edits() -> None:
    """Meilenstein 2.6: exercise the full Variante-B semantics, not just the data structures.

    1. Exam receives a snapshot from a global scale.
    2. A grade is computed for a student.
    3. The global scale is edited afterwards (a threshold moved).
    4. Re-evaluating the same exam still yields the original grade.
    """
    now = utc_now_iso()
    global_scale = GradingScale(
        scale_id="scale-1",
        name="Mathe 8",
        subject="Mathe",
        year="8",
        school="Musterschule",
        scale_type=SCALE_TYPE_SCHOOL_1_6,
        thresholds=[GradeThreshold(min_percent=80.0, grade_label="1"), GradeThreshold(min_percent=65.0, grade_label="2")],
    )

    exam = ExamProject(
        exam_id="exam-1",
        exam_name="Mathe Klausur",
        folder_path="/exams/mathe",
        created_at=now,
        updated_at=now,
        standard_page_count=1,
        grading_scale_snapshot=global_scale.to_snapshot(assigned_at=now),
    )

    first_result = resolve_grade(70.0, 100.0, exam.grading_scale_snapshot)
    assert first_result.grade_label == "2"

    # Edit the global template after the fact: raise the "2" threshold above 70%.
    global_scale.thresholds[1].min_percent = 75.0

    second_result = resolve_grade(70.0, 100.0, exam.grading_scale_snapshot)
    assert second_result.grade_label == "2"
    assert second_result.percentage == first_result.percentage

    # Also survives a full to_dict()/from_dict() round trip (the real persistence path).
    reloaded_exam = ExamProject.from_dict(exam.to_dict())
    third_result = resolve_grade(70.0, 100.0, reloaded_exam.grading_scale_snapshot)
    assert third_result.grade_label == "2"
