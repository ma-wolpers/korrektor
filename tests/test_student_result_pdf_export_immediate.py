from pathlib import Path

import fitz
import pytest

from app.adapters.bootstrap.wiring import build_gui_dependencies
from app.adapters.gui import ui_intent_controller as uic_module
from app.adapters.gui.ui_intent_controller import UiIntentController
from app.core.domain.models import ExamProject, RegionAssignment, RegionBox, StudentExam, TaskDefinition, utc_now_iso
from app.infrastructure.pdf import pdf_document_writer as pdf_writer_module
from app.infrastructure.pdf.pdf_document_writer import KORREKTOR_STATS_PAGE_MARKER


@pytest.fixture(autouse=True)
def _no_real_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(uic_module.messagebox, "showerror", lambda *args, **kwargs: None)
    monkeypatch.setattr(uic_module.messagebox, "showinfo", lambda *args, **kwargs: None)


class _FakeApp:
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


def _build_student_pdf(path: Path) -> None:
    document = fitz.open()
    document.new_page(width=200, height=300)
    document.save(path)
    document.close()


def _build_exam(exam_folder: Path, *, student_ids: tuple[str, ...] = ("alice", "bob")) -> ExamProject:
    now = utc_now_iso()
    students = []
    for student_id in student_ids:
        display_name = student_id.capitalize()
        pdf_filename = f"{display_name}.pdf"
        _build_student_pdf(exam_folder / pdf_filename)
        students.append(StudentExam(student_id=student_id, display_name=display_name, pdf_filename=pdf_filename, page_count=1))
    return ExamProject(
        exam_id="exam-1",
        exam_name="Mathe",
        folder_path=str(exam_folder),
        created_at=now,
        updated_at=now,
        standard_page_count=1,
        students=students,
        regions=[
            RegionAssignment(
                region_id="r-a",
                student_pdf="",
                page_number=1,
                box=RegionBox(0, 0, 100, 100),
                tasks=[TaskDefinition(code="1A", name="1A", max_points=10.0)],
                assigned_area_codes=["A"],
                is_read_complete=True,
            ),
        ],
    )


def _setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **exam_kwargs) -> tuple[UiIntentController, ExamProject, Path]:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    exam_folder = tmp_path / "exam"
    exam_folder.mkdir()
    deps = build_gui_dependencies(tmp_path / "repo")
    app = _FakeApp()
    controller = UiIntentController(app=app, deps=deps)
    exam = _build_exam(exam_folder, **exam_kwargs)
    controller._deps.exam_repository.save_exam(exam)
    return controller, exam, exam_folder


def _reload(controller: UiIntentController) -> ExamProject:
    return controller._deps.exam_repository.load_exam(controller._deps.exam_repository.index_root / "exam-1.json")


def _page_count(pdf_path: Path) -> int:
    document = fitz.open(pdf_path)
    try:
        return document.page_count
    finally:
        document.close()


def _last_page_text(pdf_path: Path) -> str:
    document = fitz.open(pdf_path)
    try:
        return document.load_page(document.page_count - 1).get_text()
    finally:
        document.close()


def test_append_grows_page_count_and_stamps_marker_and_flag(tmp_path: Path, monkeypatch) -> None:
    controller, exam, folder = _setup(tmp_path, monkeypatch)
    controller._deps.score_repository.save_score(exam=exam, student_id="alice", task_code="1A", points=8.0, max_points=10.0)
    scores = controller._deps.score_repository.load_scores(exam=exam)

    updated = controller.append_student_result_report_to_pdfs_immediate(
        exam=exam, student_ids=["alice"], scores=scores, chart_type="Spinnennetz", chart_scope="Pro Aufgabe"
    )

    assert updated is not None
    alice = next(s for s in updated.students if s.student_id == "alice")
    assert alice.stats_report_appended is True
    pdf_path = folder / "Alice.pdf"
    assert _page_count(pdf_path) == 2
    assert pdf_writer_module.read_trailing_page_marker(pdf_path) == KORREKTOR_STATS_PAGE_MARKER


def test_repeat_append_replaces_not_accumulates(tmp_path: Path, monkeypatch) -> None:
    controller, exam, folder = _setup(tmp_path, monkeypatch)
    controller._deps.score_repository.save_score(exam=exam, student_id="alice", task_code="1A", points=8.0, max_points=10.0)
    scores = controller._deps.score_repository.load_scores(exam=exam)
    pdf_path = folder / "Alice.pdf"

    controller.append_student_result_report_to_pdfs_immediate(
        exam=exam, student_ids=["alice"], scores=scores, chart_type="Spinnennetz", chart_scope="Pro Aufgabe"
    )
    exam = _reload(controller)
    controller.append_student_result_report_to_pdfs_immediate(
        exam=exam, student_ids=["alice"], scores=scores, chart_type="Balken", chart_scope="Pro Aufgabe"
    )

    assert _page_count(pdf_path) == 2


def test_undo_removes_page_and_resets_flag(tmp_path: Path, monkeypatch) -> None:
    controller, exam, folder = _setup(tmp_path, monkeypatch)
    controller._deps.score_repository.save_score(exam=exam, student_id="alice", task_code="1A", points=8.0, max_points=10.0)
    scores = controller._deps.score_repository.load_scores(exam=exam)
    pdf_path = folder / "Alice.pdf"

    controller.append_student_result_report_to_pdfs_immediate(
        exam=exam, student_ids=["alice"], scores=scores, chart_type="Spinnennetz", chart_scope="Pro Aufgabe"
    )
    assert _page_count(pdf_path) == 2

    assert controller.undo() is True
    assert _page_count(pdf_path) == 1
    assert _reload(controller).students[0].stats_report_appended is False

    assert controller.redo() is True
    assert _page_count(pdf_path) == 2
    assert _reload(controller).students[0].stats_report_appended is True


