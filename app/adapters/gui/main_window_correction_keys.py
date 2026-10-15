"""Correction keyboard: symbol shortcuts, digits into the points field, Space/Ctrl+Space, arrows in fields.

Where each key works (the bindings themselves are declared centrally in
``main_window_shortcut_table.py``; this mixin holds the handlers and the gating):

* **Symbol letters** (catalog ``MarkSymbol.shortcut``; ``t`` vs. Shift+``T`` are
  different keys), **digits**, **Space** ("Fertig korrigiert") and **Ctrl+Space**
  ("Aufgabe: alle als fertig markieren") fire on the canvas, the window and in the
  points field - never in the comment field or any other text field (the app-level
  bindings use ``allow_when_text_input=False``), and never while another native
  control that owns Space (button, combobox) has the focus (``applies_when``). The two
  "Fertig" switches bind Space/Ctrl+Space themselves (``_bind_finished_switch_hotkeys``).
* In the **points field** the same letters and Space/Ctrl+Space are bound on the
  field itself (widget binder, runs before the Entry's class bindings), so they act
  as shortcuts instead of being typed; digits are typed there as usual.
* A **digit** typed elsewhere jumps into the points field and starts a new value
  with that digit (the field's old content is replaced, like typing into the
  pre-selected field after navigation).
* **Arrow keys** move the text cursor in the comment field and never navigate from
  there; every other field of the correction keeps navigating (``_arrow_keys_stay_in_field``).
"""

from __future__ import annotations

from app.adapters.gui.local_keys import bind_widget_keys
from app.adapters.gui.main_window_correction_marker_palette import shortcut_display
from app.adapters.gui.ui_intents import UiIntent
from app.core.domain.mark_symbols import MARK_SYMBOLS

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.contracts.events import EventResult
from bw_gui.contracts.key_spec import KeySpec
from bw_gui.contracts.keybinding import UI_MODE_PREVIEW
from bw_gui.runtime import ui, widgets

SPACE = KeySpec.parse("Space")
CTRL_SPACE = KeySpec.parse("Ctrl+Space (tolerate: Shift)")
DIGITS = "0123456789"
_OWNS_SPACE = (widgets.Button, widgets.Checkbutton, widgets.Radiobutton, widgets.Combobox, ui.Button, ui.Checkbutton, ui.Radiobutton)


