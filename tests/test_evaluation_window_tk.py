"""Evaluation window with real Tk: overview, clicks, keys, feedback page incl. undo/redo (synthetic data)."""

from __future__ import annotations

import pytest
from tk_test_support import build_pdf, settle

from app.adapters.gui import dialog_services
from app.core.domain.grading_scale import SCALE_TYPE_SCHOOL_1_6, GradeThreshold, GradingScaleSnapshot
from app.core.domain.models import (
    ExamProject, PdfAnnotation, PersonTaskCompletion, RegionAssignment, RegionBox, StudentExam, TaskDefinition, utc_now_iso,
)
from bw_gui.testing.keys import press_key

CONTROL = 0x4


def _exam(folder) -> ExamProject:
    now = utc_now_iso()
    return ExamProject(
        exam_id="exam-evaluation", exam_name="Mathe", folder_path=str(folder), created_at=now, updated_at=now, standard_page_count=1,
        students=[StudentExam(n.lower(), n, f"{n}.pdf", 1) for n in ("Anna", "Ben", "Cara")],
        regions=[RegionAssignment("sup", "", 1, RegionBox(20, 20, 500, 400), ["1A", "1B"], ["A"])],
        tasks=[TaskDefinition("1A", "1A", 2.0), TaskDefinition("1B", "1B", 8.0)],
        person_task_completions=[PersonTaskCompletion("anna", "1A")],
        grading_scale_snapshot=GradingScaleSnapshot(
            "s", "Schule", "Mathe", "8", "X", SCALE_TYPE_SCHOOL_1_6,
            thresholds=[GradeThreshold(80.0, "1"), GradeThreshold(50.0, "2"), GradeThreshold(0.0, "3")],
        ),
        pdf_annotations=[
            PdfAnnotation("m1", "Anna.pdf", 1, "symbol", "✓", "#d62828", 50, 50, task_code="1A", region_id="sup"),
            PdfAnnotation("m2", "Ben.pdf", 1, "symbol", "✓", "#d62828", 50, 50, task_code="1A", region_id="sup"),
            PdfAnnotation("m3", "Ben.pdf", 1, "symbol", "△", "#d62828", 60, 60, task_code="1B", region_id="sup"),
        ],
    )


@pytest.fixture
def evaluation(korrektor_window, tmp_path, monkeypatch):
    window = korrektor_window
    shown: list[str] = []
    for name in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(dialog_services.messagebox, name, lambda title, text, **_: shown.append(text))
    folder = tmp_path / "exam"
    folder.mkdir()
    for name in ("Anna", "Ben", "Cara"):
        build_pdf(folder / f"{name}.pdf", 1, name)
    exam = _exam(folder)
    exam_file = window.deps.exam_repository.save_exam(exam)
    scores = window.deps.score_repository
    for student_id, task, points in (("anna", "1A", 2.0), ("anna", "1B", 8.0), ("ben", "1A", 0.0)):
        scores.save_score(exam=exam, student_id=student_id, task_code=task, points=points, max_points=2.0 if task == "1A" else 8.0)
    window.open_exam_detail(window.deps.exam_repository.load_exam(exam_file), exam_file)
    window._open_evaluation_popup()
    settle(window, 150)
    window.shown = shown
    yield window
    window._close_evaluation_popup()
    window._return_to_overview()
    window.update()


def _cell_center(tree, item: str, column: str) -> tuple[int, int]:
    x, y, width, height = tree.bbox(item, column)
    return x + width // 2, y + height // 2


def _click(tree, x: int, y: int, state: int = 0) -> None:
    tree.event_generate("<ButtonPress-1>", x=x, y=y, state=state)
    tree.event_generate("<ButtonRelease-1>", x=x, y=y, state=state)
    tree.update()


def test_overview_shows_scored_zero_unscored_grade_and_footers(evaluation):
    tree = evaluation._evaluation_overview_tree
    assert tree.item("anna", "values")[1:5] == ("2", "8", "10 / 10", "1")
    assert tree.item("ben", "values")[1:3] == ("0", "–")  # 0 points scored, 1B unscored
    assert tree.item("ben", "values")[4] == "–"  # no grade (incomplete)
    assert tree.item("footer:scored", "values")[1:3] == ("2/3", "1/3")
    assert tree.item("footer:finished", "values")[1] == "1/3"
    assert "Ohne Note: 2 (unvollständig bewertet)" in evaluation._evaluation_grades_note_var.get()


def test_real_click_on_task_header_and_on_name(evaluation):
    tree = evaluation._evaluation_overview_tree
    x, _y = _cell_center(tree, "anna", "t1")
    _click(tree, x, 5)  # header row of task column "1B"
    assert evaluation._evaluation_view == "task" and "1B" in evaluation._evaluation_task_name_var.get()
    evaluation._show_evaluation_view("overview")
    tree.update()
    before = tree.selection()
    _click(tree, *_cell_center(tree, "ben", "name"))
    assert evaluation._evaluation_view == "person" and evaluation._evaluation_person_name_var.get().startswith("Ben")
    assert tree.selection() == before


