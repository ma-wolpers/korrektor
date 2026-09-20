from pathlib import Path

import pytest

from app.adapters.bootstrap.wiring import build_gui_dependencies
from app.adapters.gui import ui_intent_controller as uic_module
from app.adapters.gui.main_window import CorrectionTemplate, MainWindow
from app.adapters.gui.ui_intent_controller import UiIntentController
from app.core.domain.models import (
    ExamProject,
    PersonAreaCompletion,
    RegionAssignment,
    RegionBox,
    StudentExam,
    TaskDefinition,
    utc_now_iso,
)


@pytest.fixture(autouse=True)
def _no_real_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent showerror/showinfo from opening a real (blocking) Tk dialog."""
    monkeypatch.setattr(uic_module.messagebox, "showerror", lambda *args, **kwargs: None)
    monkeypatch.setattr(uic_module.messagebox, "showinfo", lambda *args, **kwargs: None)


class _FakeApp:
    """Minimal stand-in for MainWindow: only what UiIntentController calls here."""

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


def _reload(controller: UiIntentController) -> ExamProject:
    return controller._deps.exam_repository.load_exam(
        controller._deps.exam_repository.index_root / "exam-1.json"
    )


# --- set_persons_area_finished_immediate -----------------------------------


def test_set_persons_area_finished_single_id_matches_legacy_single_student_behavior(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)

    updated = controller.set_persons_area_finished_immediate(
        exam=exam, student_ids=["alice"], region_id="r-a", is_finished=True
    )

    assert updated is not None
    assert [item.student_id for item in updated.person_area_completions] == ["alice"]
    assert updated.person_area_completions[0].is_finished is True
    assert controller._app.status_messages[-1] == "Fertigstatus aktualisiert: A"


def test_set_persons_area_finished_single_id_unset_matches_legacy_status_text(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)
    exam.person_area_completions = [
        PersonAreaCompletion(student_id="alice", region_id="r-a", is_finished=True)
    ]
    controller._deps.exam_repository.save_exam(exam)

    updated = controller.set_persons_area_finished_immediate(
        exam=exam, student_ids=["alice"], region_id="r-a", is_finished=False
    )

    assert updated is not None
    assert updated.person_area_completions == []
    assert controller._app.status_messages[-1] == "Fertigstatus entfernt: A"


def test_set_persons_area_finished_multiple_ids_is_one_history_action(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)

    updated = controller.set_persons_area_finished_immediate(
        exam=exam, student_ids=["alice", "bob", "carla"], region_id="r-a", is_finished=True
    )

    assert updated is not None
    finished_ids = {item.student_id for item in updated.person_area_completions if item.is_finished}
    assert finished_ids == {"alice", "bob", "carla"}

    assert controller.undo() is True
    assert _reload(controller).person_area_completions == []

    assert controller.redo() is True
    reloaded = _reload(controller)
    assert {item.student_id for item in reloaded.person_area_completions if item.is_finished} == {
        "alice",
        "bob",
        "carla",
    }


def test_set_persons_area_finished_rejects_unknown_id_without_partial_change(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)
    controller.set_persons_area_finished_immediate(
        exam=exam, student_ids=["alice"], region_id="r-a", is_finished=True
    )
    before = _reload(controller)
    before_completions = list(before.person_area_completions)

    result = controller.set_persons_area_finished_immediate(
        exam=before, student_ids=["alice", "does-not-exist"], region_id="r-a", is_finished=True
    )

    assert result is None
    after = _reload(controller)
    assert after.person_area_completions == before_completions
    assert controller.can_undo() is True  # only the setup call above pushed a HistoryAction
    assert controller.undo_label() == "Bereich als fertig markiert: A"


def test_set_persons_area_finished_deduplicates_student_ids(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)

    updated = controller.set_persons_area_finished_immediate(
        exam=exam, student_ids=["alice", "alice", "bob"], region_id="r-a", is_finished=True
    )

    assert updated is not None
    finished_ids = [item.student_id for item in updated.person_area_completions if item.is_finished]
    assert sorted(finished_ids) == ["alice", "bob"]
    assert controller._app.status_messages[-1] == "Bereich A: 2 Personen als fertig markiert"


# --- count_persons_area_finished --------------------------------------------


def test_count_persons_area_finished_counts_none_partial_all(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)
    student_ids = ["alice", "bob", "carla"]

    assert controller.count_persons_area_finished(exam=exam, region_id="r-a", student_ids=student_ids) == 0

    exam.person_area_completions = [
        PersonAreaCompletion(student_id="alice", region_id="r-a", is_finished=True)
    ]
    assert controller.count_persons_area_finished(exam=exam, region_id="r-a", student_ids=student_ids) == 1

    exam.person_area_completions.append(
        PersonAreaCompletion(student_id="bob", region_id="r-a", is_finished=True)
    )
    exam.person_area_completions.append(
        PersonAreaCompletion(student_id="carla", region_id="r-a", is_finished=True)
    )
    assert controller.count_persons_area_finished(exam=exam, region_id="r-a", student_ids=student_ids) == 3


def test_count_persons_area_finished_overcounts_duplicate_ids_by_contract(tmp_path: Path) -> None:
    """Documented contract: a caller-supplied duplicate is counted again (over-, not under-count)."""
    controller, exam = _setup(tmp_path)
    exam.person_area_completions = [
        PersonAreaCompletion(student_id="alice", region_id="r-a", is_finished=True),
        PersonAreaCompletion(student_id="bob", region_id="r-a", is_finished=True),
    ]

    count = controller.count_persons_area_finished(
        exam=exam, region_id="r-a", student_ids=["alice", "alice", "bob"]
    )

    assert count == 3


# --- MainWindow._are_all_tasks_scored (static, no Tkinter) -----------------


def _template() -> CorrectionTemplate:
    return CorrectionTemplate(
        region_id="r-a",
        area_code="A",
        page_number=1,
        box=(0.0, 0.0, 100.0, 100.0),
        tasks=[TaskDefinition(code="1a", name="1a", max_points=5.0), TaskDefinition(code="1b", name="1b", max_points=5.0)],
    )


def test_are_all_tasks_scored_false_when_a_task_is_missing_for_one_student() -> None:
    scores = {"alice": {"1a": 3.0, "1b": 2.0}, "bob": {"1a": 5.0}}

    assert (
        MainWindow._are_all_tasks_scored(scores=scores, template=_template(), student_ids=["alice", "bob"])
        is False
    )


def test_are_all_tasks_scored_true_when_everyone_has_every_task() -> None:
    scores = {"alice": {"1a": 3.0, "1b": 2.0}, "bob": {"1a": 5.0, "1b": 0.0}}

    assert (
        MainWindow._are_all_tasks_scored(scores=scores, template=_template(), student_ids=["alice", "bob"])
        is True
    )


def test_are_all_tasks_scored_false_for_empty_student_ids() -> None:
    """Vacuous-truth guard: `all(...)` over an empty sequence must not read as "all scored"."""
    assert MainWindow._are_all_tasks_scored(scores={}, template=_template(), student_ids=[]) is False
