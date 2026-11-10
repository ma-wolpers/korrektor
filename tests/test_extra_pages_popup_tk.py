"""Real-Tk tests of the "Einzelseiten ansehen" popup: layout (same "A4 page pushes the bar out" bug as the old
import wizard) and its own Left/Right page keys (synthetic PDFs, synthetic key presses)."""

from __future__ import annotations

from bw_gui.testing.keys import press_key
from tk_test_support import build_pdf, settle


def _open_popup(window, tmp_path) -> None:
    """Open the popup for a synthetic exam: Anna with Einzelseiten-Bereichen on pages 2 and 3."""
    from app.core.domain.models import ExamProject, RegionAssignment, RegionBox, StudentExam, TaskDefinition, utc_now_iso

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
        students=[StudentExam(student_id="anna", display_name="Anna", pdf_filename="Anna.pdf", page_count=3)],
        regions=[
            RegionAssignment(region_id="r1", student_pdf="", page_number=1, box=RegionBox(0, 0, 10, 10), task_codes=["1A"], assigned_area_codes=["A"]),
            RegionAssignment(region_id="x2", student_pdf="Anna.pdf", page_number=2, box=RegionBox(0, 0, 10, 10), task_codes=["1A"], assigned_area_codes=["B"]),
            RegionAssignment(region_id="x3", student_pdf="Anna.pdf", page_number=3, box=RegionBox(0, 0, 10, 10), task_codes=["1A"], assigned_area_codes=["C"]),
        ],
        tasks=[TaskDefinition("1A", "1A", 2.0)],
        is_reading_complete=False,
    )
    window._student_cursor = 0
    window._open_extra_pages_popup_for_current(notify_if_missing=False)


def test_extra_pages_popup_keeps_navigation_visible_and_scrolls(korrektor_window, tmp_path):
    """Navigation stays fully visible at small heights; the page scrolls and starts at the top on page change."""
    window = korrektor_window
    try:
        _open_popup(window, tmp_path)
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
        assert "Einzelseite 2/2 | Seite 3 | Bereiche C: 1A" in window._extra_popup_info_var.get()
        assert preview.canvas.yview()[0] == 0
    finally:
        window._close_extra_popup()
        window._current_exam = None


def test_left_and_right_turn_the_popup_pages(korrektor_window, tmp_path):
    """The keys the ◀/▶ tooltips promise work in the popup, from the preview and from a button."""
    window = korrektor_window
    try:
        _open_popup(window, tmp_path)
        preview_canvas = window._extra_popup_preview.canvas
        close_button = window._extra_popup.winfo_children()[1].winfo_children()[-1]
        assert press_key(preview_canvas, "Right") is True
        assert "Einzelseite 2/2 | Seite 3" in window._extra_popup_info_var.get()
        assert press_key(close_button, "Left") is True
        assert "Einzelseite 1/2 | Seite 2" in window._extra_popup_info_var.get()
    finally:
        window._close_extra_popup()
        window._current_exam = None