def test_redo_reinstates_the_exact_originally_rendered_page_not_a_recomputation(tmp_path: Path, monkeypatch) -> None:
    """Regression: redo must never re-render from the (possibly since-changed) current StudentResult."""
    controller, exam, folder = _setup(tmp_path, monkeypatch)
    controller._deps.score_repository.save_score(exam=exam, student_id="alice", task_code="1A", points=8.0, max_points=10.0)
    scores = controller._deps.score_repository.load_scores(exam=exam)
    pdf_path = folder / "Alice.pdf"

    controller.append_student_result_report_to_pdfs_immediate(
        exam=exam, student_ids=["alice"], scores=scores, chart_type="Spinnennetz", chart_scope="Pro Aufgabe"
    )
    original_text = _last_page_text(pdf_path)
    assert "8" in original_text

    controller.undo()
    # Change the underlying score after the original action but before redo.
    controller._deps.score_repository.save_score(exam=exam, student_id="alice", task_code="1A", points=2.0, max_points=10.0)

    assert controller.redo() is True
    redone_text = _last_page_text(pdf_path)
    assert redone_text == original_text


def test_remove_rejects_entire_batch_when_one_student_has_no_statistikseite(tmp_path: Path, monkeypatch) -> None:
    controller, exam, folder = _setup(tmp_path, monkeypatch)
    controller._deps.score_repository.save_score(exam=exam, student_id="alice", task_code="1A", points=8.0, max_points=10.0)
    controller._deps.score_repository.save_score(exam=exam, student_id="bob", task_code="1A", points=6.0, max_points=10.0)
    scores = controller._deps.score_repository.load_scores(exam=exam)

    controller.append_student_result_report_to_pdfs_immediate(
        exam=exam, student_ids=["alice"], scores=scores, chart_type="Spinnennetz", chart_scope="Pro Aufgabe"
    )
    exam = _reload(controller)

    updated = controller.remove_student_result_report_from_pdfs_immediate(exam=exam, student_ids=["alice", "bob"])

    assert updated is None
    assert _page_count(folder / "Alice.pdf") == 2
    assert _reload(controller).students[0].stats_report_appended is True


def test_remove_removes_page_and_is_undoable(tmp_path: Path, monkeypatch) -> None:
    controller, exam, folder = _setup(tmp_path, monkeypatch)
    controller._deps.score_repository.save_score(exam=exam, student_id="alice", task_code="1A", points=8.0, max_points=10.0)
    scores = controller._deps.score_repository.load_scores(exam=exam)
    pdf_path = folder / "Alice.pdf"

    controller.append_student_result_report_to_pdfs_immediate(
        exam=exam, student_ids=["alice"], scores=scores, chart_type="Spinnennetz", chart_scope="Pro Aufgabe"
    )
    exam = _reload(controller)

    updated = controller.remove_student_result_report_from_pdfs_immediate(exam=exam, student_ids=["alice"])

    assert updated is not None
    assert _page_count(pdf_path) == 1
    assert pdf_writer_module.read_trailing_page_marker(pdf_path) is None

    assert controller.undo() is True
    assert _page_count(pdf_path) == 2
    assert pdf_writer_module.read_trailing_page_marker(pdf_path) == KORREKTOR_STATS_PAGE_MARKER


def test_append_rejects_when_flag_says_appended_but_marker_is_missing(tmp_path: Path, monkeypatch) -> None:
    """Regression: physical PDF state must win over a stale/corrupted JSON flag - never guess."""
    controller, exam, folder = _setup(tmp_path, monkeypatch)
    controller._deps.score_repository.save_score(exam=exam, student_id="alice", task_code="1A", points=8.0, max_points=10.0)
    scores = controller._deps.score_repository.load_scores(exam=exam)

    exam.students[0].stats_report_appended = True  # no marker was ever actually written
    controller._deps.exam_repository.save_exam(exam)
    pdf_path = folder / "Alice.pdf"
    assert _page_count(pdf_path) == 1

    updated = controller.append_student_result_report_to_pdfs_immediate(
        exam=exam, student_ids=["alice"], scores=scores, chart_type="Spinnennetz", chart_scope="Pro Aufgabe"
    )

    assert updated is None
    assert _page_count(pdf_path) == 1


def test_append_batch_rolls_back_fully_when_second_student_fails(tmp_path: Path, monkeypatch) -> None:
    controller, exam, folder = _setup(tmp_path, monkeypatch)
    controller._deps.score_repository.save_score(exam=exam, student_id="alice", task_code="1A", points=8.0, max_points=10.0)
    controller._deps.score_repository.save_score(exam=exam, student_id="bob", task_code="1A", points=6.0, max_points=10.0)
    scores = controller._deps.score_repository.load_scores(exam=exam)

    real_append = pdf_writer_module.append_marked_stats_page
    call_count = {"n": 0}

    def _flaky_append(pdf_path, page_pdf_bytes, *, replace_existing):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("simulated failure")
        return real_append(pdf_path, page_pdf_bytes, replace_existing=replace_existing)

    monkeypatch.setattr(
        "app.adapters.gui.ui_intent_controller_student_result_pdf_export.append_marked_stats_page", _flaky_append
    )

    updated = controller.append_student_result_report_to_pdfs_immediate(
        exam=exam, student_ids=["alice", "bob"], scores=scores, chart_type="Spinnennetz", chart_scope="Pro Aufgabe"
    )

    assert updated is None
    assert _page_count(folder / "Alice.pdf") == 1
    assert _page_count(folder / "Bob.pdf") == 1
    assert _reload(controller).students[0].stats_report_appended is False
