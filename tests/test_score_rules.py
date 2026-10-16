"""Score entries: points within 0..max of the task, checked before anything is written."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.adapters.bootstrap.wiring import build_gui_dependencies
from app.adapters.gui import ui_intent_controller as uic_module
from app.adapters.gui.ui_intent_controller import UiIntentController
from app.core.domain.models import ExamProject, RegionAssignment, RegionBox, StudentExam, TaskDefinition, utc_now_iso
from app.core.domain.score_rules import points_error


class _FakeApp:
    def set_status(self, text: str) -> None:
        self.status = text

    def refresh_exam_content_in_place(self) -> None:
        pass


@pytest.fixture
def errors(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    shown: list[str] = []
    monkeypatch.setattr(uic_module.messagebox, "showerror", lambda title, text, **_: shown.append(text))
    monkeypatch.setattr(uic_module.messagebox, "showinfo", lambda title, text, **_: shown.append(text))
    return shown


def _setup(tmp_path: Path) -> tuple[UiIntentController, ExamProject]:
    folder = tmp_path / "exam"
    folder.mkdir()
    now = utc_now_iso()
    exam = ExamProject(
        exam_id="exam-scores", exam_name="Mathe", folder_path=str(folder), created_at=now, updated_at=now, standard_page_count=1,
        students=[StudentExam("anna", "Anna", "Anna.pdf", 1)],
        regions=[RegionAssignment("r", "", 1, RegionBox(0, 0, 100, 100), ["2A"], ["A"])],
        tasks=[TaskDefinition("2A", "2A", 4.0)],
    )
    controller = UiIntentController(app=_FakeApp(), deps=build_gui_dependencies(tmp_path / "app_data"))
    controller._deps.exam_repository.save_exam(exam)
    return controller, exam


@pytest.mark.parametrize(("points", "max_points", "message"), [
    (4.0, 4.0, None),
    (0.0, 4.0, None),
    (4.5, 4.0, "4.5 Punkte sind mehr als die 4 möglichen Punkte von Aufgabe 2A."),
    (-1.0, 4.0, "Punkte dürfen nicht negativ sein."),
])
def test_points_error(points, max_points, message):
    assert points_error(points, max_points, "2A") == message


def _save(controller, exam, points_text: str, max_text: str = "4", code: str = "2A") -> bool:
    return controller.save_score_immediate(exam=exam, student_id="anna", task_code=code, points_text=points_text, max_points_text=max_text)


def test_exactly_the_maximum_is_saved_more_is_rejected_without_any_change(tmp_path, errors):
    controller, exam = _setup(tmp_path)
    assert _save(controller, exam, "4")
    csv_before = (Path(exam.folder_path) / "korrektor_scores.csv").read_text(encoding="utf-8")
    history_before = controller._deps.undo_history.peek_undo()
    assert not _save(controller, exam, "5", max_text="9")  # the task's maximum (4) wins over the passed one
    assert errors[-1] == "5 Punkte sind mehr als die 4 möglichen Punkte von Aufgabe 2A."
    assert (Path(exam.folder_path) / "korrektor_scores.csv").read_text(encoding="utf-8") == csv_before
    assert controller._deps.undo_history.peek_undo() == history_before
    assert not _save(controller, exam, "-1")
    assert controller.load_saved_points(exam=exam, student_id="anna", task_code="2A") == "4.00"


def test_unknown_code_falls_back_to_the_passed_maximum(tmp_path, errors):
    controller, exam = _setup(tmp_path)
    assert _save(controller, exam, "3", max_text="3", code="X1")
    assert not _save(controller, exam, "3,5", max_text="3", code="X1")
    assert "von Aufgabe X1" in errors[-1]
