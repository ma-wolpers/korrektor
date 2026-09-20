from pathlib import Path

from app.adapters.bootstrap.wiring import build_gui_dependencies
from app.adapters.gui.ui_intent_controller import UiIntentController
from app.core.domain.models import ExamProject, RegionAssignment, RegionBox, StudentExam, TaskDefinition, utc_now_iso


class _FakeApp:
    def __init__(self) -> None:
        self.status_messages: list[str] = []

    def set_status(self, text: str) -> None:
        self.status_messages.append(text)

    def render_overview_rows(self, rows) -> None:
        pass

    def sync_current_exam_from_repository(self) -> None:
        pass

    def refresh_exam_content_in_place(self) -> None:
        pass


def _setup(tmp_path: Path) -> tuple[UiIntentController, ExamProject]:
    exam_folder = tmp_path / "exam"
    exam_folder.mkdir()
    deps = build_gui_dependencies(tmp_path / "app_data")
    app = _FakeApp()
    controller = UiIntentController(app=app, deps=deps)
    now = utc_now_iso()
    exam = ExamProject(
        exam_id="exam-1",
        exam_name="Mathe",
        folder_path=str(exam_folder),
        created_at=now,
        updated_at=now,
        standard_page_count=1,
        students=[
            StudentExam(student_id="alice", display_name="Alice", pdf_filename="Alice.pdf", page_count=1),
            StudentExam(student_id="bob", display_name="Bob", pdf_filename="Bob.pdf", page_count=1),
        ],
        regions=[
            RegionAssignment(
                region_id="r-a",
                student_pdf="",
                page_number=1,
                box=RegionBox(0, 0, 100, 100),
                tasks=[TaskDefinition(code="1A", name="1A", max_points=5.0), TaskDefinition(code="1B", name="1B", max_points=5.0)],
                assigned_area_codes=["A"],
                is_read_complete=True,
            ),
        ],
    )
    controller._deps.exam_repository.save_exam(exam)
    return controller, exam


def test_compute_student_result_for_exam_resolves_from_real_scores(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)
    controller._deps.score_repository.save_score(exam=exam, student_id="alice", task_code="1A", points=4.0, max_points=5.0)
    controller._deps.score_repository.save_score(exam=exam, student_id="alice", task_code="1B", points=3.0, max_points=5.0)
    scores = controller.load_scores_for_exam(exam=exam)

    result = controller.compute_student_result_for_exam(exam=exam, student_id="alice", scores=scores)

    assert result is not None
    assert result.display_name == "Alice"
    assert result.total_achieved_points == 7.0
    assert result.total_max_points == 10.0


def test_compute_student_result_for_exam_returns_none_for_unknown_student(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)
    scores = controller.load_scores_for_exam(exam=exam)

    assert controller.compute_student_result_for_exam(exam=exam, student_id="missing", scores=scores) is None


def test_compute_student_result_for_exam_missing_scores_stay_none(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)
    scores = controller.load_scores_for_exam(exam=exam)

    result = controller.compute_student_result_for_exam(exam=exam, student_id="bob", scores=scores)

    assert result is not None
    assert result.total_achieved_points is None