def test_ctrl_click_and_select_buttons_keep_multi_selection(evaluation):
    tree = evaluation._evaluation_overview_tree
    _click(tree, *_cell_center(tree, "anna", "t0"))
    _click(tree, *_cell_center(tree, "cara", "t0"), state=CONTROL)
    _click(tree, *_cell_center(tree, "ben", "name"), state=CONTROL)  # Ctrl on a name selects, does not navigate
    assert evaluation._evaluation_view == "overview"
    assert evaluation._evaluation_selected_ids() == ["anna", "ben", "cara"]
    _click(tree, *_cell_center(tree, "footer:avg", "t0"), state=CONTROL)
    assert evaluation._evaluation_selected_ids() == ["anna", "ben", "cara"] and "footer:avg" not in tree.selection()
    evaluation._select_all_evaluation_rows()
    assert len(tree.selection()) == 3


def test_keys_in_the_right_view_and_back_keeps_selection(evaluation):
    tree = evaluation._evaluation_overview_tree
    evaluation._select_all_evaluation_rows()
    assert not press_key(tree, "Left")  # overview: let through
    evaluation._show_evaluation_person("anna")
    assert press_key(tree, "Right")
    assert evaluation._evaluation_person_name_var.get().startswith("Ben")
    assert press_key(tree, "BackSpace")
    assert evaluation._evaluation_view == "overview" and len(tree.selection()) == 3
    evaluation._show_evaluation_task("1A")
    assert press_key(tree, "Right") and "1B" in evaluation._evaluation_task_name_var.get()


def test_feedback_page_mixed_selection_and_undo_redo_refresh_the_status(evaluation):
    window = evaluation
    tree = window._evaluation_overview_tree
    window._evaluation_overview_tree.selection_set(["anna"])
    window._append_evaluation_feedback()
    assert tree.item("anna", "values")[-1] == "✓"
    window._evaluation_overview_tree.selection_set(["anna", "ben"])
    window._remove_evaluation_feedback()  # ben has no page -> skipped, named
    assert tree.item("anna", "values")[-1] == ""
    assert "1 ohne Feedbackseite übersprungen" in window._status_var.get()
    assert window._controller.undo()  # page comes back
    assert window._evaluation_overview_tree.item("anna", "values")[-1] == "✓"
    assert window._controller.redo()
    assert window._evaluation_overview_tree.item("anna", "values")[-1] == ""


def test_feedback_page_error_keeps_the_status(evaluation, monkeypatch):
    def _boom(*_args, **_kwargs):
        raise OSError("Datei gesperrt")

    monkeypatch.setattr("app.adapters.gui.ui_intent_controller_student_result_pdf_export.append_marked_stats_page", _boom)
    evaluation._evaluation_overview_tree.selection_set(["anna", "ben"])
    evaluation._append_evaluation_feedback()
    assert evaluation._evaluation_overview_tree.item("anna", "values")[-1] == ""
    assert any("Datei gesperrt" in text for text in evaluation.shown)


def test_task_view_and_symbols_view(evaluation):
    evaluation._show_evaluation_task("1A")
    task_tree = evaluation._evaluation_task_tree
    assert [task_tree.item(item, "values")[1] for item in task_tree.get_children()] == ["2 / 2", "0 / 2", "– / 2"]
    assert [task_tree.item(item, "values")[3] for item in task_tree.get_children()] == ["✓", "", ""]
    evaluation._show_evaluation_view("symbols")
    labels = [usage.label for usage in evaluation._evaluation_symbol_usages]
    assert labels == ["Richtig", "△"]
    assert evaluation._evaluation_symbol_usages[0].submission_count == 2


def test_symbol_legend_export_from_the_symbols_view(evaluation, monkeypatch, tmp_path):
    target = tmp_path / "legende.pdf"
    monkeypatch.setattr(dialog_services.filedialog, "asksaveasfilename", lambda **_: str(target))
    evaluation._show_evaluation_view("symbols")
    assert str(evaluation._evaluation_legend_button.cget("state")) == "normal"
    evaluation._export_evaluation_legend()
    assert target.is_file()


def test_symbols_view_without_symbols_disables_the_export(evaluation):
    evaluation._current_exam.pdf_annotations = []
    evaluation._show_evaluation_view("symbols")
    assert str(evaluation._evaluation_legend_button.cget("state")) == "disabled"
    assert evaluation._controller.export_symbol_legend_for_exam(exam=evaluation._current_exam, color_hex="#000000") is None
    assert any("noch keine Symbole" in text for text in evaluation.shown)
