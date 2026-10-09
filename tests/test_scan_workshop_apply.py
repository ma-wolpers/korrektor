"""Scan-Werkstatt "Änderungen übernehmen": transaction, rollback per step, undo/redo chains (synthetic data)."""

from pathlib import Path

import pytest
from tk_test_support import build_pdf, pdf_texts

from app.adapters.bootstrap.wiring import build_gui_dependencies
from app.adapters.gui import ui_intent_controller as uic_module
from app.adapters.gui import ui_intent_controller_scan_workshop as apply_module
from app.adapters.gui.main_window_scan_workshop_view import parse_rotation_input
from app.adapters.gui.scan_workshop_session import ScanWorkshopSession
from app.adapters.gui.ui_intent_controller import UiIntentController
from app.core.domain.models import ExamProject, PdfAnnotation, StudentExam, utc_now_iso
from app.infrastructure.pdf.pdf_replacement import BACKUP_DIR_NAME, ScanWorkshopApplyError, apply_replacements


class _FakeApp:
    def __init__(self) -> None:
        self.invalidated: list[str] = []

    def set_status(self, text: str) -> None:
        pass

    def invalidate_doc_cache(self, pdf_filenames) -> None:
        self.invalidated.extend(pdf_filenames)

    def render_overview_rows(self, rows) -> None:
        pass

    def sync_current_exam_from_repository(self) -> None:
        pass

    def refresh_exam_content_in_place(self) -> None:
        pass


@pytest.fixture
def dialogs(monkeypatch):
    """Record dialogs instead of opening them; ``answers['yes']`` drives askyesno."""
    seen = {"errors": [], "yes": True, "asked": []}
    monkeypatch.setattr(uic_module.messagebox, "showerror", lambda title, text, **_: seen["errors"].append(text))
    monkeypatch.setattr(uic_module.messagebox, "askyesno", lambda title, text, **_: seen["asked"].append(text) or seen["yes"])
    return seen


