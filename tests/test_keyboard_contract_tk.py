"""Korrektor shortcuts on bw-gui's keyboard contract (shared `korrektor_window`, synthetic, no focus).

Key presses go through ``bw_gui.testing.keys.press_key`` (every bw-gui dispatcher
in bindtag order; the application binder sits on the ``all`` router like the former
``bind_all``). Covered: exact modifiers, letters independent of CapsLock, Entf as a
registered binding, the overview's Enter, and bug 1 (NumLock is no Alt for drags).
"""

from __future__ import annotations

from types import SimpleNamespace

from bw_gui.contracts import TkBackend, modifiers_from_state
from bw_gui.runtime.key_router import router_for
from bw_gui.testing.keys import press_key

SHIFT, CAPSLOCK, CONTROL, NUMLOCK, ALT = 0x0001, 0x0002, 0x0004, 0x0008, 0x20000


def test_no_foreign_keyboard_bindings_on_all(korrektor_window):
    assert router_for(korrektor_window.root).verify() == []


def test_ctrl_n_is_exact(korrektor_window, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(korrektor_window._controller, "create_exam", lambda: calls.append("new"))
    press_key(korrektor_window.root, "n", state=CONTROL | ALT)
    press_key(korrektor_window.root, "N", state=CONTROL | SHIFT)
    assert calls == []
    assert press_key(korrektor_window.root, "n", state=CONTROL | NUMLOCK) is False  # handler returns None
    assert calls == ["new"]


def test_ctrl_shift_d_opens_the_debug_dialog_without_capslock(korrektor_window):
    press_key(korrektor_window.root, "D", state=CONTROL | SHIFT)
    korrektor_window.update()
    try:
        assert korrektor_window._shortcut_runtime_debug_window is not None
    finally:
        if korrektor_window._shortcut_runtime_debug_window is not None:
            korrektor_window._shortcut_runtime_debug_window.destroy()
            korrektor_window._shortcut_runtime_debug_window = None
        korrektor_window.update()


def test_delete_is_a_registered_binding(korrektor_window, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(korrektor_window, "_delete_selected_region", lambda: calls.append("delete"))
    korrektor_window.root.focus_set()
    press_key(korrektor_window.root, "Delete")
    assert calls == ["delete"]
    assert "detail.delete" in {d.binding_id for d in korrektor_window._runtime_shortcuts.all()}


def test_overview_enter_opens_the_selected_exam(korrektor_window, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(korrektor_window._controller, "open_selected_exam", lambda: calls.append("open"))
    press_key(korrektor_window._tree, "Return", char="\r")
    assert calls == ["open"]


def test_numlock_is_no_alt_for_correction_drags(korrektor_window):
    """Bug 1: the former raw mask (0x0008, 0x20000) treated NumLock as Alt."""
    has_alt = korrektor_window._event_has_alt_modifier
    numlock = SimpleNamespace(start_modifiers=modifiers_from_state(NUMLOCK, TkBackend.WIN32))
    alt = SimpleNamespace(start_modifiers=modifiers_from_state(ALT | NUMLOCK, TkBackend.WIN32))
    assert has_alt(numlock) is False
    assert has_alt(alt) is True
