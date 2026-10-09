"""Region edits with exam-wide tasks (schema v2): points per task, A3 cleanup, A4 shared pages, A5 old scores."""

from pathlib import Path

import pytest

from app.adapters.bootstrap.wiring import build_gui_dependencies
from app.adapters.gui import ui_intent_controller as uic_module
from app.adapters.gui.ui_intent_controller import UiIntentController
from app.core.domain.models import ExamProject, PdfAnnotation, RegionAssignment, RegionBox, StudentExam, TaskDefinition, utc_now_iso


@pytest.fixture
def dialogs(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Record dialogs instead of opening them; ``dialogs["yes"]`` answers every askyesno."""
    seen = {"errors": [], "asked": [], "yes": True}
    monkeypatch.setattr(uic_module.messagebox, "showerror", lambda title, text, **_: seen["errors"].append(text))
    monkeypatch.setattr(uic_module.messagebox, "askyesno", lambda title, text, **_: seen["asked"].append(text) or seen["yes"])
    return seen


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
            StudentExam(student_id="alice", display_name="Alice", pdf_filename="Alice.pdf", page_count=2),
            StudentExam(student_id="bob", display_name="Bob", pdf_filename="Bob.pdf", page_count=1),
        ],
        regions=[
            RegionAssignment(
                region_id="r-a",
                student_pdf="",
                page_number=1,
                box=RegionBox(0, 0, 100, 100),
                task_codes=["1A"],
                assigned_area_codes=["A"],
                is_read_complete=True,
            ),
        ],
        tasks=[TaskDefinition(code="1A", name="1A", max_points=5.0)],
    )


def _setup(tmp_path: Path) -> tuple[UiIntentController, ExamProject]:
    exam_folder = tmp_path / "exam"
    exam_folder.mkdir()
    deps = build_gui_dependencies(tmp_path / "app_data")
    controller = UiIntentController(app=_FakeApp(), deps=deps)
    exam = _build_exam(exam_folder)
    controller._deps.exam_repository.save_exam(exam)
    return controller, exam


def _reload(controller) -> ExamProject:
    return controller._deps.exam_repository.load_exam(controller._deps.exam_repository.exam_file_for_id("exam-1"))


def _upsert(controller, exam, specs, *, student_pdf="", page=1, region_id=None, box=(0, 0, 50, 50)):
    return controller.upsert_region_immediate(
        exam=exam, student_pdf=student_pdf, page_number=page, box=box, task_specs=specs, region_id=region_id
    )


def test_max_points_change_when_never_scored_asks_and_applies_to_the_task(tmp_path, dialogs) -> None:
    controller, exam = _setup(tmp_path)

    updated = _upsert(controller, exam, [("1A", 8.0)], region_id="r-a", box=(0, 0, 100, 100))

    assert updated is not None and updated.tasks == [TaskDefinition("1A", "1A", 8.0)]
    assert "1A: 5 → 8 P." in dialogs["asked"][0]


def test_declined_point_change_leaves_everything_unchanged(tmp_path, dialogs) -> None:
    controller, exam = _setup(tmp_path)
    dialogs["yes"] = False

    assert _upsert(controller, exam, [("1A", 8.0)], region_id="r-a") is None
    assert _reload(controller).tasks[0].max_points == 5.0 and not controller.can_undo()


def test_max_points_change_rejected_once_task_is_scored(tmp_path, dialogs) -> None:
    controller, exam = _setup(tmp_path)
    controller._deps.score_repository.save_score(exam=exam, student_id="alice", task_code="1A", points=3.0, max_points=5.0)

    assert _upsert(controller, exam, [("1A", 8.0)], region_id="r-a") is None
    assert "bereits bewerteten" in dialogs["errors"][0]
    assert _reload(controller).tasks[0].max_points == 5.0


def test_unrelated_task_edits_allowed_when_another_task_is_scored(tmp_path, dialogs) -> None:
    controller, exam = _setup(tmp_path)
    controller._deps.score_repository.save_score(exam=exam, student_id="alice", task_code="1A", points=3.0, max_points=5.0)

    updated = _upsert(controller, exam, [("1A", 5.0), ("1B", 3.0)], region_id="r-a", box=(0, 0, 100, 100))

    assert updated is not None
    assert {task.code: task.max_points for task in updated.tasks} == {"1A": 5.0, "1B": 3.0}
    assert updated.regions[0].task_codes == ["1A", "1B"] and not dialogs["asked"]


def test_new_region_can_reference_an_existing_task_without_points(tmp_path, dialogs) -> None:
    controller, exam = _setup(tmp_path)

    updated = _upsert(controller, exam, [("1A", None), ("2A", 10.0)], box=(0, 100, 50, 150))

    assert updated is not None and len(updated.regions) == 2
    assert [region.task_codes for region in updated.regions] == [["1A"], ["1A", "2A"]]
    assert [task.code for task in updated.tasks] == ["1A", "2A"]
    assert updated.regions[1].assigned_area_codes == ["B"]


def test_unknown_code_without_points_is_rejected(tmp_path, dialogs) -> None:
    controller, exam = _setup(tmp_path)

    assert _upsert(controller, exam, [("7A", None)]) is None
    assert "7A ist noch nicht festgelegt" in dialogs["errors"][0]


def test_einzelseiten_region_on_a_page_only_one_student_has(tmp_path, dialogs) -> None:
    controller, exam = _setup(tmp_path)

    updated = _upsert(controller, exam, [("1A", None)], student_pdf="Alice.pdf", page=2)

    assert updated is not None and updated.regions[1].student_pdf == "Alice.pdf"


def test_superseiten_region_only_on_pages_every_student_has(tmp_path, dialogs) -> None:
    """Rule A4: page 2 exists only for Alice - a Superseiten-Bereich there is rejected, state unchanged."""
    controller, exam = _setup(tmp_path)

    assert _upsert(controller, exam, [("1A", None)], page=2) is None
    assert "alle Personen haben" in dialogs["errors"][0]
    assert len(_reload(controller).regions) == 1


def test_recreated_task_with_old_scores_of_a_different_maximum_is_rejected(tmp_path, dialogs) -> None:
    """Rule A5: 2A was scored with max 4 and then removed; re-creating it with 6 points must not reuse those scores."""
    controller, exam = _setup(tmp_path)
    controller._deps.score_repository.save_score(exam=exam, student_id="alice", task_code="2A", points=3.0, max_points=4.0)

    assert _upsert(controller, exam, [("2A", 6.0)]) is None
    assert "2A:4" in dialogs["errors"][0]

    updated = _upsert(controller, exam, [("2A", 4.0)])
    assert updated is not None and "alte Bewertungen von 1 Person(en) für 2A wieder aktiv" in controller._app.status_messages[-1]


def test_delete_region_prunes_its_tasks_and_removes_their_marks_in_one_undo_step(tmp_path, dialogs) -> None:
    """Rule A3: deleting the only region of 1A removes the task, its marks and its "Fertig"; Strg+Z restores all."""
    controller, exam = _setup(tmp_path)
    exam.pdf_annotations.append(PdfAnnotation("m1", "Alice.pdf", 1, "symbol", "✓", "#ff0000", 10, 10, task_code="1A", region_id="r-a"))
    exam = controller._deps.exam_repository.load_exam(controller._deps.exam_repository.save_exam(exam))
    exam = _upsert(controller, exam, [("2A", 1.0)], box=(0, 100, 50, 150))

    updated = controller.delete_region_immediate(exam=exam, region_id="r-a")

    assert [task.code for task in updated.tasks] == ["2A"] and updated.pdf_annotations == []
    assert "Symbol „✓“ bei Alice (Seite 1)" in dialogs["asked"][-1]
    assert controller.undo()
    restored = _reload(controller)
    assert [task.code for task in restored.tasks] == ["1A", "2A"] and len(restored.pdf_annotations) == 1


def test_removing_a_code_from_a_region_removes_only_marks_of_that_code(tmp_path, dialogs) -> None:
    controller, exam = _setup(tmp_path)
    exam = _upsert(controller, exam, [("1A", 5.0), ("1B", 2.0)], region_id="r-a", box=(0, 0, 100, 100))
    exam.pdf_annotations += [
        PdfAnnotation("m1", "Alice.pdf", 1, "symbol", "✓", "#ff0000", 10, 10, task_code="1A", region_id="r-a"),
        PdfAnnotation("m2", "Alice.pdf", 1, "symbol", "x", "#ff0000", 20, 20, task_code="1B", region_id="r-a"),
        PdfAnnotation("m3", "Bob.pdf", 1, "symbol", "Σ", "#ff0000", 30, 30, task_code="", region_id="r-a"),
    ]
    exam = controller._deps.exam_repository.load_exam(controller._deps.exam_repository.save_exam(exam))

    updated = _upsert(controller, exam, [("1A", None)], region_id="r-a", box=(0, 0, 100, 100))

    assert [mark.annotation_id for mark in updated.pdf_annotations] == ["m1", "m3"]
    assert [task.code for task in updated.tasks] == ["1A"]
