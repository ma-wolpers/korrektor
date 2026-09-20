from pathlib import Path

import pytest

from app.adapters.bootstrap.wiring import build_gui_dependencies
from app.adapters.gui.ui_intent_controller import UiIntentController
from app.core.domain.models import (
    ExamProject,
    PdfAnnotation,
    RegionAssignment,
    RegionBox,
    StudentExam,
    TaskDefinition,
    utc_now_iso,
)


class _FakeApp:
    def __init__(self) -> None:
        self.status_messages: list[str] = []

    def set_status(self, text: str) -> None:
        self.status_messages.append(text)

    def invalidate_doc_cache(self, pdf_filenames) -> None:
        pass

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
                tasks=[TaskDefinition(code="1a", name="1a", max_points=5.0)],
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


def _reload(controller: UiIntentController) -> ExamProject:
    return controller._deps.exam_repository.load_exam(controller._deps.exam_repository.index_root / "exam-1.json")


def _annotation(**overrides) -> PdfAnnotation:
    base = dict(
        annotation_id="ann-1",
        student_pdf="Alice.pdf",
        page_number=1,
        annotation_type="symbol",
        content="✓",
        color_hex="#d62828",
        x=10.0,
        y=20.0,
        task_code="1a",
        region_id="r-a",
        font_size=20.0,
        rotation_deg=0.0,
    )
    base.update(overrides)
    return PdfAnnotation(**base)


def test_place_annotation_immediate_persists_and_is_undoable(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)

    updated = controller.place_annotation_immediate(exam=exam, annotation=_annotation())
    assert updated is not None
    assert len(_reload(controller).pdf_annotations) == 1

    assert controller.undo() is True
    assert len(_reload(controller).pdf_annotations) == 0

    assert controller.redo() is True
    assert len(_reload(controller).pdf_annotations) == 1


def test_delete_annotation_immediate_removes_whole_sync_group_as_one_action(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)
    exam.pdf_annotations = [
        _annotation(annotation_id="ann-1", student_pdf="Alice.pdf", sync_group_id="sg-1"),
        _annotation(annotation_id="ann-2", student_pdf="Bob.pdf", sync_group_id="sg-1"),
    ]
    controller._deps.exam_repository.save_exam(exam)

    updated = controller.delete_annotation_immediate(exam=exam, annotation_id="ann-1")
    assert updated is not None
    assert len(_reload(controller).pdf_annotations) == 0

    assert controller.undo() is True
    reloaded = _reload(controller)
    assert len(reloaded.pdf_annotations) == 2
    assert {a.annotation_id for a in reloaded.pdf_annotations} == {"ann-1", "ann-2"}


def test_resize_annotation_immediate_resizes_whole_sync_group_as_one_history_action(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)
    exam.pdf_annotations = [
        _annotation(annotation_id="ann-1", student_pdf="Alice.pdf", sync_group_id="sg-1", font_size=20.0),
        _annotation(annotation_id="ann-2", student_pdf="Bob.pdf", sync_group_id="sg-1", font_size=20.0),
    ]
    controller._deps.exam_repository.save_exam(exam)

    updated = controller.resize_annotation_immediate(exam=exam, annotation_id="ann-1", delta=4.0)
    assert updated is not None
    assert all(a.font_size == 24.0 for a in updated.pdf_annotations)

    # One undo reverts both members together - the group resize is one HistoryAction.
    assert controller.undo() is True
    reloaded = _reload(controller)
    assert all(a.font_size == 20.0 for a in reloaded.pdf_annotations)


def test_rotate_annotation_immediate_is_undoable(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)
    exam.pdf_annotations = [_annotation(rotation_deg=0.0)]
    controller._deps.exam_repository.save_exam(exam)

    updated = controller.rotate_annotation_immediate(exam=exam, annotation_id="ann-1", next_rotation_deg=90.0)
    assert updated is not None
    assert updated.pdf_annotations[0].rotation_deg == 90.0

    assert controller.undo() is True
    assert _reload(controller).pdf_annotations[0].rotation_deg == 0.0


def test_recolor_annotation_immediate_is_undoable(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)
    exam.pdf_annotations = [_annotation(color_hex="#d62828")]
    controller._deps.exam_repository.save_exam(exam)

    updated = controller.recolor_annotation_immediate(exam=exam, annotation_id="ann-1", color_hex="#2a9d8f")
    assert updated is not None
    assert updated.pdf_annotations[0].color_hex == "#2a9d8f"

    assert controller.undo() is True
    assert _reload(controller).pdf_annotations[0].color_hex == "#d62828"


def test_commit_annotation_move_immediate_uses_drag_start_snapshot_not_current_state(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)
    exam.pdf_annotations = [_annotation(x=10.0, y=20.0)]
    controller._deps.exam_repository.save_exam(exam)

    # Snapshot taken at drag start, before the live-preview mutation below -
    # this is the exact ordering that fixes the Meilenstein-0.2 bug (a
    # post-mutation "before" snapshot makes undo a no-op).
    before_payload = exam.to_dict()
    exam.pdf_annotations[0].x = 99.0
    exam.pdf_annotations[0].y = 88.0

    updated = controller.commit_annotation_move_immediate(exam=exam, before_payload=before_payload)
    assert updated is not None
    assert (updated.pdf_annotations[0].x, updated.pdf_annotations[0].y) == (99.0, 88.0)

    assert controller.undo() is True
    reloaded = _reload(controller)
    assert (reloaded.pdf_annotations[0].x, reloaded.pdf_annotations[0].y) == (10.0, 20.0)


def test_enable_and_disable_annotation_sync_immediate_are_each_undoable(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)
    exam.pdf_annotations = [_annotation(student_pdf="Alice.pdf")]
    controller._deps.exam_repository.save_exam(exam)

    updated = controller.enable_annotation_sync_immediate(
        exam=exam, annotation_id="ann-1", other_student_pdfs=["Bob.pdf"]
    )
    assert updated is not None
    assert len(updated.pdf_annotations) == 2
    sync_group_id = updated.pdf_annotations[0].sync_group_id
    assert sync_group_id
    assert all(a.sync_group_id == sync_group_id for a in updated.pdf_annotations)

    assert controller.undo() is True
    reloaded = _reload(controller)
    assert len(reloaded.pdf_annotations) == 1
    assert reloaded.pdf_annotations[0].sync_group_id == ""

    assert controller.redo() is True
    reloaded = _reload(controller)
    assert len(reloaded.pdf_annotations) == 2

    updated2 = controller.disable_annotation_sync_immediate(exam=reloaded, annotation_id="ann-1")
    assert updated2 is not None
    assert len(updated2.pdf_annotations) == 1
    assert updated2.pdf_annotations[0].sync_group_id == ""

    assert controller.undo() is True
    reloaded = _reload(controller)
    assert len(reloaded.pdf_annotations) == 2


def test_annotation_mutation_rolls_back_in_memory_state_when_save_fails(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)
    exam.pdf_annotations = [_annotation(font_size=20.0)]
    controller._deps.exam_repository.save_exam(exam)

    def _boom(*_args, **_kwargs):
        raise OSError("disk full")

    controller._deps.exam_repository.save_exam = _boom  # type: ignore[method-assign]

    result = controller.resize_annotation_immediate(exam=exam, annotation_id="ann-1", delta=4.0)

    assert result is None
    # The in-memory mutation was rolled back - not left at the failed new value.
    assert exam.pdf_annotations[0].font_size == 20.0
    assert controller.can_undo() is False
