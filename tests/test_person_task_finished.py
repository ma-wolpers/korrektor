""""Fertig" per person and task (schema v2): set/clear, undo, all-or-nothing validation, counting."""

from pathlib import Path

import pytest

from app.adapters.bootstrap.wiring import build_gui_dependencies
from app.adapters.gui import ui_intent_controller as uic_module
from app.adapters.gui.main_window import CorrectionTemplate, MainWindow
from app.adapters.gui.ui_intent_controller import UiIntentController
from app.core.domain.models import (
    ExamProject,
    PersonTaskCompletion,
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
                task_codes=["1A", "1B"],
                assigned_area_codes=["A"],
                is_read_complete=True,
            ),
        ],
        tasks=[TaskDefinition(code="1A", name="1a", max_points=5.0), TaskDefinition(code="1B", name="1b", max_points=2.0)],
    )


def _setup(tmp_path: Path) -> tuple[UiIntentController, ExamProject]:
    exam_folder = tmp_path / "exam"
    exam_folder.mkdir()
    deps = build_gui_dependencies(tmp_path / "app_data")
    controller = UiIntentController(app=_FakeApp(), deps=deps)
    exam = _build_exam(exam_folder)
    controller._deps.exam_repository.save_exam(exam)
    return controller, exam


def _reload(controller: UiIntentController) -> ExamProject:
    return controller._deps.exam_repository.load_exam(controller._deps.exam_repository.exam_file_for_id("exam-1"))


def _pairs(exam: ExamProject) -> set[tuple[str, str]]:
    return {(item.student_id, item.task_code) for item in exam.person_task_completions if item.is_finished}


def test_set_single_person_single_task(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)

    updated = controller.set_persons_tasks_finished_immediate(exam=exam, student_ids=["alice"], task_codes=["1a"], is_finished=True)

    assert updated is not None and _pairs(updated) == {("alice", "1A")}
    assert controller._app.status_messages[-1] == "Aufgabe 1A als fertig markiert"
    assert controller.is_person_task_finished(exam=updated, student_id="alice", task_code="1A")
    assert not controller.are_person_tasks_finished(exam=updated, student_id="alice", task_codes=["1A", "1B"])


def test_unset_removes_only_the_given_pairs(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)
    exam.person_task_completions = [PersonTaskCompletion("alice", "1A"), PersonTaskCompletion("alice", "1B")]
    controller._deps.exam_repository.save_exam(exam)

    updated = controller.set_persons_tasks_finished_immediate(exam=exam, student_ids=["alice"], task_codes=["1A"], is_finished=False)

    assert _pairs(updated) == {("alice", "1B")}
    assert controller._app.status_messages[-1] == "Aufgabe 1A als offen markiert"


def test_multiple_persons_and_tasks_are_one_history_action(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)

    updated = controller.set_persons_tasks_finished_immediate(exam=exam, student_ids=["alice", "bob", "carla"], task_codes=["1A", "1B"], is_finished=True)

    assert len(_pairs(updated)) == 6
    assert controller.undo() is True and _pairs(_reload(controller)) == set()
    assert controller.redo() is True and len(_pairs(_reload(controller))) == 6


def test_unknown_person_or_task_rejects_everything(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)
    controller.set_persons_tasks_finished_immediate(exam=exam, student_ids=["alice"], task_codes=["1A"], is_finished=True)
    before = _reload(controller)

    assert controller.set_persons_tasks_finished_immediate(exam=before, student_ids=["alice", "nobody"], task_codes=["1A"], is_finished=True) is None
    assert controller.set_persons_tasks_finished_immediate(exam=before, student_ids=["bob"], task_codes=["9Z"], is_finished=True) is None
    assert _pairs(_reload(controller)) == {("alice", "1A")}
    assert controller.undo_label() == "Aufgabe 1A als fertig markiert"


def test_duplicate_student_ids_are_deduplicated(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)

    updated = controller.set_persons_tasks_finished_immediate(exam=exam, student_ids=["alice", "alice", "bob"], task_codes=["1A"], is_finished=True)

    assert _pairs(updated) == {("alice", "1A"), ("bob", "1A")}
    assert controller._app.status_messages[-1] == "Aufgabe 1A: 2 Personen als fertig markiert"


def test_count_counts_persons_finished_with_every_code(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)
    ids = ["alice", "bob", "carla"]
    assert controller.count_persons_tasks_finished(exam=exam, task_codes=["1A", "1B"], student_ids=ids) == 0
    exam.person_task_completions = [PersonTaskCompletion("alice", "1A"), PersonTaskCompletion("alice", "1B"), PersonTaskCompletion("bob", "1A")]

    assert controller.count_persons_tasks_finished(exam=exam, task_codes=["1A", "1B"], student_ids=ids) == 1
    assert controller.count_persons_tasks_finished(exam=exam, task_codes=["1A"], student_ids=ids) == 2
    # Documented contract: a caller-supplied duplicate is counted again.
    assert controller.count_persons_tasks_finished(exam=exam, task_codes=["1A"], student_ids=["alice", "alice"]) == 2


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
    assert MainWindow._are_all_tasks_scored(scores=scores, template=_template(), student_ids=["alice", "bob"]) is False


def test_are_all_tasks_scored_true_when_everyone_has_every_task() -> None:
    scores = {"alice": {"1a": 3.0, "1b": 2.0}, "bob": {"1a": 5.0, "1b": 0.0}}
    assert MainWindow._are_all_tasks_scored(scores=scores, template=_template(), student_ids=["alice", "bob"]) is True


def test_are_all_tasks_scored_false_for_empty_student_ids() -> None:
    """Vacuous-truth guard: `all(...)` over an empty sequence must not read as "all scored"."""
    assert MainWindow._are_all_tasks_scored(scores={}, template=_template(), student_ids=[]) is False
