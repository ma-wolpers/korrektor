from pathlib import Path

import pytest

from app.adapters.bootstrap.wiring import build_gui_dependencies
from app.adapters.gui import ui_intent_controller as uic_module
from app.adapters.gui.ui_intent_controller import UiIntentController
from app.core.domain.grading_scale import SCALE_TYPE_SCHOOL_1_6, GradeThreshold, GradingScale
from app.core.domain.models import ExamProject, RegionAssignment, RegionBox, StudentExam, TaskDefinition, utc_now_iso


@pytest.fixture(autouse=True)
def _no_real_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent showerror/showinfo from opening a real (blocking) Tk dialog."""
    monkeypatch.setattr(uic_module.messagebox, "showerror", lambda *args, **kwargs: None)
    monkeypatch.setattr(uic_module.messagebox, "showinfo", lambda *args, **kwargs: None)


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


def _build_exam(exam_folder: Path) -> ExamProject:
    now = utc_now_iso()
    return ExamProject(
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
                tasks=[TaskDefinition(code="1A", name="1A", max_points=10.0)],
                assigned_area_codes=["A"],
                is_read_complete=True,
            ),
        ],
    )


def _setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[UiIntentController, ExamProject]:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    exam_folder = tmp_path / "exam"
    exam_folder.mkdir()
    deps = build_gui_dependencies(tmp_path / "repo")
    app = _FakeApp()
    controller = UiIntentController(app=app, deps=deps)
    exam = _build_exam(exam_folder)
    controller._deps.exam_repository.save_exam(exam)
    return controller, exam


def _reload(controller: UiIntentController) -> ExamProject:
    return controller._deps.exam_repository.load_exam(controller._deps.exam_repository.index_root / "exam-1.json")


def test_apply_scored_superposition_creates_personalized_content_per_student(tmp_path: Path, monkeypatch) -> None:
    controller, exam = _setup(tmp_path, monkeypatch)
    controller._deps.score_repository.save_score(exam=exam, student_id="alice", task_code="1A", points=8.0, max_points=10.0)
    controller._deps.score_repository.save_score(exam=exam, student_id="bob", task_code="1A", points=5.0, max_points=10.0)

    updated = controller.apply_scored_superposition_immediate(
        exam=exam,
        region_id="r-a",
        page_number=1,
        task_codes=["1A"],
        student_ids=["alice", "bob"],
        annotation_type="text",
        color_hex="#d62828",
        font_size=14.0,
        x=10.0,
        y=10.0,
    )

    assert updated is not None
    by_pdf = {a.student_pdf: a for a in updated.pdf_annotations}
    assert by_pdf["Alice.pdf"].content == "8"
    assert by_pdf["Bob.pdf"].content == "5"
    assert by_pdf["Alice.pdf"].sync_group_id == by_pdf["Bob.pdf"].sync_group_id
    assert by_pdf["Alice.pdf"].x == by_pdf["Bob.pdf"].x == 10.0


def test_apply_scored_superposition_is_one_undoable_action(tmp_path: Path, monkeypatch) -> None:
    controller, exam = _setup(tmp_path, monkeypatch)
    controller._deps.score_repository.save_score(exam=exam, student_id="alice", task_code="1A", points=8.0, max_points=10.0)
    controller._deps.score_repository.save_score(exam=exam, student_id="bob", task_code="1A", points=5.0, max_points=10.0)

    controller.apply_scored_superposition_immediate(
        exam=exam, region_id="r-a", page_number=1, task_codes=["1A"], student_ids=["alice", "bob"],
        annotation_type="text", color_hex="#d62828", font_size=14.0, x=10.0, y=10.0,
    )
    assert len(_reload(controller).pdf_annotations) == 2

    assert controller.undo() is True
    assert len(_reload(controller).pdf_annotations) == 0

    assert controller.redo() is True
    assert len(_reload(controller).pdf_annotations) == 2


def test_apply_scored_superposition_rejects_entirely_when_one_student_missing_points(tmp_path: Path, monkeypatch) -> None:
    controller, exam = _setup(tmp_path, monkeypatch)
    controller._deps.score_repository.save_score(exam=exam, student_id="alice", task_code="1A", points=8.0, max_points=10.0)
    # Bob has no recorded points for 1A.

    updated = controller.apply_scored_superposition_immediate(
        exam=exam, region_id="r-a", page_number=1, task_codes=["1A"], student_ids=["alice", "bob"],
        annotation_type="text", color_hex="#d62828", font_size=14.0, x=10.0, y=10.0,
    )

    assert updated is None
    assert len(_reload(controller).pdf_annotations) == 0


def test_scored_superposition_style_change_never_touches_personalized_content(tmp_path: Path, monkeypatch) -> None:
    """Meilenstein 3 invariant: sync-group style propagation must never overwrite personalized content."""
    controller, exam = _setup(tmp_path, monkeypatch)
    controller._deps.score_repository.save_score(exam=exam, student_id="alice", task_code="1A", points=8.0, max_points=10.0)
    controller._deps.score_repository.save_score(exam=exam, student_id="bob", task_code="1A", points=5.0, max_points=10.0)

    updated = controller.apply_scored_superposition_immediate(
        exam=exam, region_id="r-a", page_number=1, task_codes=["1A"], student_ids=["alice", "bob"],
        annotation_type="text", color_hex="#d62828", font_size=14.0, x=10.0, y=10.0,
    )
    assert updated is not None
    alice_annotation_id = next(a.annotation_id for a in updated.pdf_annotations if a.student_pdf == "Alice.pdf")

    resized = controller.resize_annotation_immediate(exam=updated, annotation_id=alice_annotation_id, delta=4.0)
    assert resized is not None
    by_pdf = {a.student_pdf: a for a in resized.pdf_annotations}
    assert by_pdf["Alice.pdf"].font_size == 18.0
    assert by_pdf["Bob.pdf"].font_size == 18.0
    # content stayed personalized despite the shared style change
    assert by_pdf["Alice.pdf"].content == "8"
    assert by_pdf["Bob.pdf"].content == "5"


def _assign_scale(controller: UiIntentController, exam: ExamProject) -> None:
    scale = GradingScale(
        scale_id="",
        name="Mathe 8",
        subject="Mathe",
        year="8",
        school="Musterschule",
        scale_type=SCALE_TYPE_SCHOOL_1_6,
        thresholds=[GradeThreshold(min_percent=80.0, grade_label="1"), GradeThreshold(min_percent=50.0, grade_label="2")],
    )
    saved = controller.save_grading_scale_immediate(scale=scale)
    controller.assign_grading_scale_immediate(exam=exam, scale_id=saved.scale_id)


def test_apply_grade_superposition_requires_assigned_scale(tmp_path: Path, monkeypatch) -> None:
    controller, exam = _setup(tmp_path, monkeypatch)
    controller._deps.score_repository.save_score(exam=exam, student_id="alice", task_code="1A", points=8.0, max_points=10.0)

    updated = controller.apply_grade_superposition_immediate(
        exam=exam, region_id="r-a", page_number=1, task_codes=["1A"], student_ids=["alice"],
        annotation_type="text", color_hex="#d62828", font_size=14.0, x=10.0, y=10.0,
    )

    assert updated is None


def test_apply_grade_superposition_computes_personalized_grades(tmp_path: Path, monkeypatch) -> None:
    controller, exam = _setup(tmp_path, monkeypatch)
    _assign_scale(controller, exam)
    controller._deps.score_repository.save_score(exam=exam, student_id="alice", task_code="1A", points=9.0, max_points=10.0)
    controller._deps.score_repository.save_score(exam=exam, student_id="bob", task_code="1A", points=6.0, max_points=10.0)

    updated = controller.apply_grade_superposition_immediate(
        exam=exam, region_id="r-a", page_number=1, task_codes=["1A"], student_ids=["alice", "bob"],
        annotation_type="text", color_hex="#d62828", font_size=14.0, x=10.0, y=10.0,
    )

    assert updated is not None
    by_pdf = {a.student_pdf: a for a in updated.pdf_annotations}
    assert by_pdf["Alice.pdf"].content == "1"
    assert by_pdf["Bob.pdf"].content == "2"


def test_apply_grade_superposition_rejects_entirely_when_one_student_below_lowest_threshold(tmp_path: Path, monkeypatch) -> None:
    controller, exam = _setup(tmp_path, monkeypatch)
    _assign_scale(controller, exam)
    controller._deps.score_repository.save_score(exam=exam, student_id="alice", task_code="1A", points=9.0, max_points=10.0)
    controller._deps.score_repository.save_score(exam=exam, student_id="bob", task_code="1A", points=1.0, max_points=10.0)

    updated = controller.apply_grade_superposition_immediate(
        exam=exam, region_id="r-a", page_number=1, task_codes=["1A"], student_ids=["alice", "bob"],
        annotation_type="text", color_hex="#d62828", font_size=14.0, x=10.0, y=10.0,
    )

    assert updated is None
    assert len(_reload(controller).pdf_annotations) == 0
