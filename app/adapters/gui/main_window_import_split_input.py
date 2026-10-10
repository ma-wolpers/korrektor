from __future__ import annotations

from collections.abc import Callable

from app.adapters.gui.ui_intents import UiIntent
from bw_gui.contracts import EventResult, Key, KeySpec, Mod
from bw_gui.contracts.keybinding import UI_MODE_DIALOG, UI_MODE_EDITOR

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import WindowShortcutBinder, ui

_WIZARD_MODES = (UI_MODE_DIALOG, UI_MODE_EDITOR)


def prefer_toplevel_bindings(widget, toplevel) -> None:
    """Move ``toplevel``'s bindtag in front of ``widget``'s class bindtag.

    Tk processes bindtags in order; by default a focused entry/listbox runs
    its *class* bindings (cursor movement, selection) before the toplevel
    tag where `WindowShortcutBinder` binds. With the toplevel first, an
    executed shortcut (``EventResult.HANDLED``) suppresses the widget's own reaction,
    while blocked combinations (binder returns ``None``, e.g. Ctrl+Left)
    still reach the class bindings. Verified for ttk.Entry on win32/Tk 8.6.15.
    """
    tags = list(widget.bindtags())
    top_tag = str(toplevel)
    if top_tag in tags:
        tags.remove(top_tag)
    tags.insert(1, top_tag)
    widget.bindtags(tuple(tags))


