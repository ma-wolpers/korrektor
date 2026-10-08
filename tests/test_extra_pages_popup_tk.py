"""Real-Tk test of the Extraseiten popup layout (same "A4 page pushes the bar out" bug as the old import wizard)."""

from __future__ import annotations

from tk_test_support import build_pdf, settle


def test_extra_pages_popup_keeps_navigation_visible_and_scrolls(korrektor_window, tmp_path):
    """Navigation stays fully visible at small heights; the page scrolls and starts at the top on page change."""
    window = korrektor_window
    from app.core.domain.models import ExamProject, StudentExam, utc_now_iso

    folder = tmp_path / "exam"
    folder.mkdir()
    build_pdf(folder / "Anna.pdf", 3, "E")
    now = utc_now_iso()
    window._current_exam = ExamProject(
        exam_id="exam-1",
        exam_name="Mathe",
        folder_path=str(folder),
        created_at=now,
        updated_at=now,
        standard_page_count=1,
        students=[StudentExam(student_id="anna", display_name="Anna", pdf_filename="Anna.pdf", page_count=3, extra_pages=[2, 3])],
        regions=[],
        extra_page_assignments=[],
        person_area_completions=[],
        is_reading_complete=False,
    )
    window._student_cursor = 0
    try:
        window._open_extra_pages_popup_for_current(notify_if_missing=False)
        popup = window._extra_popup
        preview = window._extra_popup_preview
        settle(window, 200)
        nav_buttons = [child for child in popup.winfo_children()[1].winfo_children()]
        for height in (320, 600):
            popup.geometry(f"420x{height}")
            settle(window, 200)
            for widget in nav_buttons:
                y = widget.winfo_rooty() - popup.winfo_rooty()
                assert widget.winfo_ismapped() and y + widget.winfo_height() <= popup.winfo_height()
        preview.scroll(2, "pages")
        window.update()
        assert preview.canvas.yview()[0] > 0
        window._change_extra_popup_page(1)
        window.update()
        assert "Extraseite 2/2 | Seite 3" in window._extra_popup_info_var.get()
        assert preview.canvas.yview()[0] == 0
    finally:
        window._close_extra_popup()
        window._current_exam = None
