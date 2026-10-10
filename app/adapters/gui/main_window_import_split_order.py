from __future__ import annotations

from app.adapters.gui.dialog_services import messagebox
from app.adapters.gui.import_split_ordering import move_item
from app.adapters.gui.import_split_session import ImportSplitPending, SplitCompleteCallback
from app.adapters.gui.main_window_import_split_input import prefer_toplevel_bindings
from app.adapters.gui.ui_intents import UiIntent
from app.infrastructure.pdf.pdf_sources import PdfSourceInfo
from bw_gui.contracts import EventResult, Key, KeySpec, Mod
from bw_gui.contracts.keybinding import UI_MODE_DIALOG, UI_MODE_EDITOR

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import WindowShortcutBinder, ui, widgets


class MainWindowImportSplitOrderMixin:
    """Order dialog shown before merging several PDFs (user decision: order is adjustable).

    Pending contract (same rigour as the session): `ImportSplitPending`
    exists exactly while this dialog is open. `_end_import_split_pending`
    is the single, idempotent end point and is reached from "Abbrechen",
    the window's close button, ``<Destroy>`` of the dialog itself (external
    ``destroy()``, app shutdown) and a failure while building the dialog.
    "Weiter" ends the pending phase first and only then starts the merge,
    so after *every* end of this dialog ``_import_split_pending is None``
    and a new import can be started.

    The sources shown here are already validated (`inspect_pdf_sources`),
    so the page counts are reliable. They all come from one file dialog,
    i.e. one folder - identical file names from different folders are not
    possible there and are deliberately not disambiguated.
    """

    def _open_import_split_order_popup(
        self, infos: list[PdfSourceInfo], on_split_complete: SplitCompleteCallback | None
    ) -> bool:
        """Show the order dialog for ``infos`` (initially in natural filename order); True if it opened."""
        pending = ImportSplitPending(infos=list(infos), on_split_complete=on_split_complete)
        self._import_split_pending = pending
        try:
            self._build_import_split_order_popup(pending)
        except Exception as exc:
            self._end_import_split_pending()
            messagebox.showerror("PDF-Reihenfolge konnte nicht geöffnet werden", str(exc))
            return False
        return True

    def _build_import_split_order_popup(self, pending: ImportSplitPending) -> None:
        """Build the dialog: file list with page counts, ▲/▼, "Weiter", "Abbrechen"."""
        popup = ui.Toplevel(self.root)
        popup.title("PDFs zusammenführen: Reihenfolge")
        popup.transient(self.root)
        pending.popup = popup
        self._register_popup_window(popup)
        popup.protocol("WM_DELETE_WINDOW", self._end_import_split_pending)
        popup.bind("<Destroy>", self._on_import_split_order_destroyed, add="+")

        body = widgets.Frame(popup, padding=12)
        body.pack(fill=ui.BOTH, expand=True)
        widgets.Label(
            body,
            text="In dieser Reihenfolge werden die PDFs zu einem Dokument zusammengeführt (Strg+↑/↓ verschiebt):",
            style="Muted.TLabel",
        ).pack(anchor=ui.W)
        row = widgets.Frame(body)
        row.pack(fill=ui.BOTH, expand=True, pady=(8, 0))
        moves = widgets.Frame(row)
        moves.pack(side=ui.RIGHT, fill=ui.Y, padx=(8, 0))
        widgets.Button(moves, text="▲", style="SecondaryAction.TButton", command=lambda: self._move_import_split_source(-1)).pack(
            fill=ui.X
        )
        widgets.Button(moves, text="▼", style="SecondaryAction.TButton", command=lambda: self._move_import_split_source(1)).pack(
            fill=ui.X, pady=(6, 0)
        )
        listbox = ui.Listbox(row, height=min(12, max(4, len(pending.infos))), width=48, exportselection=False)
        listbox.pack(side=ui.LEFT, fill=ui.BOTH, expand=True)
        pending.listbox = listbox

        actions = widgets.Frame(body)
        actions.pack(fill=ui.X, pady=(12, 0))
        widgets.Button(actions, text="Weiter", style="PrimaryAction.TButton", command=self._confirm_import_split_order).pack(
            side=ui.LEFT
        )
        widgets.Button(
            actions, text="Abbrechen", style="SecondaryAction.TButton", command=self._end_import_split_pending
        ).pack(side=ui.RIGHT)

        self._install_import_split_order_keys(pending)
        self._fill_import_split_order_list(selected_index=0)
        listbox.focus_set()

    def _install_import_split_order_keys(self, pending: ImportSplitPending) -> None:
        """Ctrl+Up/Down move the selected file, Enter continues (bw-gui binder on the dialog)."""
        binder = WindowShortcutBinder(
            pending.popup,
            hsm_contract=self._hsm_contract,
            mode_provider=lambda: UI_MODE_DIALOG,
            on_dispatch=self._record_laufkern_intent_dispatch,
        )
        for keys, suffix, intent, action in (
            (KeySpec(Key.UP, {Mod.CTRL}), "order_up", UiIntent.IMPORT_SPLIT_ORDER_MOVE_UP, lambda: self._move_import_split_source(-1)),
            (KeySpec(Key.DOWN, {Mod.CTRL}), "order_down", UiIntent.IMPORT_SPLIT_ORDER_MOVE_DOWN, lambda: self._move_import_split_source(1)),
            (KeySpec(Key.ENTER), "order_confirm", UiIntent.IMPORT_SPLIT_ORDER_CONFIRM, self._confirm_import_split_order),
        ):
            binder.bind(
                keys,
                self._import_split_order_key_handler(action),
                binding_id=f"import_split.{suffix}",
                intent=intent,
                modes=(UI_MODE_DIALOG, UI_MODE_EDITOR),
                allow_when_text_input=True,
            )
        pending.binder = binder
        prefer_toplevel_bindings(pending.listbox, pending.popup)

    def _import_split_order_key_handler(self, action):
        def _handle(_event) -> EventResult:
            if self._import_split_pending is not None:
                action()
            return EventResult.HANDLED

        return _handle

    def _fill_import_split_order_list(self, *, selected_index: int) -> None:
        pending = self._import_split_pending
        if pending is None or pending.listbox is None:
            return
        listbox = pending.listbox
        listbox.delete(0, ui.END)
        for info in pending.infos:
            listbox.insert(ui.END, f"{info.path.name}  ({info.page_count} Seite{'' if info.page_count == 1 else 'n'})")
        listbox.selection_clear(0, ui.END)
        listbox.selection_set(selected_index)
        listbox.activate(selected_index)
        listbox.see(selected_index)

    def _move_import_split_source(self, delta: int) -> None:
        """▲/▼ and Ctrl+Up/Down: move the selected file one position (non-mutating `move_item`)."""
        pending = self._import_split_pending
        if pending is None or pending.listbox is None:
            return
        selection = pending.listbox.curselection()
        if not selection:
            return
        pending.infos, new_index = move_item(pending.infos, int(selection[0]), delta)
        self._fill_import_split_order_list(selected_index=new_index)

    def _confirm_import_split_order(self) -> None:
        """"Weiter": end the pending phase, then merge in the chosen order and open the wizard."""
        pending = self._import_split_pending
        if pending is None:
            return
        paths = [info.path for info in pending.infos]
        callback = pending.on_split_complete
        self._end_import_split_pending()
        self._start_import_split_session(paths, callback)

    def _end_import_split_pending(self) -> None:
        """Single, idempotent end of the order dialog: clear the pending state, unregister, destroy."""
        pending = self._import_split_pending
        self._import_split_pending = None
        if pending is not None:
            self._destroy_import_split_window(pending.popup)

    def _on_import_split_order_destroyed(self, event) -> None:
        """``<Destroy>`` on the order dialog itself (children are ignored): end the pending phase."""
        pending = self._import_split_pending
        if pending is None or event.widget is not pending.popup:
            return
        self._end_import_split_pending()
