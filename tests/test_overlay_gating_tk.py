"""Charakterisierung: frühere Popup-Registry + Toplevel-Scan gegen den bw-gui-Overlay-Stack (echtes Tk).

Bis 2026-10-15 führte Korrektor eine eigene ``PopupPolicyRegistry``: Popups meldeten
sich beim Öffnen an (``_register_popup_window``, das Debug-Fenster als
``dialog.non_blocking``), und vor jeder Prüfung ergänzte ein Scan jedes sichtbare
direkte Kind-Toplevel des Roots als ``dialog.modal`` (Menü-Popups, Einstellungen …)
bzw. entfernte nicht mehr sichtbare. Daraus kamen zwei Entscheidungen:

* **Sperre** der Hauptfenster-Kürzel (``has_mode_blocking_popup``),
* **Escape-Ziel** aus dem Hauptfenster: das zuletzt geöffnete Popup (``active_popup``).

:class:`_FormerRegistry` konserviert genau diesen Ablauf als Referenz. Jetzt liefern
``MainWindowShortcutsMixin._shortcut_dialog_open`` (``blocking(include_menus=True)``)
und ``_escape_popup_target`` (Overlay-Stack) beides; für jede Popup-Art und für
Kombinationen müssen alt und neu übereinstimmen. Nur synthetische Fenster, keine
Klausurdaten.
"""

from __future__ import annotations

import tkinter
from types import SimpleNamespace

import pytest

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.dialogs import ScrollablePopupWindow  # noqa: E402
from bw_gui.menu.custom_menu_bar import CustomMenuBar  # noqa: E402
from bw_gui.menu.menu_types import MenuItem  # noqa: E402
from bw_gui.runtime import create_root, ui, widgets  # noqa: E402
from bw_gui.runtime.overlay_stack import unregistered_visible_toplevels  # noqa: E402
from bw_gui.widgets import HoverTooltip  # noqa: E402

from app.adapters.gui.main_window_shortcuts import MainWindowShortcutsMixin  # noqa: E402


class _FormerRegistry:
    """Referenz: frühere Registry (Stapel in Öffnungsreihenfolge) + Scan vor jeder Prüfung."""

    def __init__(self, root):
        self.root = root
        self.stack: list[tuple[str, bool]] = []  # (popup_id, blocks)

    def register(self, window, *, blocks: bool = True) -> None:
        if all(pid != str(window) for pid, _ in self.stack):
            self.stack.append((str(window), blocks))

    def sync(self) -> None:
        visible = set()
        for child in self.root.winfo_children():
            if not isinstance(child, ui.Toplevel) or str(child.state()).lower() == "withdrawn":
                continue
            visible.add(str(child))
            self.register(child)
        self.stack = [(pid, blocks) for pid, blocks in self.stack if pid in visible]

    def dialog_open(self) -> bool:
        self.sync()
        return any(blocks for _pid, blocks in self.stack)

    def escape_target(self) -> str | None:
        self.sync()
        return self.stack[-1][0] if self.stack else None


@pytest.fixture(scope="module")
def root():
    """Sichtbarer Root (transiente Popups eines versteckten Masters blieben versteckt)."""
    for attempt in range(3):
        try:
            instance = create_root()
            break
        except tkinter.TclError as exc:
            if not any(m in str(exc) for m in ("usable", "tcl_findLibrary", "init.tcl")) or attempt == 2:
                raise
    instance.geometry("300x200+30+30")
    instance.update()
    yield instance
    instance.destroy()


@pytest.fixture
def scene(root):
    host = SimpleNamespace(root=root)
    former = _FormerRegistry(root)
    opened: list[object] = []

    class Scene:
        def scrollable_popup(self):
            """Wie Auswertung/Notenschlüssel/Kategorien/Sammelexport."""
            popup = ScrollablePopupWindow(root, title="Popup", geometry="200x120", minsize=(100, 80))
            former.register(popup)
            opened.append(popup)
            return popup

        def raw_popup(self):
            """Wie Benennung/Aufteilen/Zusatzseiten: rohes Toplevel am Root."""
            window = ui.Toplevel(root)
            window.transient(root)
            MainWindowShortcutsMixin._register_popup_window(host, window)
            former.register(window)
            opened.append(window)
            return window

        def debug_window(self):
            window = ui.Toplevel(root)
            MainWindowShortcutsMixin._register_popup_window(host, window, blocking_shortcuts=False)
            former.register(window, blocks=False)
            opened.append(window)
            return window

        def menu(self):
            bar = CustomMenuBar(root, (), theme_key="mono_day")
            anchor = ui.Frame(root, width=40, height=20)
            anchor.place(x=10, y=10)
            root.update_idletasks()
            # Fokus-Watchdog für die Szene aussetzen (sonst schliesst er das Popup,
            # sobald Testfenster den Fokus zurückholen; wie bw-gui test_menu_popup_placement).
            suspended = bar._focus_watchdog_suspended()
            suspended.__enter__()
            bar.open_popup(anchor, (MenuItem(type="command", label="Eins"),), 0, "datei")
            opened.append((bar, anchor, suspended))
            return bar._popup_stack[0]

        def tooltip(self):
            label = widgets.Label(root, text="Hover")
            label.pack()
            tip = HoverTooltip(label, "Hilfe")
            root.update()
            tip._show()
            opened.append(label)
            return tip

        def check(self):
            root.update()
            new_open = MainWindowShortcutsMixin._shortcut_dialog_open(host)
            target = MainWindowShortcutsMixin._escape_popup_target(host)
            assert new_open is former.dialog_open()
            assert (str(target) if target is not None else None) == former.escape_target()
            assert unregistered_visible_toplevels(root) == []
            return new_open, (str(target) if target is not None else None)

    yield Scene()
    for item in reversed(opened):
        try:
            if isinstance(item, tuple):
                bar, anchor, suspended = item
                bar.close_popups_from_level(0)
                suspended.__exit__(None, None, None)
                anchor.destroy()
            else:
                item.destroy()
        except tkinter.TclError:
            pass
    root.update()


def test_nothing_open(scene):
    assert scene.check() == (False, None)


def test_scrollable_and_raw_popups_block_and_are_escape_targets(scene):
    popup = scene.scrollable_popup()
    assert scene.check() == (True, str(popup))
    raw = scene.raw_popup()
    assert scene.check() == (True, str(raw))


def test_debug_window_does_not_block_but_is_an_escape_target(scene):
    debug = scene.debug_window()
    assert scene.check() == (False, str(debug))


def test_menu_popup_blocks(scene):
    popup = scene.menu()
    assert scene.check() == (True, str(popup))


def test_tooltip_is_neither(scene):
    tip = scene.tooltip()
    assert scene.check() == (False, None)
    assert tip._tip is not None and tip._tip.winfo_viewable()


def test_combinations_and_closing(scene):
    debug = scene.debug_window()
    popup = scene.scrollable_popup()
    raw = scene.raw_popup()
    assert scene.check() == (True, str(raw))
    raw.destroy()
    assert scene.check() == (True, str(popup))
    popup._request_close()
    assert scene.check() == (False, str(debug))