class MainWindowImportSplitInputMixin:
    """Keyboard, checkbox, section list and name field of the PDF import wizard.

    Keyboard contract (user decisions), valid while the name field has the
    focus - which it keeps, since every other wizard widget has
    ``takefocus=False`` and focus returns to it after clicks:

    - Left/Right (also with Shift, via ``tolerate``): previous/next page.
    - Enter / keypad Enter (both are ``Key.ENTER`` in bw-gui): split here; the
      name field becomes empty.
    - Shift+Enter: undo the split of the current section; the field shows the
      previous section's name again.
    - Up/Down, Page Up/Page Down: scroll the preview.

    Shortcuts go through bw-gui's `WindowShortcutBinder` on the wizard
    toplevel (intents in `UiIntent`). Every handler first checks that the
    session still exists: the binder gates and scopes shortcuts, but it is no
    guarantee against events that were already queued when the session ended.
    """

    def _install_import_split_input(self, view) -> None:
        """Bind the wizard shortcuts and the name-field trace for ``view``."""
        binder = WindowShortcutBinder(
            view.popup,
            hsm_contract=self._hsm_contract,
            mode_provider=lambda: UI_MODE_DIALOG,
            on_dispatch=self._record_laufkern_intent_dispatch,
        )
        bindings: tuple[tuple[KeySpec, str, str, Callable[[], None]], ...] = (
            (KeySpec(Key.LEFT, tolerate={Mod.SHIFT}), "page_prev", UiIntent.IMPORT_SPLIT_PAGE_PREV, lambda: self._step_import_split_page(-1)),
            (KeySpec(Key.RIGHT, tolerate={Mod.SHIFT}), "page_next", UiIntent.IMPORT_SPLIT_PAGE_NEXT, lambda: self._step_import_split_page(1)),
            (KeySpec(Key.ENTER), "mark", UiIntent.IMPORT_SPLIT_MARK, self._mark_import_split_boundary),
            (KeySpec(Key.ENTER, {Mod.SHIFT}), "unmark", UiIntent.IMPORT_SPLIT_UNMARK, self._unmark_import_split_boundary),
            (KeySpec(Key.UP), "scroll_up", UiIntent.IMPORT_SPLIT_SCROLL_UP, lambda: view.preview.scroll(-1)),
            (KeySpec(Key.DOWN), "scroll_down", UiIntent.IMPORT_SPLIT_SCROLL_DOWN, lambda: view.preview.scroll(1)),
            (KeySpec(Key.PAGE_UP), "scroll_page_up", UiIntent.IMPORT_SPLIT_SCROLL_UP, lambda: view.preview.scroll(-1, "pages")),
            (KeySpec(Key.PAGE_DOWN), "scroll_page_down", UiIntent.IMPORT_SPLIT_SCROLL_DOWN, lambda: view.preview.scroll(1, "pages")),
        )
        for keys, suffix, intent, action in bindings:
            binder.bind(
                keys,
                self._import_split_key_handler(action),
                binding_id=f"import_split.{suffix}",
                intent=intent,
                modes=_WIZARD_MODES,
                allow_when_text_input=True,
            )
        view.binder = binder
        prefer_toplevel_bindings(view.name_entry, view.popup)
        view.name_var.trace_add("write", self._on_import_split_name_typed)

    def _import_split_key_handler(self, action: Callable[[], None]):
        """Wrap ``action`` as a key handler that is a no-op once the session has ended."""

        def _handle(_event) -> EventResult:
            if self._import_split_session is not None and self._import_split_view is not None:
                action()
            return EventResult.HANDLED

        return _handle

    def _step_import_split_page(self, delta: int) -> None:
        """◀/▶ and Left/Right: move one page (no wrap-around)."""
        session = self._import_split_session
        if session is None:
            return
        if session.step_page(delta):
            self._refresh_import_split_view(page_changed=True)
        self._focus_import_split_name_field()

    def _mark_import_split_boundary(self) -> None:
        """Enter / checkbox on: a new Abgabe starts on the current page, with an empty name."""
        session = self._import_split_session
        if session is None:
            return
        page = session.current_page
        if session.mark_boundary(page):
            self._refresh_import_split_view(reload_name=True)
        elif page == 1:
            self._flash_import_split_info("Seite 1 beginnt immer die erste Abgabe.")
        else:
            self._flash_import_split_info("Hier beginnt bereits eine Abgabe.")
        self._focus_import_split_name_field()

    def _unmark_import_split_boundary(self) -> None:
        """Shift+Enter / checkbox off: undo the split of the current section; show the previous name."""
        session = self._import_split_session
        if session is None:
            return
        if session.unmark_section_of(session.current_page):
            self._refresh_import_split_view(reload_name=True)
        else:
            self._flash_import_split_info("Die erste Abgabe beginnt immer auf Seite 1.")
        self._focus_import_split_name_field()

    def _on_import_split_boundary_selected(self, selected: bool) -> None:
        """Checkbox callback: same methods as Enter / Shift+Enter."""
        if selected:
            self._mark_import_split_boundary()
        else:
            self._unmark_import_split_boundary()

    def _on_import_split_section_selected(self, _event=None) -> None:
        """Section list click: jump to the section start (no-op for the current section - no select loop)."""
        session = self._import_split_session
        view = self._import_split_view
        if session is None or view is None:
            return
        selection = view.section_tree.selection()
        start = view.tree_start_by_iid.get(selection[0]) if selection else None
        if start is None or start == session.section_start_for_page(session.current_page):
            return
        if session.go_to_page(start):
            self._refresh_import_split_view(page_changed=True)
        self._focus_import_split_name_field()

    def _on_import_split_name_typed(self, *_args) -> None:
        """Name-field trace: store what the user typed for the current section (ignored while guarded)."""
        session = self._import_split_session
        view = self._import_split_view
        if session is None or view is None or view.suppress_name_trace:
            return
        session.set_name_for_page(session.current_page, view.name_var.get())
        self._refresh_import_split_view()

    def _show_import_split_name(self, text: str) -> None:
        """The only programmatic write to the name field: guarded so the trace does not store it."""
        view = self._import_split_view
        if view is None:
            return
        view.suppress_name_trace = True
        try:
            view.name_var.set(text)
        finally:
            view.suppress_name_trace = False
        view.name_entry.icursor(ui.END)

    def _flash_import_split_info(self, text: str) -> None:
        """Append a short note to the header line until the next refresh."""
        session = self._import_split_session
        view = self._import_split_view
        if session is not None and view is not None:
            view.info_var.set(f"{self._import_split_origin_text(session)} · {text}")

    def _focus_import_split_name_field(self) -> None:
        """Return the keyboard focus to the name field once pending events are processed."""
        view = self._import_split_view
        if view is None:
            return

        def _focus() -> None:
            try:
                if int(view.name_entry.winfo_exists()):
                    view.name_entry.focus_set()
            except Exception:
                pass

        view.popup.after_idle(_focus)
