"""Real-Tk test of the naming window (menu "Klausur" → "Namen erfassen & umbenennen…"), synthetic data only."""

from __future__ import annotations

from tk_test_support import FOCUS_ONLY, build_pdf, settle

from app.adapters.gui import dialog_services
from app.core.domain.models import ExamProject, StudentExam, utc_now_iso


def _open_exam(window, tmp_path):
    folder = tmp_path / "exam"
    folder.mkdir()
    for name in ("Abgabe_01", "Abgabe_02"):
        build_pdf(folder / f"{name}.pdf", 1, name)
    now = utc_now_iso()
    exam = ExamProject(
        exam_id="exam-naming",
        exam_name="Mathe",
        folder_path=str(folder),
        created_at=now,
        updated_at=now,
        standard_page_count=1,
        students=[StudentExam(student_id=n.lower(), display_name=n, pdf_filename=f"{n}.pdf", page_count=1) for n in ("Abgabe_01", "Abgabe_02")],
    )
    exam_file = window.deps.exam_repository.save_exam(exam)
    window.open_exam_detail(window.deps.exam_repository.load_exam(exam_file), exam_file)
    return folder


def _drag(view, x0, y0, x1, y1):
    view.canvas.event_generate("<ButtonPress-1>", x=x0, y=y0)
    view.canvas.event_generate("<B1-Motion>", x=x1, y=y1)
    view.canvas.event_generate("<ButtonRelease-1>", x=x1, y=y1)


def test_naming_window_sets_field_captures_names_and_renames(korrektor_window, tmp_path, monkeypatch):
    window = korrektor_window
    monkeypatch.setattr(dialog_services.messagebox, "showwarning", lambda *a, **k: None)
    folder = _open_exam(window, tmp_path)
    try:
        window.open_naming_window()
        view = window._naming_window_view
        settle(window, 200)
        assert view.stage == "region" and view.stage_button.cget("text") == "Namen erfassen ▶"

        _drag(view, 10, 10, 300, 80)
        settle(window)
        region = window._current_exam.name_region
        assert region is not None and region.x1 > region.x0 > 0

        window._toggle_naming_stage()
        settle(window)
        assert view.stage == "capture"
        view.name_var.set("Anna Müller")
        window._change_naming_student(1)
        view.name_var.set("Ben")
        window._change_naming_student(1)
        assert str(view.rename_button.cget("state")) == "normal"

        window._rename_all_students()
        settle(window)
        assert sorted(student.display_name for student in window._current_exam.students) == ["Anna Müller", "Ben"]
        assert (folder / "Anna_Müller.pdf").exists() and (folder / "Ben.pdf").exists()

        view.popup.destroy()
        settle(window)
        assert window._naming_window_view is None
    finally:
        window._end_naming_window()
        window._return_to_overview()
        window.update()


@FOCUS_ONLY
def test_naming_window_keys_work_inside_the_name_field(korrektor_window, tmp_path):
    window = korrektor_window
    _open_exam(window, tmp_path)
    try:
        window.open_naming_window()
        view = window._naming_window_view
        settle(window, 200)
        _drag(view, 10, 10, 300, 80)
        window._toggle_naming_stage()
        settle(window)
        entry = view.name_entry
        entry.focus_force()
        settle(window)
        entry.delete(0, "end")
        entry.insert(0, "Anna")
        entry.event_generate("<Return>")
        settle(window)
        assert view.cursor == 1 and window._pending_student_names == {"abgabe_01": "Anna"}
        entry.focus_force()
        settle(window)
        entry.event_generate("<Left>")
        settle(window)
        assert view.cursor == 0 and view.name_var.get() == "Anna"
    finally:
        window._end_naming_window()
        window._return_to_overview()
        window.update()
