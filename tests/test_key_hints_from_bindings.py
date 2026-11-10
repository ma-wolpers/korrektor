"""Menus and tooltips take their keys from the bindings (one source), shown in German.

The expectations are the texts that used to be written next to the bindings;
``korrektor_window`` is the shared, synthetic main window (never shown).
"""

from __future__ import annotations

import re
from pathlib import Path

from app.adapters.gui.local_keys import ENTER, PAGE_NEXT_KEY, PAGE_PREV_KEY
from app.adapters.gui.main_window_correction_keys import CTRL_SPACE, SPACE
from app.adapters.gui.main_window_import_split_input import MARK_KEY, UNMARK_KEY
from app.adapters.gui.ui_intents import UiIntent
from bw_gui.shortcuts import compose_hover_text, humanize_shortcut

GUI = Path(__file__).resolve().parents[1] / "app" / "adapters" / "gui"
_SHORTCUT_LITERAL = re.compile(r'shortcut="[^"]+"')
_KEY_IN_LABEL = re.compile(r'label=f?"[^"]*\((?:Strg|Ctrl|Shift|Alt|Entf|Esc|Enter|F\d{1,2})\b[^"]*\)"')

_SHOWN_KEYS = {
    UiIntent.GLOBAL_CREATE_EXAM: "Strg+N",
    UiIntent.GLOBAL_EXPORT: "Strg+E",
    UiIntent.GLOBAL_UNDO: "Strg+Z",
    UiIntent.GLOBAL_REDO: "Strg+Y",
    UiIntent.GLOBAL_ESCAPE: "Esc",
    UiIntent.DETAIL_DELETE: "Entf",
    UiIntent.DETAIL_NAVIGATE_LEFT: "Links",
    UiIntent.DETAIL_NAVIGATE_RIGHT: "Rechts",
    UiIntent.CORRECTION_ZOOM_IN: "Strg++",
    UiIntent.CORRECTION_ZOOM_OUT: "Strg+-",
    UiIntent.CORRECTION_ZOOM_RESET: "Strg+0",
    UiIntent.DEBUG_RUNTIME_OVERLAY: "Strg+Shift+D",
    UiIntent.DEBUG_RUNTIME_OFFLINE: "Strg+Shift+O",
}


def test_registry_keys_match_the_former_texts(korrektor_window):
    registry = korrektor_window._runtime_shortcuts
    assert {intent: humanize_shortcut(registry.shortcut_for_intent(intent)) for intent in _SHOWN_KEYS} == _SHOWN_KEYS
    assert korrektor_window._menu_label("Neue Klausur", UiIntent.GLOBAL_CREATE_EXAM) == "Neue Klausur (Strg+N)"
    labels = [item.label for item in korrektor_window._menu_items_debug()]
    assert labels == ["Shortcut-Runtime-Debug anzeigen (Strg+Shift+D)", "Offline simulieren (Strg+Shift+O)"]


def test_tooltips_read_the_key_when_shown(korrektor_window):
    texts = {tooltip.current_text() for tooltip in korrektor_window._hover_tooltips}
    assert "Neue Klausur erstellen\nShortcut: Strg+N" in texts
    assert "Korrektur-Zoom auf 100% setzen\nShortcut: Strg+0" in texts


def test_local_key_constants_show_the_former_texts():
    shown = [humanize_shortcut(key) for key in (ENTER, SPACE, CTRL_SPACE, PAGE_PREV_KEY, PAGE_NEXT_KEY)]
    assert shown == ["Enter", "Leertaste", "Strg+Leertaste", "Links", "Rechts"]
    assert compose_hover_text("Teilen", (MARK_KEY, UNMARK_KEY)) == "Teilen\nShortcut: Enter oder Shift+Enter"


def test_no_key_names_as_text_in_menus_or_tooltips():
    hits = [
        f"{path.name}:{number}: {line.strip()}"
        for path in sorted(GUI.rglob("*.py"))
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if _SHORTCUT_LITERAL.search(line) or _KEY_IN_LABEL.search(line)
    ]
    assert hits == []
