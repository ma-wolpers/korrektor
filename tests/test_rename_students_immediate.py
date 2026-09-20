from pathlib import Path

import pytest

from app.adapters.bootstrap.wiring import build_gui_dependencies
from app.adapters.gui import ui_intent_controller as uic_module
from app.adapters.gui.ui_intent_controller import UiIntentController
from app.core.domain.models import ExamProject, StudentExam, utc_now_iso


@pytest.fixture(autouse=True)
def _no_real_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent showerror/showinfo from opening a real (blocking) Tk dialog."""
    monkeypatch.setattr(uic_module.messagebox, "showerror", lambda *args, **kwargs: None)
    monkeypatch.setattr(uic_module.messagebox, "showinfo", lambda *args, **kwargs: None)


class _FakeApp:
    """Minimal stand-in for MainWindow: only what UiIntentController calls here."""

    def __init__(self) -> None:
        self.status_messages: list[str] = []
        self.invalidated: list[str] = []

    def set_status(self, text: str) -> None:
        self.status_messages.append(text)

    def invalidate_doc_cache(self, pdf_filenames) -> None:
        self.invalidated.extend(pdf_filenames)

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
            StudentExam(student_id="s1", display_name="Scan1", pdf_filename="Scan1.pdf", page_count=1),
            StudentExam(student_id="s2", display_name="Scan2", pdf_filename="Scan2.pdf", page_count=1),
        ],
    )


def _setup(tmp_path: Path) -> tuple[UiIntentController, ExamProject, Path]:
    exam_folder = tmp_path / "exam"
    exam_folder.mkdir()
    (exam_folder / "Scan1.pdf").write_bytes(b"scan-1")
    (exam_folder / "Scan2.pdf").write_bytes(b"scan-2")

    deps = build_gui_dependencies(tmp_path / "app_data")
    app = _FakeApp()
    controller = UiIntentController(app=app, deps=deps)

    exam = _build_exam(exam_folder)
    controller._deps.exam_repository.save_exam(exam)

    return controller, exam, exam_folder


def test_rename_students_immediate_renames_files_and_updates_exam(tmp_path: Path) -> None:
    controller, exam, exam_folder = _setup(tmp_path)

    updated = controller.rename_students_immediate(
        exam=exam,
        name_by_student_id={"s1": "Anna Müller", "s2": "Ben Schmidt"},
    )

    assert updated is not None
    by_id = {s.student_id: s for s in updated.students}
    assert by_id["s1"].pdf_filename == "Anna_Müller.pdf"
    assert by_id["s1"].display_name == "Anna Müller"
    assert by_id["s2"].pdf_filename == "Ben_Schmidt.pdf"
    assert (exam_folder / "Anna_Müller.pdf").exists()
    assert (exam_folder / "Ben_Schmidt.pdf").exists()
    assert not (exam_folder / "Scan1.pdf").exists()
    assert not (exam_folder / "Scan2.pdf").exists()
    # student_id is the stable identity and must never change.
    assert {s.student_id for s in updated.students} == {"s1", "s2"}


def test_rename_students_immediate_is_undoable_and_redoable(tmp_path: Path) -> None:
    controller, exam, exam_folder = _setup(tmp_path)

    controller.rename_students_immediate(
        exam=exam,
        name_by_student_id={"s1": "Anna Müller", "s2": "Ben Schmidt"},
    )
    assert (exam_folder / "Anna_Müller.pdf").exists()

    assert controller.undo() is True
    assert (exam_folder / "Scan1.pdf").exists()
    assert (exam_folder / "Scan2.pdf").exists()
    assert not (exam_folder / "Anna_Müller.pdf").exists()

    assert controller.redo() is True
    assert (exam_folder / "Anna_Müller.pdf").exists()
    assert (exam_folder / "Ben_Schmidt.pdf").exists()
    assert not (exam_folder / "Scan1.pdf").exists()


def test_rename_students_immediate_swaps_names_without_false_conflict(tmp_path: Path) -> None:
    controller, exam, exam_folder = _setup(tmp_path)

    updated = controller.rename_students_immediate(
        exam=exam,
        name_by_student_id={"s1": "Scan2", "s2": "Scan1"},
    )

    assert updated is not None
    by_id = {s.student_id: s for s in updated.students}
    assert by_id["s1"].pdf_filename == "Scan2.pdf"
    assert by_id["s2"].pdf_filename == "Scan1.pdf"
    assert (exam_folder / "Scan1.pdf").read_bytes() == b"scan-2"
    assert (exam_folder / "Scan2.pdf").read_bytes() == b"scan-1"


def test_rename_students_immediate_aborts_on_unassigned_extra_pdf(tmp_path: Path) -> None:
    controller, exam, exam_folder = _setup(tmp_path)
    (exam_folder / "Leftover.pdf").write_bytes(b"stray")

    updated = controller.rename_students_immediate(
        exam=exam,
        name_by_student_id={"s1": "Anna Müller", "s2": "Ben Schmidt"},
    )

    assert updated is None
    # Nothing was touched: the preflight must reject before any rename.
    assert (exam_folder / "Scan1.pdf").exists()
    assert (exam_folder / "Scan2.pdf").exists()
    assert (exam_folder / "Leftover.pdf").exists()