def _setup(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    folder = tmp_path / "exam"
    folder.mkdir()
    build_pdf(folder / "a.pdf", 3, "A")
    build_pdf(folder / "b.pdf", 2, "B")
    now = utc_now_iso()
    exam = ExamProject(
        exam_id="scan", exam_name="Mathe", folder_path=str(folder), created_at=now, updated_at=now, standard_page_count=2,
        students=[
            StudentExam(student_id="a", display_name="Anna", pdf_filename="a.pdf", page_count=3),
            StudentExam(student_id="b", display_name="Ben", pdf_filename="b.pdf", page_count=2),
        ],
        pdf_annotations=[PdfAnnotation("m1", "a.pdf", 3, "symbol", "✓", "#ff0000", 50.0, 60.0)],
    )
    deps = build_gui_dependencies(tmp_path / "base")
    controller = UiIntentController(app=_FakeApp(), deps=deps)
    exam_file = deps.exam_repository.save_exam(exam)
    return controller, deps.exam_repository.load_exam(exam_file), folder, exam_file


def _apply(controller, exam, edit):
    """Run ``edit(session)`` on a fresh session and apply its pending changes like the GUI does."""
    session = ScanWorkshopSession(exam.students)
    edit(session)
    states = {pdf: session.states[pdf] for pdf in session.changed_pdfs()}
    remap = controller.plan_scan_workshop_apply(exam=exam, states=states)
    return controller.apply_scan_workshop_immediate(exam=exam, states=states, remap=remap)


def _edit_a(session):
    """Anna: page 3 to the front, delete page 2; Ben: delete page 1."""
    session.go_page(2)
    session.move_page(-2)
    session.go_page(2)  # position 3 = original page 2
    session.toggle_delete()
    session.go_student(1)
    session.go_page(-1)  # Ben keeps position 2 (clamped) -> page 1
    session.toggle_delete()


def _edit_b(session):
    """Anna: swap the two remaining pages."""
    session.move_page(1)


def _state(folder):
    return pdf_texts(folder / "a.pdf"), pdf_texts(folder / "b.pdf")


def test_apply_writes_pdfs_backups_and_remapped_exam(tmp_path, monkeypatch, dialogs):
    controller, exam, folder, exam_file = _setup(tmp_path, monkeypatch)
    updated = _apply(controller, exam, _edit_a)

    assert _state(folder) == (["A 3", "A 1"], ["B 2"])
    assert [student.page_count for student in updated.students] == [2, 1]
    assert updated.pdf_annotations[0].page_number == 1
    backups = sorted(path.name for path in (folder / BACKUP_DIR_NAME).rglob("*.pdf"))
    assert backups == [".a_roh.pdf", ".b_roh.pdf"]
    assert not list(folder.glob("*.tmp.pdf"))
    assert controller.can_undo() and set(controller._app.invalidated) == {"a.pdf", "b.pdf"}


def test_sequence_apply_a_b_undo_b_a_redo_a_b(tmp_path, monkeypatch, dialogs):
    controller, exam, folder, exam_file = _setup(tmp_path, monkeypatch)
    repo = controller._deps.exam_repository
    original = _state(folder)
    after_a = _apply(controller, exam, _edit_a)
    state_a = _state(folder)
    _apply(controller, after_a, _edit_b)
    state_b = _state(folder)
    assert state_a == (["A 3", "A 1"], ["B 2"]) and state_b == (["A 1", "A 3"], ["B 2"])

    for expected, pages, step in ((state_a, [2, 1], controller.undo), (original, [3, 2], controller.undo),
                                  (state_a, [2, 1], controller.redo), (state_b, [2, 1], controller.redo)):
        assert step()
        assert _state(folder) == expected
        assert [student.page_count for student in repo.load_exam(exam_file).students] == pages
    assert not dialogs["errors"] and len(dialogs["asked"]) == 4


def test_declined_warning_keeps_stacks_and_files(tmp_path, monkeypatch, dialogs):
    controller, exam, folder, _ = _setup(tmp_path, monkeypatch)
    _apply(controller, exam, _edit_a)
    dialogs["yes"] = False

    assert not controller.undo()
    assert controller.can_undo() and not controller.can_redo()
    assert _state(folder) == (["A 3", "A 1"], ["B 2"])


def test_undo_refuses_when_the_pdf_changed_meanwhile(tmp_path, monkeypatch, dialogs):
    controller, exam, folder, _ = _setup(tmp_path, monkeypatch)
    _apply(controller, exam, _edit_a)
    build_pdf(folder / "a.pdf", 1, "fremd")

    assert not controller.undo()
    assert "verändert" in dialogs["errors"][0] and controller.can_undo()
    assert pdf_texts(folder / "a.pdf") == ["fremd 1"] and pdf_texts(folder / "b.pdf") == ["B 2"]


def _assert_untouched(folder, exam_file, before_json, controller):
    assert _state(folder) == (["A 1", "A 2", "A 3"], ["B 1", "B 2"])
    assert exam_file.read_bytes() == before_json
    assert not list(folder.glob("*.tmp.pdf")) and not list((folder / BACKUP_DIR_NAME).rglob("*.pdf"))
    assert not controller.can_undo()


def test_failure_while_writing_temp_files_changes_nothing(tmp_path, monkeypatch, dialogs):
    controller, exam, folder, exam_file = _setup(tmp_path, monkeypatch)
    before = exam_file.read_bytes()
    real_write, calls = apply_module.write_edited_pdf, []

    def failing_write(source, order, edits, target):
        calls.append(target)
        if len(calls) == 2:
            raise OSError("Platte voll")
        return real_write(source, order, edits, target)

    monkeypatch.setattr(apply_module, "write_edited_pdf", failing_write)
    assert _apply(controller, exam, _edit_a) is None
    assert "Platte voll" in dialogs["errors"][0]
    _assert_untouched(folder, exam_file, before, controller)


def test_failure_while_swapping_rolls_back(tmp_path, monkeypatch, dialogs):
    controller, exam, folder, exam_file = _setup(tmp_path, monkeypatch)
    before = exam_file.read_bytes()
    real_replace = Path.replace

    def flaky_replace(self, target):
        if self.name == "b.korrektor.tmp.pdf":
            raise PermissionError("gesperrt")
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", flaky_replace)
    assert _apply(controller, exam, _edit_a) is None
    monkeypatch.setattr(Path, "replace", real_replace)
    assert "gesperrt" in dialogs["errors"][0] and "nichts verändert" in dialogs["errors"][0]
    _assert_untouched(folder, exam_file, before, controller)


def test_failure_while_saving_the_exam_rolls_back_the_pdfs(tmp_path, monkeypatch, dialogs):
    controller, exam, folder, exam_file = _setup(tmp_path, monkeypatch)
    before = exam_file.read_bytes()

    def failing_save(_exam):
        raise OSError("Speichern fehlgeschlagen")

    monkeypatch.setattr(controller._deps.exam_repository, "save_exam", failing_save)
    assert _apply(controller, exam, _edit_a) is None
    assert "Speichern fehlgeschlagen" in dialogs["errors"][0]
    _assert_untouched(folder, exam_file, before, controller)


def test_rollback_reports_files_it_could_not_restore(tmp_path, monkeypatch):
    target, temp = build_pdf(tmp_path / "a.pdf", 1, "alt"), build_pdf(tmp_path / "a.tmp.pdf", 1, "neu")
    real_unlink = Path.unlink

    def stuck_unlink(self, missing_ok=False):
        if self == target:
            raise PermissionError("offen in einem Viewer")
        return real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", stuck_unlink)
    with pytest.raises(ScanWorkshopApplyError) as info:
        apply_replacements(tmp_path / "aid", {target: temp}, after=lambda: (_ for _ in ()).throw(OSError("save")))
    backup = tmp_path / "aid" / "roh" / ".a_roh.pdf"
    assert info.value.leftover_files == [target, backup]
    assert str(info.value.cause) == "save"
    assert pdf_texts(backup) == ["alt 1"] and pdf_texts(target) == ["neu 1"]  # original kept safe, not forced over


@pytest.mark.parametrize(
    ("text", "expected"),
    [("3,5", 3.5), (" -2° ", -2.0), ("1.25", 1.25), ("", 0.0), ("abc", None), ("1,2,3", None), ("0,5 cm", 0.5), ("-1cm", -1.0)],
)
def test_parse_rotation_input(text, expected):
    assert parse_rotation_input(text) == expected
