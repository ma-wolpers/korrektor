"""Correction navigation: task/person dropdowns, saving before every switch (synthetic data, shared `korrektor_window`)."""

from __future__ import annotations

import pytest
from test_correction_segments_tk import correction  # noqa: F401  (fixture)
from tk_test_support import settle

from bw_gui.runtime import combobox_selection


def _pick(dropdown, key) -> None:
    """Pick ``key`` like a user would (the bw-gui pick handler runs synchronously)."""
    combobox_selection.set_index(dropdown.widget, dropdown.keys.index(key), notify=True)


def _saved(window, student_id: str, code: str) -> tuple[str | None, str | None]:
    """``(points, comment)`` stored for ``student_id``/``code``."""
    exam = window._current_exam
    controller = window._controller
    return (
        controller.load_saved_points(exam=exam, student_id=student_id, task_code=code),
        controller.load_saved_comment(exam=exam, student_id=student_id, task_code=code),
    )


def test_dropdowns_show_start_state(correction):
    window = correction
    assert window._correction_task_dropdown.keys == ("1A", "1B", "2A")
    assert window._correction_task_dropdown.selected_key == "1A"
    assert window._correction_student_dropdown.keys == ("anna", "ben")
    assert window._correction_student_dropdown.selected_key == "anna"


def test_task_pick_saves_old_task_and_leaves_new_task_untouched(correction):
    """Regression: the pick used to save the old task's points onto the newly picked task."""
    window = correction
    window._correction_points_var.set("1,5")
    window._correction_comment_var.set("gut")
    _pick(window._correction_task_dropdown, "1B")

    assert window._selected_correction_task()[0] == "1B"
    assert _saved(window, "anna", "1A") == ("1.50", "gut")
    assert _saved(window, "anna", "1B")[0] in (None, "")
    assert window._correction_points_var.get() == ""

    _pick(window._correction_task_dropdown, "1A")
    assert window._correction_points_var.get() == "1.50"
    assert window._correction_comment_var.get() == "gut"


def test_person_pick_saves_old_person_and_loads_new(correction):
    window = correction
    window._correction_points_var.set("2")
    window._correction_comment_var.set("Anna-Kommentar")
    _pick(window._correction_student_dropdown, "ben")

    assert window._current_correction_student().student_id == "ben"
    assert _saved(window, "anna", "1A")[1] == "Anna-Kommentar"
    assert _saved(window, "ben", "1A")[0] in (None, "")
    assert window._correction_comment_var.get() == ""
    assert window._correction_info_var.get().count("Ben") == 1


def test_arrow_moves_keep_dropdowns_in_sync_and_old_value_stays_pickable(correction):
    """Regression: after ↓ the combo still remembered 1A, so picking 1A again was swallowed."""
    window = correction
    window._cycle_correction_task(1)
    assert window._correction_task_dropdown.selected_key == "1B"
    combo = window._correction_task_dropdown.widget
    combo.current(0)
    combo.event_generate("<<ComboboxSelected>>")
    assert window._selected_correction_task()[0] == "1A"

    window._change_correction_student(1)
    assert window._correction_student_dropdown.selected_key == "ben"
    window._change_correction_student(1)  # wraps around
    assert window._correction_student_dropdown.selected_key == "anna"


def test_picking_current_entry_changes_nothing(correction, monkeypatch):
    window = correction
    calls: list[str] = []
    monkeypatch.setattr(window, "_on_correction_task_switched", lambda: calls.append("switched"))
    window._go_to_correction_task("1A")
    assert calls == []


def test_rename_during_correction_updates_person_labels(correction):
    window = correction
    window._current_exam.students[1].display_name = "Benjamin"
    window._refresh_correction_nav_dropdowns()
    assert "Benjamin" in window._correction_student_dropdown.widget.cget("values")
    assert window._correction_student_dropdown.selected_key == "anna"


@pytest.mark.parametrize("delta", [1, -1])
def test_main_task_jump_saves_before_switching(correction, delta):
    window = correction
    window._correction_comment_var.set("vor Sprung")
    window._cycle_correction_main_task(delta)
    assert window._selected_correction_task()[0] == "2A"
    assert _saved(window, "anna", "1A")[1] == "vor Sprung"
    assert window._correction_task_dropdown.selected_key == "2A"


def _zoomed(window, percent: int = 240):
    """Make the preview taller than the canvas, so there is something to scroll."""
    window._correction_zoom_percent = percent
    window._render_correction_preview()
    settle(window, 50)
    first, last = window._correction_canvas.yview()
    assert last - first < 0.95, "preview must be scrollable for this test"
    return window._correction_canvas


def test_person_switch_keeps_the_scroll_position(correction):
    window = correction
    window._go_to_correction_task("1B")  # same single region for both people
    canvas = _zoomed(window)
    canvas.yview_moveto(0.2)
    settle(window, 20)
    before = canvas.yview()
    window._change_correction_student(1)
    settle(window, 20)
    assert canvas.yview() == pytest.approx(before, abs=0.01)


def test_person_switch_at_the_bottom_stays_at_the_bottom(correction):
    window = correction
    canvas = _zoomed(window)  # task 1A: Anna has two regions, Ben one (different heights)
    canvas.yview_moveto(1.0)
    settle(window, 20)
    window._change_correction_student(1)
    settle(window, 20)
    assert canvas.yview()[1] == pytest.approx(1.0, abs=0.001)
    canvas.yview_moveto(1.0)
    window._change_correction_student(1)  # back to Anna, taller: jumps to her bottom too
    settle(window, 20)
    assert canvas.yview()[1] == pytest.approx(1.0, abs=0.001) and canvas.yview()[0] > 0.0


def test_everything_visible_counts_as_bottom(correction):
    window = correction
    window._correction_zoom_percent = 10  # everything fits: yview == (0, 1)
    window._render_correction_preview()
    settle(window, 50)
    assert window._correction_canvas.yview() == pytest.approx((0.0, 1.0))
    window._correction_zoom_percent = 240
    window._change_correction_student(1)  # renders zoomed: taller than the canvas -> bottom
    settle(window, 20)
    first, last = window._correction_canvas.yview()
    assert last == pytest.approx(1.0, abs=0.001) and first > 0.0


def test_top_or_middle_is_not_forced_to_the_bottom(correction):
    window = correction
    canvas = _zoomed(window)
    canvas.yview_moveto(0.0)
    settle(window, 20)
    window._change_correction_student(1)
    settle(window, 20)
    assert canvas.yview()[0] == pytest.approx(0.0)


def test_bonus_task_is_marked_in_the_dropdown_and_the_max_label(correction):
    window = correction
    window._current_exam.tasks[2].is_bonus = True
    try:
        window._refresh_correction_nav_dropdowns()
        labels = tuple(window._correction_task_dropdown.widget.cget("values"))
        assert labels == ("1A (2 P.)", "1B (1 P.)", "2A (3 P., Bonus)")
        window._go_to_correction_task("2A")
        assert window._correction_max_points_var.get() == "Max: 3 (Bonus)"
        window._go_to_correction_task("1A")
        assert window._correction_max_points_var.get() == "Max: 2"
    finally:
        window._current_exam.tasks[2].is_bonus = False


def test_leaving_an_untouched_task_does_not_score_it_as_zero(correction):
    """Regression: every switch saved an empty points field as 0, so merely paging through scored tasks."""
    window = correction
    window._cycle_correction_task(1)
    window._cycle_correction_task(1)
    window._cycle_correction_task(-1)
    assert window._controller.load_scores_for_exam(exam=window._current_exam).get("anna", {}) == {}
