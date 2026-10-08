"""Controller flow of "Neue Klausur": choice between folder and PDF import (fake app, synthetic PDFs)."""

from pathlib import Path

import fitz
import pytest

from app.adapters.bootstrap.wiring import build_gui_dependencies
from app.adapters.gui import ui_intent_controller_overview as overview_module
from app.adapters.gui.ui_intent_controller import UiIntentController


class _FakeApp:
    """Records what the controller asks the main window to do."""

    def __init__(self, *, wizard_starts: bool = True) -> None:
        self.wizard_calls: list[object] = []
        self.wizard_starts = wizard_starts
        self.opened_exams: list[object] = []
        self.reading_started = 0
        self.statuses: list[str] = []

    def open_import_split_wizard(self, *, on_split_complete=None) -> bool:
        self.wizard_calls.append(on_split_complete)
        return self.wizard_starts

    def set_status(self, text: str) -> None:
        self.statuses.append(text)

    def render_overview_rows(self, rows) -> None:
        pass

    def open_exam_detail(self, exam, exam_file) -> None:
        self.opened_exams.append(exam)

    def start_reading_mode_for_current_exam(self) -> None:
        self.reading_started += 1

    def sync_current_exam_from_repository(self) -> None:
        pass

    def refresh_exam_content_in_place(self) -> None:
        pass


def _build_pdf(path: Path) -> None:
    document = fitz.open()
    document.new_page()
    document.save(path)
    document.close()


@pytest.fixture
def dialogs(monkeypatch: pytest.MonkeyPatch):
    state = {"choice": None, "folder": "", "strings": [], "infos": [], "errors": []}
    monkeypatch.setattr(overview_module.choicedialog, "askchoice", lambda *args, **kwargs: state["choice"])
    monkeypatch.setattr(overview_module.filedialog, "askdirectory", lambda **kwargs: state["folder"])
    monkeypatch.setattr(
        overview_module.simpledialog, "askstring", lambda *args, **kwargs: state["strings"].pop(0)
    )
    monkeypatch.setattr(overview_module.messagebox, "showinfo", lambda t, m, **kw: state["infos"].append(m))
    monkeypatch.setattr(overview_module.messagebox, "showerror", lambda t, m, **kw: state["errors"].append(m))
    return state


def _controller(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, app: _FakeApp) -> UiIntentController:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    deps = build_gui_dependencies(tmp_path / "repo")
    return UiIntentController(app=app, deps=deps)


def test_folder_choice_keeps_the_previous_flow(tmp_path, monkeypatch, dialogs):
    folder = tmp_path / "exam"
    folder.mkdir()
    _build_pdf(folder / "Anna_Müller.pdf")
    app = _FakeApp()
    controller = _controller(tmp_path, monkeypatch, app)
    dialogs.update(choice="folder", folder=str(folder), strings=["Mathe", "", ""])

    controller.create_exam()

    assert app.wizard_calls == []
    assert [student.display_name for student in app.opened_exams[0].students] == ["Anna_Müller"]
    assert app.reading_started == 1


def test_split_choice_opens_wizard_and_callback_creates_exam_with_typed_names(tmp_path, monkeypatch, dialogs):
    app = _FakeApp()
    controller = _controller(tmp_path, monkeypatch, app)
    dialogs.update(choice="split")

    controller.create_exam()

    assert len(app.wizard_calls) == 1 and callable(app.wizard_calls[0])
    split_folder = tmp_path / "split"
    split_folder.mkdir()
    _build_pdf(split_folder / "Anna_Müller.pdf")
    _build_pdf(split_folder / "Abgabe_02.pdf")
    dialogs["strings"] = ["Mathe 10a", "10a", "Mathe"]

    app.wizard_calls[0](split_folder, {"Anna_Müller.pdf": "Anna Müller", "Abgabe_02.pdf": "Abgabe_02"})

    exam = app.opened_exams[0]
    assert sorted(student.display_name for student in exam.students) == ["Abgabe_02", "Anna Müller"]
    assert exam.exam_name == "Mathe 10a" and app.reading_started == 1


def test_split_callback_cancelled_name_dialog_reports_folder(tmp_path, monkeypatch, dialogs):
    app = _FakeApp()
    controller = _controller(tmp_path, monkeypatch, app)
    split_folder = tmp_path / "split"
    split_folder.mkdir()
    _build_pdf(split_folder / "Anna.pdf")
    dialogs["strings"] = [None]

    controller._create_exam_from_split(split_folder, {"Anna.pdf": "Anna"})

    assert app.opened_exams == []
    assert str(split_folder) in dialogs["infos"][-1]


def test_split_choice_rejected_by_running_import_creates_nothing(tmp_path, monkeypatch, dialogs):
    app = _FakeApp(wizard_starts=False)
    controller = _controller(tmp_path, monkeypatch, app)
    dialogs.update(choice="split")

    controller.create_exam()

    assert app.opened_exams == []
    assert "nicht gestartet" in app.statuses[-1]


def test_cancelling_the_choice_does_nothing(tmp_path, monkeypatch, dialogs):
    app = _FakeApp()
    controller = _controller(tmp_path, monkeypatch, app)
    dialogs.update(choice=None)

    controller.create_exam()

    assert app.wizard_calls == [] and app.opened_exams == []
