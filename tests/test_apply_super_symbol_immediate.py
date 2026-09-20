from pathlib import Path

import pytest

from app.adapters.bootstrap.wiring import build_gui_dependencies
from app.adapters.gui import ui_intent_controller as uic_module
from app.adapters.gui.ui_intent_controller import UiIntentController
from app.core.domain.models import ExamProject, RegionAssignment, RegionBox, StudentExam, TaskDefinition, utc_now_iso


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
            StudentExam(student_id="carla", display_name="Carla", pdf_filename="Carla.pdf", page_count=1),
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


def test_apply_super_symbol_immediate_creates_one_annotation_per_matched_student(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)

    updated = controller.apply_super_symbol_immediate(
        exam=exam,
        region_id="r-a",
        page_number=1,
        matched_student_ids=["alice", "carla"],
        annotation_type="symbol",
        content="✓",
        color_hex="#d62828",
        font_size=20.0,
        x=12.0,
        y=34.0,
    )

    assert updated is not None
    assert len(updated.pdf_annotations) == 2
    by_pdf = {a.student_pdf: a for a in updated.pdf_annotations}
    assert set(by_pdf.keys()) == {"Alice.pdf", "Carla.pdf"}
    assert by_pdf["Alice.pdf"].x == 12.0
    assert by_pdf["Alice.pdf"].y == 34.0
    assert by_pdf["Alice.pdf"].region_id == "r-a"
    # One shared sync_group_id ties all Supersymbol annotations together.
    assert by_pdf["Alice.pdf"].sync_group_id == by_pdf["Carla.pdf"].sync_group_id
    assert by_pdf["Alice.pdf"].sync_group_id != ""


def test_apply_super_symbol_immediate_is_one_undoable_action(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)

    controller.apply_super_symbol_immediate(
        exam=exam,
        region_id="r-a",
        page_number=1,
        matched_student_ids=["alice", "bob", "carla"],
        annotation_type="symbol",
        content="✓",
        color_hex="#d62828",
        font_size=20.0,
        x=1.0,
        y=1.0,
    )

    reloaded = controller._deps.exam_repository.load_exam(
        controller._deps.exam_repository.index_root / "exam-1.json"
    )
    assert len(reloaded.pdf_annotations) == 3

    assert controller.undo() is True
    reloaded = controller._deps.exam_repository.load_exam(
        controller._deps.exam_repository.index_root / "exam-1.json"
    )
    assert len(reloaded.pdf_annotations) == 0

    assert controller.redo() is True
    reloaded = controller._deps.exam_repository.load_exam(
        controller._deps.exam_repository.index_root / "exam-1.json"
    )
    assert len(reloaded.pdf_annotations) == 3


def test_apply_super_symbol_immediate_returns_none_for_empty_match_list(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)

    updated = controller.apply_super_symbol_immediate(
        exam=exam,
        region_id="r-a",
        page_number=1,
        matched_student_ids=[],
        annotation_type="symbol",
        content="✓",
        color_hex="#d62828",
        font_size=20.0,
        x=1.0,
        y=1.0,
    )

    assert updated is None


def test_load_scores_for_exam_reads_csv_keyed_by_student_and_task(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)

    controller._deps.score_repository.save_score(
        exam=exam, student_id="alice", task_code="1a", points=3.0, max_points=5.0
    )
    controller._deps.score_repository.save_score(
        exam=exam, student_id="bob", task_code="1a", points=5.0, max_points=5.0
    )

    scores = controller.load_scores_for_exam(exam=exam)

    assert scores["alice"]["1a"] == 3.0
    assert scores["bob"]["1a"] == 5.0
    assert "carla" not in scores
