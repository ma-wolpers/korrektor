"""Real-Tk test of the Scan-Werkstatt view (synthetic data only)."""

from __future__ import annotations

import pytest
from tk_test_support import FOCUS_ONLY, build_pdf, pdf_texts, settle

from app.adapters.gui import dialog_services
from app.core.domain.models import ExamProject, StudentExam, utc_now_iso


def _open_exam(window, tmp_path):
    folder = tmp_path / "exam"
    folder.mkdir()
    build_pdf(folder / "a.pdf", 3, "A")
    build_pdf(folder / "b.pdf", 2, "B")
    now = utc_now_iso()
    exam = ExamProject(
        exam_id="exam-scan", exam_name="Mathe", folder_path=str(folder), created_at=now, updated_at=now, standard_page_count=2,
        students=[
            StudentExam(student_id="a", display_name="Anna", pdf_filename="a.pdf", page_count=3),
            StudentExam(student_id="b", display_name="Ben", pdf_filename="b.pdf", page_count=2),
        ],
    )
    exam_file = window.deps.exam_repository.save_exam(exam)
    window.open_exam_detail(window.deps.exam_repository.load_exam(exam_file), exam_file)
    return folder


def _crosshair_lines(canvas):
    return [item for item in canvas.find_all() if canvas.type(item) == "line"]


@pytest.fixture
def scan_window(korrektor_window, tmp_path, monkeypatch):
    window = korrektor_window
    monkeypatch.setattr(dialog_services.messagebox, "askyesno", lambda *a, **k: True)
    folder = _open_exam(window, tmp_path)
    window.root.geometry("1100x700")
    window._start_scan_workshop()
    settle(window, 250)
    yield window, folder
    if window._scan_session is not None:
        window._scan_session.discard()
    window._leave_scan_workshop()
    window._return_to_overview()
    window.update()


def test_crosshair_starts_centred_stays_after_click_and_navigation(scan_window):
    window, _folder = scan_window
    session, view = window._scan_session, window._scan_view
    assert session.crosshair == (0.5, 0.5) and len(_crosshair_lines(view.canvas)) == 2

    left, top, width, height = view.image_box
    view.canvas.event_generate("<ButtonPress-1>", x=int(left + width * 0.25), y=int(top + height * 0.1))
    settle(window)
    clicked = session.crosshair
    assert clicked[0] == pytest.approx(0.25, abs=0.02) and clicked[1] == pytest.approx(0.1, abs=0.02)

    window._scan_go_page(1)
    window._scan_go_student(1)
    settle(window)
    assert window._scan_session.crosshair == clicked and len(_crosshair_lines(view.canvas)) == 2
    assert "Ben" in view.info_var.get()


def test_bars_stay_visible_in_a_small_window(scan_window):
    window, _folder = scan_window
    window.root.geometry("900x420")
    settle(window, 250)
    bottom = window.root.winfo_rooty() + window.root.winfo_height()
    button = window._scan_view.delete_button
    assert button.winfo_ismapped() and button.winfo_rooty() + button.winfo_height() <= bottom


def test_apply_from_the_view_changes_the_pdf_and_keeps_the_crosshair(scan_window):
    window, folder = scan_window
    window._scan_session.set_crosshair(0.3, 0.7)
    window._scan_go_page(1)
    window._scan_toggle_delete()
    window._scan_rotate_key(1)
    assert window._scan_view.pending_var.get().startswith("Offene Änderungen: 1")

    assert window._apply_scan_workshop()
    settle(window)
    assert pdf_texts(folder / "a.pdf") == ["A 1", "A 3"]
    assert window._scan_session.crosshair == (0.3, 0.7) and not window._scan_session.changed_pdfs()
    assert [student.page_count for student in window._current_exam.students] == [2, 2]


@FOCUS_ONLY
def test_keys_navigate_rotate_and_delete(scan_window):
    window, _folder = scan_window
    canvas = window._scan_view.canvas
    canvas.focus_force()
    settle(window)
    for sequence in ("<Down>", "<Control-Right>", "<Delete>", "<Right>"):
        canvas.event_generate(sequence)
        settle(window)
    state = window._scan_session.states["a.pdf"]
    assert state.edit_for(2).rotation_deg == pytest.approx(window._scan_rotation_step_deg)
    assert state.edit_for(2).deleted and window._scan_session.student_index == 1


_CM = 72.0 / 2.54


def test_shift_buttons_and_fields(scan_window):
    window, _folder = scan_window
    assert window._scan_shift_key(1, 0) == "break"
    edit = window._scan_session.current_edit
    assert edit.offset_x_pt == pytest.approx(window._scan_shift_step_cm * _CM) and edit.rotation_deg == 0.0
    assert "Verschiebung +0.5/+0.0 cm" in window._scan_view.info_var.get()

    window._scan_view.shift_x_var.set("0")
    window._scan_view.shift_y_var.set("1,5 cm")
    window._flush_scan_shift()
    edit = window._scan_session.current_edit
    assert (edit.offset_x_pt, edit.offset_y_pt) == pytest.approx((0.0, 1.5 * _CM))
    assert window._scan_view.shift_y_var.get() == "1,5"


def test_shift_arrow_outside_the_scan_workshop_keeps_plain_arrow_behaviour(scan_window, monkeypatch):
    window, _folder = scan_window
    seen = []
    monkeypatch.setattr(window, "_on_right_key", lambda event: seen.append("right"))
    monkeypatch.setattr(window, "_active_view", "detail")

    window._on_shift_arrow_key(1, None)

    assert seen == ["right"] and window._scan_session.current_edit.rotation_deg == 0.0


@FOCUS_ONLY
def test_shift_arrow_turns_90_and_ctrl_shift_arrows_shift_without_side_effects(scan_window):
    window, _folder = scan_window
    canvas = window._scan_view.canvas
    canvas.focus_force()
    settle(window)

    canvas.event_generate("<Shift-Right>")
    settle(window)
    session = window._scan_session
    assert session.current_edit.rotation_deg == pytest.approx(90.0) and session.student_index == 0

    canvas.event_generate("<Control-Shift-Right>")
    canvas.event_generate("<Control-Shift-Down>")
    settle(window)
    edit = session.current_edit
    step = window._scan_shift_step_cm * _CM
    assert (edit.offset_x_pt, edit.offset_y_pt) == pytest.approx((step, step))
    assert edit.rotation_deg == pytest.approx(90.0) and session.student_index == 0 and session.position == 1
