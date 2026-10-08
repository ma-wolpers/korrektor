"""Exam folders as the single source: adopting existing exam data and removing exams (fake app, synthetic data)."""

from pathlib import Path

import fitz
import pytest

from app.adapters.bootstrap.wiring import build_gui_dependencies
from app.adapters.gui import ui_intent_controller_exam_storage as storage_module
from app.adapters.gui import ui_intent_controller_overview as overview_module
from app.adapters.gui.ui_intent_controller import UiIntentController
from app.infrastructure.repositories.json_exam_repository import EXAM_DATA_FILENAME


class _FakeApp:
    def __init__(self) -> None:
        self.opened: list[object] = []
        self.statuses: list[str] = []
        self.selected = None

    def set_status(self, text: str) -> None:
        self.statuses.append(text)

    def render_overview_rows(self, rows) -> None:
        self.rows = rows

    def open_exam_detail(self, exam, exam_file) -> None:
        self.opened.append(exam)

    def start_reading_mode_for_current_exam(self) -> None:
        pass

    def get_selected_row(self):
        return self.selected

    def on_exam_deleted(self, exam_id) -> None:
        pass

    def sync_current_exam_from_repository(self) -> None:
        pass

    def refresh_exam_content_in_place(self) -> None:
        pass


@pytest.fixture
def dialogs(monkeypatch):
    state = {"yesno": [], "choice": [], "strings": [], "errors": []}
    for module in (overview_module, storage_module):
        monkeypatch.setattr(module.messagebox, "askyesno", lambda *a, **k: state["yesno"].pop(0))
        monkeypatch.setattr(module.messagebox, "showerror", lambda t, m, **k: state["errors"].append(m))
        monkeypatch.setattr(module.messagebox, "showinfo", lambda *a, **k: None)
        monkeypatch.setattr(module.choicedialog, "askchoice", lambda *a, **k: state["choice"].pop(0))
    monkeypatch.setattr(overview_module.simpledialog, "askstring", lambda *a, **k: state["strings"].pop(0))
    return state


def _controller(tmp_path: Path, monkeypatch, name: str) -> tuple[UiIntentController, _FakeApp]:
    monkeypatch.setenv("APPDATA", str(tmp_path / f"appdata-{name}"))
    app = _FakeApp()
    return UiIntentController(app=app, deps=build_gui_dependencies(tmp_path / f"base-{name}")), app


def _exam_folder(tmp_path: Path, name: str = "exam") -> Path:
    folder = tmp_path / name
    folder.mkdir()
    document = fitz.open()
    document.new_page()
    document.save(folder / "Anna.pdf")
    document.close()
    return folder


def _create(controller, dialogs, folder: Path, exam_name: str = "Mathe"):
    dialogs["strings"] += [exam_name, "", ""]
    assert controller._create_exam_from_folder(folder) is True
    return controller._deps.exam_repository.exam_file_for_id(controller._app.opened[-1].exam_id)


def test_folder_copied_to_another_pc_is_adopted_with_all_data(tmp_path, monkeypatch, dialogs):
    pc1, _app1 = _controller(tmp_path, monkeypatch, "pc1")
    folder = _exam_folder(tmp_path)
    exam_file = _create(pc1, dialogs, folder)
    exam = pc1._deps.exam_repository.load_exam(exam_file)
    exam.task_comments = {"anna": {"1A": "Gut gemacht"}}
    pc1._deps.exam_repository.save_exam(exam)

    pc2, app2 = _controller(tmp_path, monkeypatch, "pc2")
    dialogs["yesno"] = [True]
    assert pc2._create_exam_from_folder(folder) is True

    adopted = app2.opened[-1]
    assert adopted.exam_id == exam.exam_id and adopted.task_comments == {"anna": {"1A": "Gut gemacht"}}
    assert pc2._deps.exam_repository.exam_file_for_id(exam.exam_id) == exam_file
    assert dialogs["strings"] == []  # no name prompts for an adopted exam


def test_same_folder_is_just_opened(tmp_path, monkeypatch, dialogs):
    controller, app = _controller(tmp_path, monkeypatch, "pc")
    folder = _exam_folder(tmp_path)
    _create(controller, dialogs, folder)

    assert controller._create_exam_from_folder(folder) is True
    assert len(app.opened) == 2 and dialogs["yesno"] == []


