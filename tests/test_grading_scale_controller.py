from pathlib import Path

import pytest

from app.adapters.bootstrap.wiring import build_gui_dependencies
from app.adapters.gui import ui_intent_controller as uic_module
from app.adapters.gui.ui_intent_controller import UiIntentController
from app.core.domain.grading_scale import (
    SCALE_TYPE_SCHOOL_1_6,
    STATUS_ACTIVE,
    STATUS_ARCHIVED,
    GradeThreshold,
    GradingScale,
)
from app.core.domain.models import ExamProject, StudentExam, utc_now_iso


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


def _setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[UiIntentController, ExamProject]:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    exam_folder = tmp_path / "exam"
    exam_folder.mkdir()
    deps = build_gui_dependencies(tmp_path / "repo")
    app = _FakeApp()
    controller = UiIntentController(app=app, deps=deps)
    now = utc_now_iso()
    exam = ExamProject(
        exam_id="exam-1",
        exam_name="Mathe Klausur",
        folder_path=str(exam_folder),
        created_at=now,
        updated_at=now,
        standard_page_count=1,
        students=[StudentExam(student_id="alice", display_name="Alice", pdf_filename="Alice.pdf", page_count=1)],
    )
    controller._deps.exam_repository.save_exam(exam)
    return controller, exam


def _scale() -> GradingScale:
    return GradingScale(
        scale_id="",
        name="Mathe 8",
        subject="Mathe",
        year="8",
        school="Musterschule",
        scale_type=SCALE_TYPE_SCHOOL_1_6,
        thresholds=[GradeThreshold(min_percent=80.0, grade_label="1")],
    )


def test_save_grading_scale_immediate_assigns_id_when_new(tmp_path: Path, monkeypatch) -> None:
    controller, _exam = _setup(tmp_path, monkeypatch)

    saved = controller.save_grading_scale_immediate(scale=_scale())

    assert saved.scale_id
    assert controller.list_grading_scales() == [saved]


def test_save_grading_scale_immediate_updates_existing(tmp_path: Path, monkeypatch) -> None:
    controller, _exam = _setup(tmp_path, monkeypatch)
    saved = controller.save_grading_scale_immediate(scale=_scale())

    saved.name = "Mathe 8 (neu)"
    controller.save_grading_scale_immediate(scale=saved)

    scales = controller.list_grading_scales()
    assert len(scales) == 1
    assert scales[0].name == "Mathe 8 (neu)"


def test_list_active_grading_scales_excludes_archived(tmp_path: Path, monkeypatch) -> None:
    controller, _exam = _setup(tmp_path, monkeypatch)
    saved = controller.save_grading_scale_immediate(scale=_scale())

    assert controller.list_active_grading_scales() == [saved]
    controller.archive_grading_scale_immediate(scale_id=saved.scale_id)
    assert controller.list_active_grading_scales() == []
    assert controller.list_grading_scales()[0].status == STATUS_ARCHIVED


def test_reactivate_grading_scale_immediate(tmp_path: Path, monkeypatch) -> None:
    controller, _exam = _setup(tmp_path, monkeypatch)
    saved = controller.save_grading_scale_immediate(scale=_scale())
    controller.archive_grading_scale_immediate(scale_id=saved.scale_id)

    controller.reactivate_grading_scale_immediate(scale_id=saved.scale_id)

    assert controller.list_grading_scales()[0].status == STATUS_ACTIVE


def test_delete_grading_scale_immediate_succeeds_when_never_used(tmp_path: Path, monkeypatch) -> None:
    controller, _exam = _setup(tmp_path, monkeypatch)
    saved = controller.save_grading_scale_immediate(scale=_scale())

    assert controller.delete_grading_scale_immediate(scale_id=saved.scale_id) is True
    assert controller.list_grading_scales() == []


def test_delete_grading_scale_immediate_rejected_once_used(tmp_path: Path, monkeypatch) -> None:
    controller, exam = _setup(tmp_path, monkeypatch)
    saved = controller.save_grading_scale_immediate(scale=_scale())
    controller.assign_grading_scale_immediate(exam=exam, scale_id=saved.scale_id)

    assert controller.delete_grading_scale_immediate(scale_id=saved.scale_id) is False
    assert len(controller.list_grading_scales()) == 1


def test_assign_grading_scale_immediate_sets_snapshot_and_records_usage(tmp_path: Path, monkeypatch) -> None:
    controller, exam = _setup(tmp_path, monkeypatch)
    saved = controller.save_grading_scale_immediate(scale=_scale())

    updated = controller.assign_grading_scale_immediate(exam=exam, scale_id=saved.scale_id)

    assert updated is not None
    assert updated.grading_scale_snapshot is not None
    assert updated.grading_scale_snapshot.source_scale_id == saved.scale_id
    assert updated.grading_scale_snapshot.name == saved.name

    usage = controller.list_grading_scale_usage(saved.scale_id)
    assert len(usage) == 1
    assert usage[0].exam_id == "exam-1"


def test_assign_grading_scale_immediate_is_undoable(tmp_path: Path, monkeypatch) -> None:
    controller, exam = _setup(tmp_path, monkeypatch)
    saved = controller.save_grading_scale_immediate(scale=_scale())

    controller.assign_grading_scale_immediate(exam=exam, scale_id=saved.scale_id)
    assert controller.undo() is True

    reloaded = controller._deps.exam_repository.load_exam(
        controller._deps.exam_repository.index_root / "exam-1.json"
    )
    assert reloaded.grading_scale_snapshot is None
    # The usage record itself is an append-only fact and survives the undo.
    assert len(controller.list_grading_scale_usage(saved.scale_id)) == 1


def test_assign_grading_scale_immediate_returns_none_for_unknown_scale(tmp_path: Path, monkeypatch) -> None:
    controller, exam = _setup(tmp_path, monkeypatch)

    assert controller.assign_grading_scale_immediate(exam=exam, scale_id="missing") is None
