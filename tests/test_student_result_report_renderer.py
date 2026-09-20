from pathlib import Path

from app.core.domain.grading_scale import SCALE_TYPE_SCHOOL_1_6, GradeThreshold, GradingScaleSnapshot
from app.core.domain.models import TaskCategory, TaskDefinition
from app.core.domain.student_result import compute_student_result
from app.infrastructure.rendering.competency_chart_renderer import save_figure
from app.infrastructure.rendering.student_result_report_renderer import render_student_result_report


def _result():
    snapshot = GradingScaleSnapshot(
        source_scale_id="scale-1",
        name="Mathe 8",
        subject="Mathe",
        year="8",
        school="Musterschule",
        scale_type=SCALE_TYPE_SCHOOL_1_6,
        thresholds=[GradeThreshold(min_percent=80.0, grade_label="1"), GradeThreshold(min_percent=50.0, grade_label="2")],
        assigned_at="2026-09-20T10:00:00.000000Z",
    )
    return compute_student_result(
        student_id="alice",
        display_name="Alice",
        scores_by_task={"1A": 5.0, "1B": 4.0, "2A": 9.0},
        all_tasks=[
            TaskDefinition(code="1A", name="1A", max_points=5.0),
            TaskDefinition(code="1B", name="1B", max_points=5.0),
            TaskDefinition(code="2A", name="2A", max_points=10.0),
        ],
        categories=[TaskCategory(category_id="cat-geo", name="Geometrie"), TaskCategory(category_id="cat-alg", name="Algebra")],
        category_assignments={"1A": "cat-geo", "1B": "cat-geo", "2A": "cat-alg"},
        grading_scale_snapshot=snapshot,
    )


def test_render_student_result_report_radar_saves_as_png(tmp_path: Path) -> None:
    fig = render_student_result_report(_result(), chart_type="Spinnennetz", chart_scope="Pro Aufgabe")
    out_path = tmp_path / "alice.png"

    save_figure(fig, out_path)

    assert out_path.exists()
    assert out_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_render_student_result_report_bar_saves_as_pdf(tmp_path: Path) -> None:
    fig = render_student_result_report(_result(), chart_type="Balken", chart_scope="Pro Kategorie")
    out_path = tmp_path / "alice.pdf"

    save_figure(fig, out_path)

    assert out_path.exists()
    assert out_path.read_bytes().startswith(b"%PDF")


def test_render_student_result_report_saves_as_jpg(tmp_path: Path) -> None:
    fig = render_student_result_report(_result())
    out_path = tmp_path / "alice.jpg"

    save_figure(fig, out_path)

    assert out_path.exists()
    assert out_path.read_bytes().startswith(b"\xff\xd8\xff")


def test_render_student_result_report_handles_no_categories_no_grade() -> None:
    result = compute_student_result(
        student_id="bob",
        display_name="Bob",
        scores_by_task={"1A": 3.0},
        all_tasks=[TaskDefinition(code="1A", name="1A", max_points=5.0)],
        categories=[],
        category_assignments={},
        grading_scale_snapshot=None,
    )

    fig = render_student_result_report(result)

    assert fig is not None