def test_moved_folder_switches_the_registration(tmp_path, monkeypatch, dialogs):
    controller, _app = _controller(tmp_path, monkeypatch, "pc")
    old = _exam_folder(tmp_path, "old")
    exam_id = controller._deps.exam_repository.read_exam_header(_create(controller, dialogs, old))["exam_id"]
    new = tmp_path / "new"
    old.rename(new)
    dialogs["yesno"] = [True]

    assert controller._create_exam_from_folder(new) is True
    assert controller._deps.exam_repository.exam_file_for_id(exam_id) == (new / EXAM_DATA_FILENAME).resolve()


@pytest.mark.parametrize("choice", ["as_new", "switch"])
def test_copy_of_a_known_exam_never_opens_the_other_one(tmp_path, monkeypatch, dialogs, choice):
    import shutil

    controller, app = _controller(tmp_path, monkeypatch, "pc")
    original = _exam_folder(tmp_path, "original")
    exam_id = controller._deps.exam_repository.read_exam_header(_create(controller, dialogs, original))["exam_id"]
    copy = tmp_path / "copy"
    shutil.copytree(original, copy)
    dialogs["choice"] = [choice]

    assert controller._create_exam_from_folder(copy) is True

    repo = controller._deps.exam_repository
    opened = app.opened[-1]
    assert Path(opened.folder_path) == copy.resolve()
    if choice == "as_new":
        assert opened.exam_id != exam_id
        assert repo.exam_file_for_id(exam_id) == (original / EXAM_DATA_FILENAME).resolve()
        assert repo.exam_file_for_id(opened.exam_id) == (copy / EXAM_DATA_FILENAME).resolve()
    else:
        assert repo.exam_file_for_id(exam_id) == (copy / EXAM_DATA_FILENAME).resolve()
    controller.undo()
    assert repo.exam_file_for_id(exam_id) == (original / EXAM_DATA_FILENAME).resolve()
    assert repo.read_exam_header(copy / EXAM_DATA_FILENAME)["exam_id"] == exam_id


class _Row:
    def __init__(self, exam_file: Path, exam_id: str) -> None:
        self.source_file = exam_file
        self.exam_id = exam_id
        self.exam_name = "Mathe"


def test_remove_from_overview_keeps_data_and_is_undoable(tmp_path, monkeypatch, dialogs):
    controller, app = _controller(tmp_path, monkeypatch, "pc")
    exam_file = _create(controller, dialogs, _exam_folder(tmp_path))
    exam_id = controller._deps.exam_repository.read_exam_header(exam_file)["exam_id"]
    app.selected = _Row(exam_file, exam_id)
    dialogs["choice"] = ["unregister"]

    controller.delete_selected_exam()

    repo = controller._deps.exam_repository
    assert repo.list_exam_files() == [] and exam_file.exists()
    controller.undo()
    assert repo.list_exam_files() == [exam_file]


def test_delete_data_removes_json_csv_and_registry_together_and_undo_restores_all(tmp_path, monkeypatch, dialogs):
    controller, app = _controller(tmp_path, monkeypatch, "pc")
    folder = _exam_folder(tmp_path)
    exam_file = _create(controller, dialogs, folder)
    (folder / "korrektor_scores.csv").write_text("student_id;1A\nanna;3\n", encoding="utf-8")
    exam_bytes = exam_file.read_bytes()
    exam_id = controller._deps.exam_repository.read_exam_header(exam_file)["exam_id"]
    app.selected = _Row(exam_file, exam_id)
    dialogs["choice"] = ["delete_data"]

    controller.delete_selected_exam()

    repo = controller._deps.exam_repository
    assert not exam_file.exists() and not (folder / "korrektor_scores.csv").exists()
    assert repo.list_exam_files() == [] and (folder / "Anna.pdf").exists()
    controller.undo()
    assert exam_file.read_bytes() == exam_bytes
    assert (folder / "korrektor_scores.csv").read_text(encoding="utf-8") == "student_id;1A\nanna;3\n"
    assert repo.list_exam_files() == [exam_file]
    controller.redo()
    assert not exam_file.exists() and repo.list_exam_files() == []


def test_failed_data_deletion_rolls_back(tmp_path, monkeypatch, dialogs):
    controller, _app = _controller(tmp_path, monkeypatch, "pc")
    folder = _exam_folder(tmp_path)
    exam_file = _create(controller, dialogs, folder)
    scores = folder / "korrektor_scores.csv"
    scores.write_text("x", encoding="utf-8")
    real_unlink = Path.unlink

    def _locked(self, *args, **kwargs):
        if self.name == "korrektor_scores.csv":
            raise PermissionError("gesperrt")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", _locked)
    with pytest.raises(PermissionError):
        controller._deps.exam_repository.delete_exam_data(exam_file)

    assert exam_file.exists() and scores.exists()
    assert controller._deps.exam_repository.list_exam_files() == [exam_file]
