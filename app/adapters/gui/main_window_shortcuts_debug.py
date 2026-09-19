from __future__ import annotations

from bw_gui.contracts.keybinding import UI_MODE_DIALOG, UI_MODE_EDITOR, UI_MODE_GLOBAL, UI_MODE_OFFLINE, UI_MODE_PREVIEW

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui, widgets


class MainWindowShortcutsDebugMixin:
    def _open_shortcut_runtime_debug_dialog(self) -> None:
        """Open compact runtime diagnostics table for keybinding evaluation."""

        if self._shortcut_runtime_debug_window is not None and int(self._shortcut_runtime_debug_window.winfo_exists()):
            self._refresh_shortcut_runtime_debug_dialog()
            self._shortcut_runtime_debug_window.deiconify()
            self._shortcut_runtime_debug_window.lift()
            self._shortcut_runtime_debug_window.focus_force()
            return

        window = ui.Toplevel(self.root)
        window.title("Shortcut Runtime Debug")
        window.geometry("960x500")
        window.minsize(800, 400)
        self._register_popup_window(window, policy_id="dialog.non_blocking")

        toolbar = widgets.Frame(window, padding=(10, 8))
        toolbar.pack(fill=ui.X)
        widgets.Label(toolbar, textvariable=self._shortcut_runtime_debug_context_var, style="Muted.TLabel").pack(
            side=ui.LEFT,
            fill=ui.X,
            expand=True,
        )
        offline_check = widgets.Checkbutton(
            toolbar,
            text="Offline simulieren",
            variable=self._shortcut_debug_offline_var,
            command=self._refresh_shortcut_runtime_debug_dialog,
        )
        offline_check.pack(side=ui.LEFT, padx=(12, 0))
        self._attach_hover_help(offline_check, label="Offline-Simulation fuer Runtime-Resolver umschalten", shortcut="Ctrl+Shift+O")

        refresh_button = widgets.Button(
            toolbar,
            text="Aktualisieren",
            style="SecondaryAction.TButton",
            command=self._refresh_shortcut_runtime_debug_dialog,
        )
        refresh_button.pack(side=ui.LEFT, padx=(8, 0))
        self._attach_hover_help(refresh_button, label="Shortcut-Runtime-Debug neu berechnen", shortcut=None)

        body = widgets.Frame(window, padding=(10, 0, 10, 8))
        body.pack(fill=ui.BOTH, expand=True)
        columns = ("mode", "key", "binding", "status", "reason")
        table = widgets.Treeview(body, columns=columns, show="headings")
        table.heading("mode", text="Mode")
        table.heading("key", text="Key")
        table.heading("binding", text="Binding")
        table.heading("status", text="Status")
        table.heading("reason", text="Reason")
        table.column("mode", width=100, anchor=ui.CENTER, stretch=False)
        table.column("key", width=130, anchor=ui.CENTER, stretch=False)
        table.column("binding", width=300, anchor=ui.W, stretch=True)
        table.column("status", width=90, anchor=ui.CENTER, stretch=False)
        table.column("reason", width=180, anchor=ui.W, stretch=True)
        table.pack(side=ui.LEFT, fill=ui.BOTH, expand=True)
        y_scroll = widgets.Scrollbar(body, orient="vertical", command=table.yview)
        y_scroll.pack(side=ui.RIGHT, fill=ui.Y)
        table.configure(yscrollcommand=y_scroll.set)

        widgets.Label(window, textvariable=self._shortcut_runtime_debug_summary_var, style="Muted.TLabel").pack(anchor=ui.W, padx=10, pady=(0, 8))

        self._shortcut_runtime_debug_window = window
        self._shortcut_runtime_debug_table = table
        window.protocol("WM_DELETE_WINDOW", self._close_shortcut_runtime_debug_dialog)
        self._refresh_shortcut_runtime_debug_dialog()

    def _close_shortcut_runtime_debug_dialog(self) -> None:
        """Destroy runtime debug dialog and clear widget references."""

        if self._shortcut_runtime_debug_window is not None and int(self._shortcut_runtime_debug_window.winfo_exists()):
            popup_id = str(self._shortcut_runtime_debug_window)
            self._popup_registry.close_popup(popup_id)
            self._tracked_popup_ids.discard(popup_id)
            self._shortcut_runtime_debug_window.destroy()
        self._shortcut_runtime_debug_window = None
        self._shortcut_runtime_debug_table = None

    def _refresh_shortcut_runtime_debug_dialog(self) -> None:
        """Refresh tabular runtime diagnostics rows and summary."""

        table = self._shortcut_runtime_debug_table
        if table is None:
            return

        context = self._build_runtime_context()
        self._shortcut_runtime_debug_context_var.set(
            f"mode={context.active_mode} | offline={context.offline} | dialog={context.dialog_open} | text-focus={context.text_input_focused}"
        )

        for item_id in table.get_children(""):
            table.delete(item_id)

        active_count = 0
        disabled_count = 0
        for mode in (UI_MODE_GLOBAL, UI_MODE_EDITOR, UI_MODE_PREVIEW, UI_MODE_DIALOG, UI_MODE_OFFLINE):
            for definition in self._runtime_shortcuts.all():
                if mode not in definition.modes and UI_MODE_GLOBAL not in definition.modes:
                    continue
                can_execute, reason = self._runtime_shortcuts.evaluate_runtime(
                    definition,
                    context,
                    active_mode_override=mode,
                )
                status = "active" if can_execute else "disabled"
                if can_execute:
                    active_count += 1
                else:
                    disabled_count += 1
                table.insert(
                    "",
                    ui.END,
                    values=(mode, definition.sequence, definition.binding_id, status, "" if can_execute else reason),
                )

        total = active_count + disabled_count
        self._shortcut_runtime_debug_summary_var.set(
            " | ".join(
                [
                    f"Bindings: {total} total",
                    f"{active_count} active",
                    f"{disabled_count} disabled",
                    self._summarize_laufkern_reachability(context=context),
                    self._summarize_laufkern_completion(),
                ]
            )
        )
