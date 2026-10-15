"""Correction keyboard: symbol letters, digits, Space/Ctrl+Space, arrows - and nothing of it in the comment field."""

from __future__ import annotations

import pytest
from test_correction_segments_tk import correction  # noqa: F401  (fixture)
from tk_test_support import FOCUS_ONLY

from app.core.domain.mark_symbols import MARK_SYMBOLS, SYMBOL_BY_KEY
from bw_gui.testing.keys import press_key

SHIFT, CAPS_LOCK, CONTROL = 0x1, 0x2, 0x4


def _press(widget, char: str, state: int = 0) -> bool:
    """A printable key as Tk reports it (keysym = char for letters/digits)."""
    return press_key(widget, char, char=char, state=state)


def test_no_shortcut_conflicts(correction):
    assert correction._runtime_shortcuts.find_conflicts() == []


@pytest.mark.parametrize("symbol", MARK_SYMBOLS, ids=lambda s: s.key)
def test_every_symbol_letter_selects_its_symbol_on_the_canvas(correction, symbol):
    window = correction
    window._set_correction_marker_tool("check" if symbol.key != "check" else "wrong")
    state = SHIFT if symbol.shortcut.isupper() else 0
    assert _press(window._correction_canvas, symbol.shortcut.lower() if state else symbol.shortcut, state)
    assert window._correction_marker_tool_key == symbol.key


def test_t_and_shift_t_differ_and_caps_lock_does_not_count(correction):
    window = correction
    canvas = window._correction_canvas
    assert _press(canvas, "T", SHIFT) and window._correction_marker_tool_key == "swap_v"
    assert _press(canvas, "t") and window._correction_marker_tool_key == "swap_h"
    window._set_correction_marker_tool("check")
    assert _press(canvas, "T", CAPS_LOCK) and window._correction_marker_tool_key == "swap_h"


def test_letters_in_the_points_field_choose_the_symbol_and_are_not_typed(correction):
    window = correction
    window._correction_points_var.set("1")
    assert _press(window._correction_points_entry, "f")
    assert window._correction_marker_tool_key == "wrong"
    assert window._correction_points_var.get() == "1"


def test_digit_outside_a_field_starts_a_new_points_value(correction):
    window = correction
    window._correction_points_var.set("12")
    assert _press(window._correction_canvas, "7")
    assert window._correction_points_var.get() == "7"


def test_nothing_fires_in_the_comment_field(correction, monkeypatch):
    window = correction
    clicks = []
    monkeypatch.setattr(window._correction_finished_check, "invoke", lambda: clicks.append("finished"))
    monkeypatch.setattr(window._correction_finished_all_check, "invoke", lambda: clicks.append("all"))
    window._set_correction_marker_tool("check")
    window._correction_points_var.set("3")
    comment = window._correction_comment_entry

    assert not _press(comment, "f")
    assert not _press(comment, "5")
    assert not press_key(comment, "space", char=" ")
    assert not press_key(comment, "space", char=" ", state=CONTROL)
    assert window._correction_marker_tool_key == "check"
    assert window._correction_points_var.get() == "3"
    assert clicks == []


def test_space_toggles_finished_and_ctrl_space_toggles_all(correction, monkeypatch):
    window = correction
    clicks = []
    monkeypatch.setattr(window._correction_finished_check, "invoke", lambda: clicks.append("finished"))
    monkeypatch.setattr(window._correction_finished_all_check, "invoke", lambda: clicks.append("all"))
    window._correction_finished_check.configure(state="normal")
    window._correction_finished_all_check.configure(state="normal")

    assert press_key(window._correction_canvas, "space", char=" ")
    assert press_key(window._correction_points_entry, "space", char=" ")
    assert press_key(window._correction_canvas, "space", char=" ", state=CONTROL)
    assert press_key(window._correction_points_entry, "space", char=" ", state=CONTROL | SHIFT)
    assert clicks == ["finished", "finished", "all", "all"]


def _record_switch_clicks(window, monkeypatch) -> list[str]:
    clicks: list[str] = []
    monkeypatch.setattr(window._correction_finished_check, "invoke", lambda: clicks.append("finished"))
    monkeypatch.setattr(window._correction_finished_all_check, "invoke", lambda: clicks.append("all"))
    window._correction_finished_check.configure(state="normal")
    window._correction_finished_all_check.configure(state="normal")
    return clicks