class MainWindowCorrectionKeysMixin:
    """Handlers and gating of the correction view's single-key shortcuts."""

    def _correction_keys_active(self) -> bool:
        """True while the correction view is shown and active."""
        return self._active_view == "correction" and self._correction_mode_active

    def _correction_hotkey_applies(self, event) -> bool:
        """``applies_when`` of the app-level hotkeys: not while a native control owning Space has the focus."""
        widget = getattr(event, "widget", None)
        if widget is None:
            widget = self.root.focus_get()
        return not isinstance(widget, _OWNS_SPACE)

    def _arrow_keys_stay_in_field(self) -> bool:
        """True if an arrow key must stay in the focused field instead of navigating.

        Outside the correction every text field keeps its arrows (as before); in the
        correction only the comment field does - the points field keeps navigating.
        Single place for the guard all arrow handlers share (`main_window_dispatch.py`).
        """
        widget = self.root.focus_get()
        if not self._is_editable_widget(widget):
            return False
        if not self._correction_keys_active():
            return True
        return widget is self._correction_comment_entry

    def _on_marker_tool_key(self, tool_key: str):
        """Symbol shortcut: make ``tool_key`` the current symbol (status line names it)."""
        if not self._correction_keys_active():
            return None
        self._set_correction_marker_tool(tool_key)
        self._status_var.set(self._correction_marker_info_var.get())
        return EventResult.HANDLED

    def _on_digit_key(self, digit: str):
        """Digit outside a text field: jump into the points field and start the value with ``digit``."""
        if not self._correction_keys_active():
            return None
        entry = self._correction_points_entry
        if str(entry.cget("state")) == "disabled":
            self._status_var.set("Fertig korrigiert – Punkte sind gesperrt (Leertaste hebt das auf).")
            return EventResult.HANDLED
        entry.focus_set()
        self._correction_points_var.set(digit)
        entry.selection_clear()
        entry.icursor(ui.END)
        return EventResult.HANDLED

    def _on_space_key(self, _event=None):
        """Space: toggle "Fertig korrigiert" of the current person (same as a click on the switch)."""
        return self._invoke_correction_switch(self._correction_finished_check)

    def _on_ctrl_space_key(self, _event=None):
        """Ctrl+Space: toggle "Aufgabe: alle als fertig markieren" (same as a click on that switch)."""
        return self._invoke_correction_switch(self._correction_finished_all_check)

    def _invoke_correction_switch(self, switch):
        """Click ``switch`` if it exists and is enabled; the key is consumed in the correction either way."""
        if not self._correction_keys_active():
            return None
        if switch is not None and str(switch.cget("state")) != "disabled":
            switch.invoke()
        return EventResult.HANDLED

    def _points_entry_hotkey_rows(self) -> list[tuple[KeySpec, str, object]]:
        """Widget-binder rows for the points field: symbol letters, Space and Ctrl+Space act as shortcuts there."""
        rows: list[tuple[KeySpec, str, object]] = [
            (KeySpec.char(symbol.shortcut), f"correction.points.tool.{symbol.key}",
             lambda _e, key=symbol.key: self._on_marker_tool_key(key))
            for symbol in MARK_SYMBOLS
        ]
        rows.append((SPACE, "correction.points.toggle_finished", self._on_space_key))
        rows.append((CTRL_SPACE, "correction.points.toggle_finished_all", self._on_ctrl_space_key))
        return rows

    def _bind_finished_switch_hotkeys(self, switch) -> None:
        """Space/Ctrl+Space on one of the two "Fertig" switches, ahead of Tk's own Space binding.

        When the points field is locked (person finished), the focus sits on the
        "Fertig korrigiert" switch (`_focus_first_input_field`). Tk's native
        ``<Key-space>`` binding of a checkbutton also fires with Ctrl held, so without
        this widget binder Ctrl+Space toggled "Fertig korrigiert" instead of "alle".
        The widget binder runs before the class binding and consumes the key, so on
        both switches Space = "Fertig korrigiert" and Ctrl+Space = "alle als fertig".
        """
        bind_widget_keys(
            switch,
            ((SPACE, "correction.switch.toggle_finished", self._on_space_key),
             (CTRL_SPACE, "correction.switch.toggle_finished_all", self._on_ctrl_space_key)),
        )

    def _register_correction_hotkeys(self, bind) -> None:
        """Declare the app-level correction hotkeys (called from the central shortcut table).

        Args:
            bind: ``self._bind_runtime_shortcut`` - one binding per symbol and per
                digit, so each handler gets its concrete symbol/digit by closure
                (bw-gui handlers receive only the ``KeyEvent``).
        """
        common = {"modes": (UI_MODE_PREVIEW,), "allow_when_text_input": False, "applies_when": self._correction_hotkey_applies}
        for symbol in MARK_SYMBOLS:
            bind(KeySpec.char(symbol.shortcut), lambda _e, key=symbol.key: self._on_marker_tool_key(key),
                 binding_id=f"correction.tool.{symbol.key}", intent=UiIntent.CORRECTION_SELECT_MARKER_TOOL,
                 description=f"Markierung: {symbol.label} ({shortcut_display(symbol.shortcut)})", **common)
        for digit in DIGITS:
            bind(KeySpec.char(digit), lambda _e, digit=digit: self._on_digit_key(digit),
                 binding_id=f"correction.digit.{digit}", intent=UiIntent.CORRECTION_DIGIT_TO_POINTS, **common)
        bind(SPACE, self._on_space_key, binding_id="correction.toggle_finished",
             intent=UiIntent.CORRECTION_TOGGLE_FINISHED, **common)
        bind(CTRL_SPACE, self._on_ctrl_space_key, binding_id="correction.toggle_finished_all",
             intent=UiIntent.CORRECTION_TOGGLE_FINISHED_ALL, **common)
