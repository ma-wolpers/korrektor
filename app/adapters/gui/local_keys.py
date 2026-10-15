"""Widget- and popup-local shortcuts over the bw-gui binders (no raw ``widget.bind``).

``bind_widget_keys``: Return/Escape etc. on one entry, text or list
(``WidgetShortcutBinder``, before the widget's class bindings). The handler's result
decides propagation exactly like the former ``widget.bind`` callbacks: ``None`` lets
the key continue (class bindings, popup and application shortcuts), ``HANDLED``
consumes it.

``bind_popup_table``: popup shortcut tables bound on the focus widget *and* on the
popup window.

The PDF-import wizard, its file-order dialog and the naming window keep keyboard
focus on one widget (name field or list). Their shortcuts must run **before** that
widget's native class bindings (otherwise e.g. ←/→ would first move the text cursor),
and they must also work while focus is elsewhere in the popup.

bw-gui's keyboard contract expresses exactly that without touching bindtags (the
former ``prefer_toplevel_bindings`` moved the toplevel tag in front of the class
tag): the same table is bound on a ``WidgetShortcutBinder`` of the focus widget
(its bindtag sits directly after the widget, before the class) and on the popup's
``WindowShortcutBinder`` (toplevel tag). With focus in the widget the widget binder
consumes the key (``HANDLED``) and the window binder never sees it; with focus
elsewhere the window binder handles it. Blocked combinations (e.g. Ctrl+←, exact
modifiers) reach neither and keep the widget's native behaviour.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from bw_gui.contracts.events import EventResult
from bw_gui.contracts.key_spec import KeySpec
from bw_gui.contracts.keybinding import UI_MODE_DIALOG, UI_MODE_EDITOR

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import WidgetShortcutBinder, WindowShortcutBinder

ENTER = KeySpec.parse("Enter (tolerate: Shift)")
ESCAPE = KeySpec.parse("Escape (tolerate: Shift)")

PopupKeyRow = tuple[KeySpec | list[KeySpec], str, str, Callable[[], object]]
_POPUP_MODES = (UI_MODE_DIALOG, UI_MODE_EDITOR)


def bind_widget_keys(widget: Any, rows: Iterable[tuple[KeySpec, str, Callable[[object], object]]]) -> WidgetShortcutBinder:
    """Bind *rows* ``(keys, binding_id, handler)`` on *widget*, active while it has text focus.

    Args:
        widget: Entry, text, list or tree that receives the key events.
        rows: ``handler(KeyEvent) -> EventResult | None``; ``binding_id`` doubles as intent.

    Returns:
        The widget binder (ends with the widget's ``<Destroy>``).
    """
    binder = WidgetShortcutBinder(widget)
    for keys, binding_id, handler in rows:
        binder.bind(keys, handler, binding_id=binding_id, intent=binding_id, allow_when_text_input=True)
    return binder


def bind_popup_table(
    popup: Any,
    focus_widget: Any,
    table: Iterable[PopupKeyRow],
    *,
    id_prefix: str,
    alive: Callable[[], bool],
    hsm_contract: Any,
    on_dispatch: Callable[..., None],
) -> tuple[WidgetShortcutBinder, WindowShortcutBinder]:
    """Bind *table* on *focus_widget* first and on *popup* second (see module docstring).

    Args:
        popup: The popup toplevel.
        focus_widget: The widget that normally holds keyboard focus in the popup.
        table: Rows ``(keys, suffix, intent, action)``; ``action()`` takes no arguments.
        id_prefix: Binding-id prefix (``f"{id_prefix}.{suffix}"``).
        alive: Returns ``False`` once the popup's session has ended; the action is
            then skipped (events can still be queued), the key is still consumed.
        hsm_contract: Validates each intent.
        on_dispatch: LaufKern dispatch tracking (``on_dispatch(intent, success=...)``).

    Returns:
        ``(widget_binder, window_binder)``; both end with the popup's ``<Destroy>``.
    """
    kwargs = {"hsm_contract": hsm_contract, "mode_provider": lambda: UI_MODE_DIALOG, "on_dispatch": on_dispatch}
    binders = (WidgetShortcutBinder(focus_widget, **kwargs), WindowShortcutBinder(popup, **kwargs))
    for keys, suffix, intent, action in table:
        for binder in binders:
            binder.bind(
                keys,
                _guarded(action, alive),
                binding_id=f"{id_prefix}.{suffix}",
                intent=intent,
                modes=_POPUP_MODES,
                allow_when_text_input=True,
            )
    return binders


def _guarded(action: Callable[[], object], alive: Callable[[], bool]) -> Callable[[object], EventResult]:
    """Wrap *action* as a key handler that is a no-op once the session has ended."""

    def _handle(_event: object) -> EventResult:
        if alive():
            action()
        return EventResult.HANDLED

    return _handle