@pytest.mark.parametrize("focused", ["_correction_finished_check", "_correction_finished_all_check"])
def test_ctrl_space_on_a_focused_fertig_switch_is_the_all_shortcut(correction, monkeypatch, focused):
    """Ctrl+Space reaches the app shortcut on a focused switch (bw-gui toggles react to plain Space only);
    plain Space stays with the focused switch itself (native activation, not the app binder)."""
    window = correction
    clicks = _record_switch_clicks(window, monkeypatch)
    switch = getattr(window, focused)
    assert press_key(switch, "space", char=" ", state=CONTROL)
    assert not press_key(switch, "space", char=" ")
    assert clicks == ["all"]


def test_ctrl_space_does_nothing_when_the_all_switch_is_locked(correction, monkeypatch):
    window = correction
    clicks = _record_switch_clicks(window, monkeypatch)
    window._correction_finished_all_check.configure(state="disabled")
    assert press_key(window._correction_finished_check, "space", char=" ", state=CONTROL)
    assert clicks == []


def test_space_and_ctrl_space_on_an_ordinary_focused_button_stay_native(correction, monkeypatch):
    """Tk activates a focused ttk.Button on Space and on Ctrl+Space; the app shortcuts step aside."""
    window = correction
    clicks = _record_switch_clicks(window, monkeypatch)
    button = window._marker_palette_buttons["check"]
    assert not press_key(button, "space", char=" ")
    assert not press_key(button, "space", char=" ", state=CONTROL)
    assert clicks == []


def test_locked_points_field_puts_the_focus_on_the_preview_not_on_the_switch(correction, monkeypatch):
    window = correction
    focused: list[str] = []
    monkeypatch.setattr(window._correction_canvas, "focus_set", lambda: focused.append("canvas"))
    monkeypatch.setattr(window._correction_finished_check, "focus_set", lambda: focused.append("switch"))
    window._correction_points_entry.configure(state="disabled")
    try:
        window._focus_first_input_field()
    finally:
        window._correction_points_entry.configure(state="normal")
    assert focused == ["canvas"]


@FOCUS_ONLY
def test_real_ctrl_space_with_focus_on_the_fertig_switch_toggles_only_all(correction, monkeypatch):
    """End to end with real Tk events: the native switch binding and the app shortcut together."""
    window = correction
    switch = window._correction_finished_check
    window.root.deiconify()
    window.root.update()
    # Move the focus first and let its side effects settle: leaving the points field
    # saves and refreshes the completion controls (locks "alle", rewrites the variable).
    switch.focus_force()
    window.root.update()
    if window.root.focus_get() is not switch:
        pytest.skip("no OS keyboard focus available")
    clicks = _record_switch_clicks(window, monkeypatch)
    # Tk's native activation flips the switch's display variable (it never calls the
    # monkeypatched Python `invoke`), so a native toggle shows up as "native-finished".
    trace = switch._display.trace_add("write", lambda *_: clicks.append("native-finished"))
    try:
        switch.event_generate("<Control-Key-space>", when="now")
        window.root.update()
    finally:
        switch._display.trace_remove("write", trace)
    assert clicks == ["all"]


@pytest.mark.parametrize("handler", ["_on_left_key", "_on_right_key", "_on_up_key", "_on_down_key", "_on_ctrl_up_key", "_on_ctrl_down_key"])
def test_arrows_stay_in_the_comment_field_but_navigate_from_the_points_field(correction, monkeypatch, handler):
    window = correction
    start = (window._correction_cursor, window._selected_correction_task()[0])
    monkeypatch.setattr(window.root, "focus_get", lambda: window._correction_comment_entry)
    getattr(window, handler)(None)
    assert (window._correction_cursor, window._selected_correction_task()[0]) == start

    monkeypatch.setattr(window.root, "focus_get", lambda: window._correction_points_entry)
    getattr(window, handler)(None)
    assert (window._correction_cursor, window._selected_correction_task()[0]) != start


def test_symbol_tooltips_name_the_shortcut(correction):
    window = correction
    window._set_correction_marker_tool("swap_v")
    assert "Umschalt+T" in window._correction_marker_info_var.get()
    assert SYMBOL_BY_KEY["swap_v"].shortcut == "T"
