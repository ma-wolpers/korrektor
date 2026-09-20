from pathlib import Path

import pytest

from app.adapters.bootstrap.wiring import build_gui_dependencies
from app.adapters.gui import ui_intent_controller as uic_module
from app.adapters.gui.ui_intent_controller import UiIntentController
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
        students=[StudentExam(student_id="alice", display_name="Alice", pdf_filename="Alice.pdf", page_count=1)],
        regions=[
            RegionAssignment(
                region_id="r-a",
                student_pdf="",
                page_number=1,
                box=RegionBox(0, 0, 100, 100),
                tasks=[TaskDefinition(code="1A", name="1A", max_points=5.0)],
                assigned_area_codes=["A"],
                is_read_complete=True,
            ),
        ],
    )


def _setup(tmp_path: Path) -> tuple[UiIntentController, ExamProject]:
    exam_folder = tmp_path / "exam"
    exam_folder.mkdir()
    deps = build_gui_dependencies(tmp_path / "app_data")
    app = _FakeApp()
    controller = UiIntentController(app=app, deps=deps)
    exam = _build_exam(exam_folder)
    controller._deps.exam_repository.save_exam(exam)
    return controller, exam


def test_upsert_region_immediate_allows_max_points_change_when_never_scored(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)

    updated = controller.upsert_region_immediate(
        exam=exam,
        student_pdf="",
        page_number=1,
        box=(0, 0, 100, 100),
        task_specs=[("1A", 8.0)],
        area_codes=["A"],
        region_id="r-a",
    )

    assert updated is not None
    assert updated.regions[0].tasks[0].max_points == 8.0


def test_upsert_region_immediate_rejects_max_points_change_once_task_is_scored(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)
    controller._deps.score_repository.save_score(exam=exam, student_id="alice", task_code="1A", points=3.0, max_points=5.0)

    updated = controller.upsert_region_immediate(
        exam=exam,
        student_pdf="",
        page_number=1,
        box=(0, 0, 100, 100),
        task_specs=[("1A", 8.0)],
        area_codes=["A"],
        region_id="r-a",
    )

    assert updated is None
    reloaded = controller._deps.exam_repository.load_exam(
        controller._deps.exam_repository.index_root / "exam-1.json"
    )
    assert reloaded.regions[0].tasks[0].max_points == 5.0


def test_upsert_region_immediate_allows_unrelated_task_edits_when_another_task_is_scored(tmp_path: Path) -> None:
    """Only the specific task_code(s) whose max_points actually changed are protected."""
    controller, exam = _setup(tmp_path)
    controller._deps.score_repository.save_score(exam=exam, student_id="alice", task_code="1A", points=3.0, max_points=5.0)

    updated = controller.upsert_region_immediate(
        exam=exam,
        student_pdf="",
        page_number=1,
        box=(0, 0, 100, 100),
        task_specs=[("1A", 5.0), ("1B", 3.0)],
        area_codes=["A"],
        region_id="r-a",
    )

    assert updated is not None
    codes = {task.code: task.max_points for task in updated.regions[0].tasks}
    assert codes == {"1A": 5.0, "1B": 3.0}


def test_upsert_region_immediate_allows_max_points_on_brand_new_region(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)

    updated = controller.upsert_region_immediate(
        exam=exam,
        student_pdf="",
        page_number=1,
        box=(0, 0, 50, 50),
        task_specs=[("2A", 10.0)],
        area_codes=["B"],
        region_id=None,
    )

    assert updated is not None
    assert len(updated.regions) == 2
