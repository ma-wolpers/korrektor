from __future__ import annotations

from app.adapters.gui.local_keys import bind_popup_table
from app.adapters.gui.ui_intents import UiIntent
from bw_gui.contracts.key_spec import KeySpec

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui

_k = KeySpec.parse


class MainWindowImportSplitInputMixin:
    """Keyboard, checkbox, section list and name field of the PDF import wizard.

    Keyboard contract (user decisions), valid while the name field has the
    focus - which it keeps, since every other wizard widget has
    ``takefocus=False`` and focus returns to it after clicks:

    - Left/Right (also with Shift): previous/next page.
    - Enter (main or keypad): split here; the name field becomes empty.
    - Shift+Enter: undo the split of the current section; the field shows the
      previous section's name again.
    - Up/Down, Page Up/Page Down (also with Shift): scroll the preview.

    Shortcuts go through bw-gui binders on the name field and the wizard
    toplevel (``local_keys.bind_popup_table``; intents in `UiIntent`). Every
    handler first checks that the session still exists: the binder gates and
    scopes shortcuts, but it is no guarantee against events that were already
    queued when the session ended.
    """

    def _install_import_split_input(self, view) -> None:
        """Bind the wizard shortcuts and the name-field trace for ``view``."""
        table = (
            (_k("Left (tolerate: Shift)"), "page_prev", UiIntent.IMPORT_SPLIT_PAGE_PREV, lambda: self._step_import_split_page(-1)),
            (_k("Right (tolerate: Shift)"), "page_next", UiIntent.IMPORT_SPLIT_PAGE_NEXT, lambda: self._step_import_split_page(1)),
            (_k("Enter"), "mark", UiIntent.IMPORT_SPLIT_MARK, self._mark_import_split_boundary),
            (_k("Shift+Enter"), "unmark", UiIntent.IMPORT_SPLIT_UNMARK, self._unmark_import_split_boundary),
            (_k("Up (tolerate: Shift)"), "scroll_up", UiIntent.IMPORT_SPLIT_SCROLL_UP, lambda: view.preview.scroll(-1)),
            (_k("Down (tolerate: Shift)"), "scroll_down", UiIntent.IMPORT_SPLIT_SCROLL_DOWN, lambda: view.preview.scroll(1)),
            (_k("PageUp (tolerate: Shift)"), "scroll_page_up", UiIntent.IMPORT_SPLIT_SCROLL_UP, lambda: view.preview.scroll(-1, "pages")),
            (_k("PageDown (tolerate: Shift)"), "scroll_page_down", UiIntent.IMPORT_SPLIT_SCROLL_DOWN, lambda: view.preview.scroll(1, "pages")),
        )
        view.binder = bind_popup_table(
            view.popup,
            view.name_entry,
            table,
            id_prefix="import_split",
            alive=lambda: self._import_split_session is not None and self._import_split_view is not None,
            hsm_contract=self._hsm_contract,
            on_dispatch=self._record_laufkern_intent_dispatch,
        )
        view.name_var.trace_add("write", self._on_import_split_name_typed)

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
