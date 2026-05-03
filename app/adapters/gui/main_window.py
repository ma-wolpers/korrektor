from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk
from typing import TYPE_CHECKING

import fitz

from app.adapters.bootstrap.wiring import GuiDependencies
from app.adapters.gui.keybinding_registry import (
    UI_MODE_DIALOG,
    UI_MODE_EDITOR,
    UI_MODE_GLOBAL,
    UI_MODE_OFFLINE,
    UI_MODE_PREVIEW,
    KeyBindingDefinition,
    KeybindingRegistry,
    KeybindingRuntimeContext,
)
from app.adapters.gui.hsm_contract import (
    ESCAPE_CLOSE_POPUP,
    ESCAPE_EXIT_INLINE_EDITOR,
    ESCAPE_POP_PARENT,
    build_ui_hsm_contract,
)
from app.adapters.gui.popup_policy import POPUP_KIND_MODAL, POPUP_KIND_NON_MODAL, PopupPolicy, PopupPolicyRegistry
from app.adapters.gui.ui_intents import UiIntent
from app.adapters.gui.view_models import ExamOverviewRow
from app.core.domain.models import ExamProject, StudentExam
from app.core.domain.progress import ProgressCalculator

if TYPE_CHECKING:
    from app.adapters.gui.ui_intent_controller import UiIntentController


class MainWindow:
    def __init__(self, root: tk.Tk, deps: GuiDependencies) -> None:
        self.root = root
        self.deps = deps
        self.root.title("Korrektor")
        self.root.geometry("1180x740")
        self.root.minsize(980, 640)

        self._rows_by_tree_id: dict[str, ExamOverviewRow] = {}
        self._controller = None
        self._correction_controls_frame: ttk.Frame | None = None
        self._in_detail_mode = False
        self._selected_region_id: str | None = None
        self._region_tree_rows: dict[str, str] = {}

        self._status_var = tk.StringVar(value="Bereit")
        self._detail_exam_file: Path | None = None
        self._current_exam: ExamProject | None = None
        self._student_cursor = 0
        self._correction_mode_active = False
        self._correction_student_indices: list[int] = []
        self._correction_cursor = 0
        self._detail_submode = "reading"

        self._reading_active = False
        self._reading_student_cursor = 0
        self._reading_page = 1
        self._reading_info_var = tk.StringVar(value="Einlesemodus: nicht aktiv")
        self._assignment_mode_var = tk.StringVar(value="quick")
        self._extra_mode_active = False
        self._extra_sequence: list[tuple[int, int]] = []
        self._extra_cursor = 0
        self._doc_cache: dict[str, fitz.Document] = {}
        self._render_photo: tk.PhotoImage | None = None
        self._x_factor = 1.0
        self._y_factor = 1.0
        self._drag_start: tuple[float, float] | None = None
        self._drag_rect_id: int | None = None
        self._popup_photo: tk.PhotoImage | None = None
        self._extra_popup: tk.Toplevel | None = None
        self._extra_popup_canvas: tk.Canvas | None = None
        self._extra_popup_info_var: tk.StringVar | None = None
        self._extra_popup_student_index: int | None = None
        self._extra_popup_cursor = 0
        self._canvas_image_id: int | None = None
        self._runtime_shortcuts = KeybindingRegistry()
        self._shortcut_debug_offline_var = tk.BooleanVar(value=False)
        self._shortcut_runtime_debug_window: tk.Toplevel | None = None
        self._shortcut_runtime_debug_table: ttk.Treeview | None = None
        self._shortcut_runtime_debug_context_var = tk.StringVar(value="")
        self._shortcut_runtime_debug_summary_var = tk.StringVar(value="")
        self._popup_registry = PopupPolicyRegistry()
        self._popup_registry.register_policy(PopupPolicy(policy_id="dialog.modal", kind=POPUP_KIND_MODAL))
        self._popup_registry.register_policy(
            PopupPolicy(
                policy_id="dialog.non_blocking",
                kind=POPUP_KIND_NON_MODAL,
                trap_focus=False,
                affects_mode=False,
            )
        )
        self._tracked_popup_ids: set[str] = set()
        self._hsm_contract = build_ui_hsm_contract(
            intents=[
                UiIntent.GLOBAL_CREATE_EXAM,
                UiIntent.GLOBAL_ESCAPE,
                UiIntent.DETAIL_NAVIGATE_LEFT,
                UiIntent.DETAIL_NAVIGATE_RIGHT,
                UiIntent.DEBUG_RUNTIME_OVERLAY,
                UiIntent.DEBUG_RUNTIME_OFFLINE,
            ]
        )

        self._build_styles()
        self._build_layout()

    def set_controller(self, controller: "UiIntentController") -> None:
        self._controller = controller
        self._bind_runtime_shortcut(
            "<Control-n>",
            lambda _event: self._controller.create_exam(),
            binding_id="global.new_exam",
            intent=UiIntent.GLOBAL_CREATE_EXAM,
            modes=(UI_MODE_GLOBAL, UI_MODE_DIALOG),
            allow_when_text_input=True,
        )
        self._bind_runtime_shortcut(
            "<Escape>",
            self._on_escape,
            binding_id="global.escape",
            intent=UiIntent.GLOBAL_ESCAPE,
            modes=(UI_MODE_GLOBAL, UI_MODE_PREVIEW, UI_MODE_DIALOG),
            allow_when_text_input=True,
        )
        self._bind_runtime_shortcut(
            "<Left>",
            self._on_left_key,
            binding_id="detail.left",
            intent=UiIntent.DETAIL_NAVIGATE_LEFT,
            modes=(UI_MODE_PREVIEW,),
        )
        self._bind_runtime_shortcut(
            "<Right>",
            self._on_right_key,
            binding_id="detail.right",
            intent=UiIntent.DETAIL_NAVIGATE_RIGHT,
            modes=(UI_MODE_PREVIEW,),
        )
        self._bind_runtime_shortcut(
            "<Control-Shift-d>",
            lambda _event: self._open_shortcut_runtime_debug_dialog(),
            binding_id="debug.runtime_overlay",
            intent=UiIntent.DEBUG_RUNTIME_OVERLAY,
            modes=(UI_MODE_GLOBAL, UI_MODE_PREVIEW, UI_MODE_DIALOG),
            allow_when_text_input=True,
        )
        self._bind_runtime_shortcut(
            "<Control-Shift-o>",
            lambda _event: self._toggle_runtime_offline(),
            binding_id="debug.runtime_offline",
            intent=UiIntent.DEBUG_RUNTIME_OFFLINE,
            modes=(UI_MODE_GLOBAL, UI_MODE_PREVIEW, UI_MODE_DIALOG),
            allow_when_text_input=True,
        )

    def start(self) -> None:
        if self._controller:
            self._controller.refresh_exam_overview()
        self.root.mainloop()

    def _register_runtime_shortcut(
        self,
        *,
        binding_id: str,
        sequence: str,
        intent: str,
        modes: tuple[str, ...],
        allow_when_text_input: bool = False,
        allow_when_offline: bool = True,
    ) -> KeyBindingDefinition:
        """Register one runtime shortcut definition in the central resolver."""

        intent_ok, _intent_reason = self._hsm_contract.validate_intent(intent)
        if not intent_ok:
            raise ValueError(f"Unknown runtime shortcut intent: {intent}")

        definition = KeyBindingDefinition(
            binding_id=binding_id,
            sequence=sequence,
            intent=intent,
            modes=modes,
            allow_when_text_input=allow_when_text_input,
            allow_when_offline=allow_when_offline,
        )
        self._runtime_shortcuts.register(definition)
        return definition

    def _sync_popup_sessions_from_windows(self) -> None:
        """Synchronize popup registry with currently visible toplevel windows."""

        visible_popup_ids: set[str] = set()
        for child in self.root.winfo_children():
            if not isinstance(child, tk.Toplevel):
                continue
            try:
                if not int(child.winfo_exists()):
                    continue
                if str(child.state()).lower() == "withdrawn":
                    continue
            except Exception:
                continue

            popup_id = str(child)
            visible_popup_ids.add(popup_id)
            if popup_id in self._tracked_popup_ids:
                continue
            title = ""
            try:
                title = str(child.title() or "")
            except Exception:
                title = ""
            self._popup_registry.open_popup(popup_id=popup_id, title=title, policy_id="dialog.modal")
            self._tracked_popup_ids.add(popup_id)

        stale_ids = self._tracked_popup_ids - visible_popup_ids
        for popup_id in tuple(stale_ids):
            self._popup_registry.close_popup(popup_id)
            self._tracked_popup_ids.discard(popup_id)

    def _register_popup_window(self, window: tk.Toplevel, *, policy_id: str = "dialog.modal") -> None:
        """Register popup window immediately in popup policy registry."""

        popup_id = str(window)
        if popup_id in self._tracked_popup_ids:
            return
        self._popup_registry.open_popup(popup_id=popup_id, title=str(window.title() or ""), policy_id=policy_id)
        self._tracked_popup_ids.add(popup_id)

    @staticmethod
    def _is_editable_widget(widget) -> bool:
        if widget is None:
            return False
        return isinstance(widget, (tk.Entry, ttk.Entry, tk.Text, ttk.Combobox, tk.Spinbox))

    def _build_runtime_context(self, event: tk.Event[tk.Misc] | None = None) -> KeybindingRuntimeContext:
        """Build runtime context for evaluating keybinding execution."""

        self._sync_popup_sessions_from_windows()
        focused_widget = getattr(event, "widget", None) or self.root.focus_get()
        text_input_focused = self._is_editable_widget(focused_widget)
        dialog_open = self._popup_registry.has_mode_blocking_popup()
        offline = bool(self._shortcut_debug_offline_var.get())

        if offline:
            active_mode = UI_MODE_OFFLINE
        elif dialog_open:
            active_mode = UI_MODE_DIALOG
        elif text_input_focused:
            active_mode = UI_MODE_EDITOR
        elif self._current_exam is not None:
            active_mode = UI_MODE_PREVIEW
        else:
            active_mode = UI_MODE_GLOBAL

        return KeybindingRuntimeContext(
            active_mode=active_mode,
            offline=offline,
            text_input_focused=text_input_focused,
            dialog_open=dialog_open,
        )

    def _bind_runtime_shortcut(
        self,
        sequence: str,
        handler,
        *,
        binding_id: str,
        intent: str,
        modes: tuple[str, ...],
        allow_when_text_input: bool = False,
        allow_when_offline: bool = True,
    ) -> None:
        """Bind one shortcut through the runtime resolver."""

        definition = self._register_runtime_shortcut(
            binding_id=binding_id,
            sequence=sequence,
            intent=intent,
            modes=modes,
            allow_when_text_input=allow_when_text_input,
            allow_when_offline=allow_when_offline,
        )

        def _wrapped(event):
            context = self._build_runtime_context(event)
            can_execute, _reason = self._runtime_shortcuts.evaluate_runtime(definition, context)
            if not can_execute:
                return None
            return handler(event)

        self.root.bind_all(sequence, _wrapped)

    def _toggle_runtime_offline(self) -> None:
        """Toggle offline simulation for runtime shortcut diagnostics."""

        self._shortcut_debug_offline_var.set(not bool(self._shortcut_debug_offline_var.get()))
        self._refresh_shortcut_runtime_debug_dialog()

    def _open_shortcut_runtime_debug_dialog(self) -> None:
        """Open compact runtime diagnostics table for keybinding evaluation."""

        if self._shortcut_runtime_debug_window is not None and int(self._shortcut_runtime_debug_window.winfo_exists()):
            self._refresh_shortcut_runtime_debug_dialog()
            self._shortcut_runtime_debug_window.deiconify()
            self._shortcut_runtime_debug_window.lift()
            self._shortcut_runtime_debug_window.focus_force()
            return

        window = tk.Toplevel(self.root)
        window.title("Shortcut Runtime Debug")
        window.geometry("960x500")
        window.minsize(800, 400)
        self._register_popup_window(window, policy_id="dialog.non_blocking")

        toolbar = ttk.Frame(window, padding=(10, 8))
        toolbar.pack(fill=tk.X)
        ttk.Label(toolbar, textvariable=self._shortcut_runtime_debug_context_var, style="Muted.TLabel").pack(
            side=tk.LEFT,
            fill=tk.X,
            expand=True,
        )
        ttk.Checkbutton(
            toolbar,
            text="Offline simulieren",
            variable=self._shortcut_debug_offline_var,
            command=self._refresh_shortcut_runtime_debug_dialog,
        ).pack(side=tk.LEFT, padx=(12, 0))
        ttk.Button(toolbar, text="Aktualisieren", style="SecondaryAction.TButton", command=self._refresh_shortcut_runtime_debug_dialog).pack(side=tk.LEFT, padx=(8, 0))

        body = ttk.Frame(window, padding=(10, 0, 10, 8))
        body.pack(fill=tk.BOTH, expand=True)
        columns = ("mode", "key", "binding", "status", "reason")
        table = ttk.Treeview(body, columns=columns, show="headings")
        table.heading("mode", text="Mode")
        table.heading("key", text="Key")
        table.heading("binding", text="Binding")
        table.heading("status", text="Status")
        table.heading("reason", text="Reason")
        table.column("mode", width=100, anchor=tk.CENTER, stretch=False)
        table.column("key", width=130, anchor=tk.CENTER, stretch=False)
        table.column("binding", width=300, anchor=tk.W, stretch=True)
        table.column("status", width=90, anchor=tk.CENTER, stretch=False)
        table.column("reason", width=180, anchor=tk.W, stretch=True)
        table.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        y_scroll = ttk.Scrollbar(body, orient="vertical", command=table.yview)
        y_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        table.configure(yscrollcommand=y_scroll.set)

        ttk.Label(window, textvariable=self._shortcut_runtime_debug_summary_var, style="Muted.TLabel").pack(anchor=tk.W, padx=10, pady=(0, 8))

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
                    tk.END,
                    values=(mode, definition.sequence, definition.binding_id, status, "" if can_execute else reason),
                )

        total = active_count + disabled_count
        self._shortcut_runtime_debug_summary_var.set(
            f"Bindings: {total} total | {active_count} active | {disabled_count} disabled"
        )

    def _build_styles(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        self.root.configure(bg="#f5f2ea")

        style.configure("App.TFrame", background="#f5f2ea")
        style.configure("Surface.TFrame", background="#fffdf8")
        style.configure("Title.TLabel", background="#f5f2ea", foreground="#2a2218", font=("Segoe UI", 18, "bold"))
        style.configure("Muted.TLabel", background="#f5f2ea", foreground="#6a5d4d", font=("Segoe UI", 10))
        style.configure("Status.TLabel", background="#f5f2ea", foreground="#4f4438", font=("Segoe UI", 10, "bold"))
        style.configure("PrimaryAction.TButton", padding=(14, 8), font=("Segoe UI", 10, "bold"))
        style.configure("SecondaryAction.TButton", padding=(12, 8), font=("Segoe UI", 10))

    def _build_layout(self) -> None:
        shell = ttk.Frame(self.root, style="App.TFrame", padding=16)
        shell.pack(fill=tk.BOTH, expand=True)

        title_row = ttk.Frame(shell, style="App.TFrame")
        title_row.pack(fill=tk.X)

        ttk.Label(title_row, text="Korrektor", style="Title.TLabel").pack(side=tk.LEFT)
        ttk.Label(title_row, text="Workflow für Einlesen und Korrektur", style="Muted.TLabel").pack(side=tk.LEFT, padx=(12, 0), pady=(8, 0))

        action_row = ttk.Frame(shell, style="App.TFrame")
        action_row.pack(fill=tk.X, pady=(14, 10))

        ttk.Button(
            action_row,
            text="Neue Klausur (Strg+N)",
            style="PrimaryAction.TButton",
            command=lambda: self._controller and self._controller.create_exam(),
        ).pack(side=tk.LEFT)
        self._back_button = ttk.Button(
            action_row,
            text="Zur Uebersicht",
            style="SecondaryAction.TButton",
            command=self._return_to_overview,
        )
        self._back_button.pack(side=tk.LEFT, padx=(10, 0))
        self._back_button.state(["disabled"])
        ttk.Button(
            action_row,
            text="Ausgewählte Klausur öffnen",
            style="SecondaryAction.TButton",
            command=lambda: self._controller and self._controller.open_selected_exam(),
        ).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(
            action_row,
            text="Einlesemodus starten",
            style="SecondaryAction.TButton",
            command=self._start_reading_mode,
        ).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(
            action_row,
            text="Extraseiten-Modus",
            style="SecondaryAction.TButton",
            command=self._start_extra_mode,
        ).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(
            action_row,
            text="Shortcut Debug",
            style="SecondaryAction.TButton",
            command=self._open_shortcut_runtime_debug_dialog,
        ).pack(side=tk.LEFT, padx=(10, 0))

        content = ttk.PanedWindow(shell, orient=tk.HORIZONTAL)
        content.pack(fill=tk.BOTH, expand=True)
        self._content_pane = content

        left = ttk.Frame(content, style="Surface.TFrame", padding=12)
        right = ttk.Frame(content, style="Surface.TFrame", padding=12)
        content.add(left, weight=2)
        content.add(right, weight=1)
        self._overview_panel = left
        self._detail_panel = right

        self._tree = ttk.Treeview(
            left,
            columns=("name", "read", "corr", "regions", "done", "complete", "flags"),
            show="headings",
            height=18,
        )
        headings = {
            "name": "Klausur",
            "read": "Einlesen %",
            "corr": "Korrektur %",
            "regions": "Bereiche",
            "done": "Korrigiert",
            "complete": "Vollständig",
            "flags": "Offen",
        }
        widths = {"name": 250, "read": 100, "corr": 100, "regions": 90, "done": 90, "complete": 100, "flags": 110}
        for key in headings:
            self._tree.heading(key, text=headings[key])
            self._tree.column(key, width=widths[key], anchor=tk.CENTER if key != "name" else tk.W)
        self._tree.pack(fill=tk.BOTH, expand=True)
        self._tree.bind("<Double-1>", lambda _event: self._controller and self._controller.open_selected_exam())
        self._tree.bind("<Return>", lambda _event: self._controller and self._controller.open_selected_exam())

        ttk.Label(right, text="Klausur-Details", style="Title.TLabel").pack(anchor=tk.W)
        self._detail_name = tk.StringVar(value="-")
        self._detail_pages = tk.StringVar(value="Standardseiten: -")
        self._detail_students = tk.StringVar(value="Schüler:innen: -")
        self._detail_regions = tk.StringVar(value="Bereiche: -")
        self._detail_status = tk.StringVar(value="Status: -")
        self._active_student = tk.StringVar(value="Aktive Person: -")

        for variable in [
            self._detail_name,
            self._detail_pages,
            self._detail_students,
            self._detail_regions,
            self._detail_status,
            self._active_student,
        ]:
            ttk.Label(right, textvariable=variable, style="Muted.TLabel").pack(anchor=tk.W, pady=4)

        self._mode_tabs = ttk.Frame(right, style="Surface.TFrame")
        self._mode_tabs.pack(fill=tk.X, pady=(8, 6))
        ttk.Button(self._mode_tabs, text="Einlesen", style="SecondaryAction.TButton", command=self._start_reading_mode).pack(side=tk.LEFT)
        ttk.Button(self._mode_tabs, text="Korrektur", style="SecondaryAction.TButton", command=self._start_correction_mode).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(self._mode_tabs, text="Extraseiten", style="SecondaryAction.TButton", command=self._start_extra_mode).pack(side=tk.LEFT, padx=(8, 0))

        self._correction_controls_frame = ttk.Frame(right, style="Surface.TFrame")
        self._correction_controls_frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Separator(self._correction_controls_frame).pack(fill=tk.X, pady=(0, 10))
        ttk.Label(self._correction_controls_frame, text="Schnellkorrektur", style="Muted.TLabel").pack(anchor=tk.W)

        correction_header = ttk.Frame(self._correction_controls_frame, style="Surface.TFrame")
        correction_header.pack(fill=tk.X, pady=(6, 6))
        ttk.Label(correction_header, text="Bereich", style="Muted.TLabel").pack(side=tk.LEFT)
        self._correction_area_var = tk.StringVar(value="A")
        self._correction_area_combo = ttk.Combobox(
            correction_header,
            textvariable=self._correction_area_var,
            state="readonly",
            width=8,
            values=("A",),
        )
        self._correction_area_combo.pack(side=tk.LEFT, padx=(8, 8))
        ttk.Button(correction_header, text="Korrekturmodus", style="SecondaryAction.TButton", command=self._start_correction_mode).pack(side=tk.LEFT)
        ttk.Button(correction_header, text="Modus beenden", style="SecondaryAction.TButton", command=self._stop_correction_mode).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(correction_header, text="Extraseiten ansehen", style="SecondaryAction.TButton", command=self._toggle_extra_pages_popup_for_current).pack(side=tk.RIGHT)

        form = ttk.Frame(self._correction_controls_frame, style="Surface.TFrame")
        form.pack(fill=tk.X, pady=(8, 0))
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="Aufgabe", style="Muted.TLabel").grid(row=0, column=0, sticky=tk.W, padx=(0, 6), pady=4)
        ttk.Label(form, text="Max", style="Muted.TLabel").grid(row=1, column=0, sticky=tk.W, padx=(0, 6), pady=4)
        ttk.Label(form, text="Erreicht", style="Muted.TLabel").grid(row=2, column=0, sticky=tk.W, padx=(0, 6), pady=4)

        self._task_code_var = tk.StringVar(value="A1")
        self._max_points_var = tk.StringVar(value="0")
        self._points_var = tk.StringVar(value="")

        self._task_code_entry = ttk.Entry(form, textvariable=self._task_code_var)
        self._max_points_entry = ttk.Entry(form, textvariable=self._max_points_var)
        self._points_entry = ttk.Entry(form, textvariable=self._points_var)

        self._task_code_entry.grid(row=0, column=1, sticky=tk.EW, pady=4)
        self._max_points_entry.grid(row=1, column=1, sticky=tk.EW, pady=4)
        self._points_entry.grid(row=2, column=1, sticky=tk.EW, pady=4)

        self._task_code_entry.bind("<Escape>", self._on_points_escape)
        self._max_points_entry.bind("<Escape>", self._on_points_escape)
        self._points_entry.bind("<FocusOut>", self._on_points_focus_out)
        self._points_entry.bind("<Return>", self._on_points_commit)
        self._points_entry.bind("<Escape>", self._on_points_escape)

        nav = ttk.Frame(self._correction_controls_frame, style="Surface.TFrame")
        nav.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(nav, text="◀ Person", style="SecondaryAction.TButton", command=lambda: self._move_student(-1)).pack(side=tk.LEFT)
        ttk.Button(nav, text="Person ▶", style="SecondaryAction.TButton", command=lambda: self._move_student(1)).pack(side=tk.LEFT, padx=(8, 0))

        self._reading_workspace_frame = ttk.Frame(right, style="Surface.TFrame")
        self._reading_workspace_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Separator(self._reading_workspace_frame).pack(fill=tk.X, pady=(12, 10))
        ttk.Label(self._reading_workspace_frame, textvariable=self._reading_info_var, style="Muted.TLabel").pack(anchor=tk.W, pady=(0, 8))

        self._reading_toolbar = ttk.Frame(self._reading_workspace_frame, style="Surface.TFrame")
        self._reading_toolbar.pack(fill=tk.X)
        ttk.Button(self._reading_toolbar, text="◀ Seite", style="SecondaryAction.TButton", command=lambda: self._change_reading_page(-1)).pack(side=tk.LEFT)
        ttk.Button(self._reading_toolbar, text="Seite ▶", style="SecondaryAction.TButton", command=lambda: self._change_reading_page(1)).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(self._reading_toolbar, text="◀ Schüler:in", style="SecondaryAction.TButton", command=lambda: self._change_reading_student(-1)).pack(side=tk.LEFT, padx=(14, 0))
        ttk.Button(self._reading_toolbar, text="Schüler:in ▶", style="SecondaryAction.TButton", command=lambda: self._change_reading_student(1)).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(self._reading_toolbar, text="Einlesen abschließen", style="PrimaryAction.TButton", command=self._finish_reading_mode).pack(side=tk.RIGHT)

        self._extra_toolbar = ttk.Frame(self._reading_workspace_frame, style="Surface.TFrame")
        self._extra_toolbar.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(self._extra_toolbar, text="◀ Extraseite", style="SecondaryAction.TButton", command=lambda: self._change_extra_page(-1)).pack(side=tk.LEFT)
        ttk.Button(self._extra_toolbar, text="Extraseite ▶", style="SecondaryAction.TButton", command=lambda: self._change_extra_page(1)).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(self._extra_toolbar, text="Bereich zuordnen", style="PrimaryAction.TButton", command=self._assign_current_extra_page).pack(side=tk.RIGHT)

        self._mode_row = ttk.Frame(self._reading_workspace_frame, style="Surface.TFrame")
        self._mode_row.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(self._mode_row, text="Zuordnung:", style="Muted.TLabel").pack(side=tk.LEFT)
        ttk.Radiobutton(self._mode_row, text="Schnell (Code:Punkte)", value="quick", variable=self._assignment_mode_var).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Radiobutton(self._mode_row, text="Formular", value="form", variable=self._assignment_mode_var).pack(side=tk.LEFT, padx=(8, 0))
        self._assignment_mode_var.trace_add("write", lambda *_args: self._refresh_task_input_mode())

        canvas_container = ttk.Frame(self._reading_workspace_frame, style="Surface.TFrame", height=360)
        canvas_container.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        canvas_container.pack_propagate(False)

        canvas_scroll_x = ttk.Scrollbar(canvas_container, orient=tk.HORIZONTAL)
        canvas_scroll_y = ttk.Scrollbar(canvas_container, orient=tk.VERTICAL)

        self._reading_canvas = tk.Canvas(
            canvas_container,
            width=520,
            height=360,
            bg="#f2ede3",
            highlightthickness=1,
            highlightbackground="#b8aa96",
            xscrollcommand=canvas_scroll_x.set,
            yscrollcommand=canvas_scroll_y.set,
        )
        canvas_scroll_x.config(command=self._reading_canvas.xview)
        canvas_scroll_y.config(command=self._reading_canvas.yview)

        canvas_scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        canvas_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        self._reading_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._reading_canvas.bind("<ButtonPress-1>", self._on_canvas_press)
        self._reading_canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self._reading_canvas.bind("<ButtonRelease-1>", self._on_canvas_release)

        self._regions_editor = ttk.Frame(self._reading_workspace_frame, style="Surface.TFrame")
        self._regions_editor.pack(fill=tk.BOTH, pady=(10, 0))

        self._regions_tree = ttk.Treeview(
            self._regions_editor,
            columns=("area", "student", "page"),
            show="headings",
            height=5,
        )
        self._regions_tree.heading("area", text="Bereich")
        self._regions_tree.heading("student", text="PDF")
        self._regions_tree.heading("page", text="Seite")
        self._regions_tree.column("area", width=80, anchor=tk.CENTER)
        self._regions_tree.column("student", width=180, anchor=tk.W)
        self._regions_tree.column("page", width=80, anchor=tk.CENTER)
        self._regions_tree.pack(fill=tk.X)
        self._regions_tree.bind("<<TreeviewSelect>>", self._on_region_selected)
        self.root.bind_all("<Delete>", self._on_delete_region_key)

        editor_head = ttk.Frame(self._regions_editor, style="Surface.TFrame")
        editor_head.pack(fill=tk.X, pady=(8, 4))
        ttk.Label(editor_head, text="Aktiver Bereich:", style="Muted.TLabel").pack(side=tk.LEFT)
        self._active_region_var = tk.StringVar(value="-")
        ttk.Label(editor_head, textvariable=self._active_region_var, style="Status.TLabel").pack(side=tk.LEFT, padx=(8, 0))

        self._quick_tasks_var = tk.StringVar(value="")
        self._quick_tasks_entry = ttk.Entry(self._regions_editor, textvariable=self._quick_tasks_var)
        self._quick_tasks_entry.pack(fill=tk.X)
        self._quick_tasks_entry.bind("<FocusOut>", lambda _e: self._save_selected_region())

        self._form_tasks_text = tk.Text(self._regions_editor, height=4, wrap="word")
        self._form_tasks_text.bind("<FocusOut>", lambda _e: self._save_selected_region())

        region_actions = ttk.Frame(self._regions_editor, style="Surface.TFrame")
        region_actions.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(region_actions, text="Speichern", style="SecondaryAction.TButton", command=self._save_selected_region).pack(side=tk.LEFT)
        ttk.Button(region_actions, text="Loeschen", style="SecondaryAction.TButton", command=self._delete_selected_region).pack(side=tk.LEFT, padx=(8, 0))

        self._refresh_task_input_mode()

        ttk.Separator(shell).pack(fill=tk.X, pady=(10, 8))
        ttk.Label(shell, textvariable=self._status_var, style="Status.TLabel").pack(anchor=tk.W)

        self._hide_correction_controls()
        self._set_detail_submode("reading")

    def render_overview_rows(self, rows: list[ExamOverviewRow]) -> None:
        self._rows_by_tree_id.clear()
        for item in self._tree.get_children():
            self._tree.delete(item)

        for row in rows:
            tree_id = self._tree.insert(
                "",
                tk.END,
                values=(
                    row.exam_name,
                    f"{row.reading_percent:.0f}",
                    f"{row.correction_percent:.0f}",
                    row.region_count,
                    row.corrected_region_count,
                    "Ja" if row.reading_complete else "Nein",
                    "Ja" if row.has_open_flags else "Nein",
                ),
            )
            self._rows_by_tree_id[tree_id] = row

        children = self._tree.get_children()
        if children:
            self._tree.selection_set(children[0])
            self._tree.focus(children[0])

        self._status_var.set(f"{len(rows)} Klausuren geladen")

    def get_selected_row(self) -> ExamOverviewRow | None:
        selection = self._tree.selection()
        if selection:
            return self._rows_by_tree_id.get(selection[0])
        children = self._tree.get_children()
        if not children:
            return None
        first = children[0]
        self._tree.selection_set(first)
        self._tree.focus(first)
        return self._rows_by_tree_id.get(first)

    def open_exam_detail(self, exam: ExamProject, exam_file: Path) -> None:
        self._detail_exam_file = exam_file
        self._current_exam = exam
        self._student_cursor = 0
        self._reading_active = False
        self._reading_student_cursor = 0
        self._reading_page = 1
        self._extra_mode_active = False
        self._extra_sequence = []
        self._extra_cursor = 0
        self._correction_mode_active = False
        self._correction_student_indices = []
        self._correction_cursor = 0

        self._refresh_correction_area_choices(exam)
        self._apply_detail_labels(exam)
        self._status_var.set(f"Detailansicht: {exam.exam_name}")
        self._reading_info_var.set("Einlesemodus: bereit")
        self._reading_canvas.delete("all")
        self._hide_correction_controls()
        self._close_extra_popup()
        self._selected_region_id = None
        self._refresh_region_tree()
        self._show_detail_mode()

    def _apply_detail_labels(self, exam: ExamProject) -> None:
        progress = ProgressCalculator().compute(exam)

        self._detail_name.set(f"Name: {exam.exam_name}")
        self._detail_pages.set(f"Standardseiten: {exam.standard_page_count}")
        self._detail_students.set(f"Schüler:innen: {len(exam.students)}")
        self._detail_regions.set(
            f"Bereiche: {progress.corrected_region_count}/{progress.region_count} korrigiert"
        )
        flags = []
        if progress.has_unassigned_extra_pages:
            flags.append("Extraseiten offen")
        if progress.has_missing_page_markings:
            flags.append("Seitenmarkierung fehlt")
        self._detail_status.set("Status: " + (", ".join(flags) if flags else "Keine offenen Warnungen"))
        self._refresh_active_student_label()

    def _on_escape(self, _event: tk.Event[tk.Misc]) -> None:
        self._sync_popup_sessions_from_windows()
        widget = self.root.focus_get()
        action = self._hsm_contract.resolve_escape_action(
            has_popup=self._popup_registry.has_active_popup(),
            has_inline_editor=isinstance(widget, (tk.Entry, ttk.Entry))
            or self._correction_mode_active
            or self._reading_active
            or self._extra_mode_active,
            has_parent_state=self._current_exam is not None,
        )

        if action == ESCAPE_CLOSE_POPUP:
            active_popup = self._popup_registry.active_popup()
            if active_popup is not None:
                popup_id = active_popup.popup_id
                for child in self.root.winfo_children():
                    if not isinstance(child, tk.Toplevel):
                        continue
                    if str(child) != popup_id:
                        continue
                    try:
                        child.destroy()
                    except Exception:
                        pass
                    break
                self._popup_registry.close_popup(popup_id)
                self._tracked_popup_ids.discard(popup_id)
                return

        if action == ESCAPE_EXIT_INLINE_EDITOR:
            if isinstance(widget, (tk.Entry, ttk.Entry)):
                self.root.focus_set()
                return

            if self._correction_mode_active:
                self._stop_correction_mode()
                return

            if self._reading_active or self._extra_mode_active:
                self._reading_active = False
                self._extra_mode_active = False
                self._extra_sequence = []
                self._close_extra_popup()
                self._reading_info_var.set("Einlesemodus: bereit")
                self._status_var.set("Einlesemodus verlassen")
                self._reading_canvas.delete("all")
                self._hide_correction_controls()
                return

        if action != ESCAPE_POP_PARENT or self._current_exam is None:
            self._status_var.set("Bereits in Gesamtübersicht")
            return

        self._current_exam = None
        self._detail_name.set("-")
        self._detail_pages.set("Standardseiten: -")
        self._detail_students.set("Schüler:innen: -")
        self._detail_regions.set("Bereiche: -")
        self._detail_status.set("Status: -")
        self._active_student.set("Aktive Person: -")
        self._reading_active = False
        self._extra_mode_active = False
        self._extra_sequence = []
        self._correction_mode_active = False
        self._correction_student_indices = []
        self._reading_info_var.set("Einlesemodus: nicht aktiv")
        self._reading_canvas.delete("all")
        self._hide_correction_controls()
        self._close_extra_popup()
        self._return_to_overview()

    def set_status(self, text: str) -> None:
        self._status_var.set(text)

    def _refresh_active_student_label(self) -> None:
        if not self._current_exam or not self._current_exam.students:
            self._active_student.set("Aktive Person: -")
            return
        if self._correction_mode_active and self._correction_student_indices:
            idx = self._correction_student_indices[self._correction_cursor]
            student = self._current_exam.students[idx]
            self._active_student.set(
                f"Aktive Person: {student.display_name} ({self._correction_cursor + 1}/{len(self._correction_student_indices)}) | Bereich {self._correction_area_var.get()}"
            )
            return

        student = self._current_exam.students[self._student_cursor]
        self._active_student.set(
            f"Aktive Person: {student.display_name} ({self._student_cursor + 1}/{len(self._current_exam.students)})"
        )

    def _on_points_focus_out(self, _event: tk.Event[tk.Misc]) -> None:
        self._commit_points_if_possible()

    def _on_points_commit(self, _event: tk.Event[tk.Misc]) -> None:
        self._commit_points_if_possible()
        self.root.focus_set()

    def _on_points_escape(self, _event: tk.Event[tk.Misc]) -> None:
        self._commit_points_if_possible()
        self.root.focus_set()

    def _move_student(self, delta: int) -> None:
        if not self._current_exam or not self._current_exam.students:
            return
        self._commit_points_if_possible()
        if self._correction_mode_active and self._correction_student_indices:
            self._correction_cursor = (self._correction_cursor + delta) % len(self._correction_student_indices)
            self._student_cursor = self._correction_student_indices[self._correction_cursor]
            self._refresh_active_student_label()
            self._focus_first_input_field()
            self._open_extra_pages_popup_for_current(notify_if_missing=False)
            return
        self._student_cursor = (self._student_cursor + delta) % len(self._current_exam.students)
        self._refresh_active_student_label()
        self._focus_first_input_field()

    def _on_left_key(self, _event: tk.Event[tk.Misc]) -> None:
        if self._detail_submode == "extra" and self._extra_mode_active:
            self._change_extra_page(-1)
            return
        if self._detail_submode == "reading" and self._reading_active:
            self._change_reading_page(-1)
            return
        self._move_student(-1)

    def _on_right_key(self, _event: tk.Event[tk.Misc]) -> None:
        if self._detail_submode == "extra" and self._extra_mode_active:
            self._change_extra_page(1)
            return
        if self._detail_submode == "reading" and self._reading_active:
            self._change_reading_page(1)
            return
        self._move_student(1)

    def _commit_points_if_possible(self) -> None:
        if not self._controller or not self._current_exam or not self._current_exam.students:
            return
        student = self._current_exam.students[self._student_cursor]
        self._controller.save_score_immediate(
            exam=self._current_exam,
            student_id=student.student_id,
            task_code=self._task_code_var.get(),
            points_text=self._points_var.get(),
            max_points_text=self._max_points_var.get(),
        )

    def _start_reading_mode(self) -> None:
        if not self._current_exam or not self._current_exam.students:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Klausur öffnen.")
            return
        self._stop_correction_mode(silent=True)
        self._extra_mode_active = False
        self._reading_active = True
        self._reading_student_cursor = 0
        self._reading_page = 1
        self._set_detail_submode("reading")
        self._render_current_reading_page()
        self._status_var.set("Einlesemodus aktiv")

    @staticmethod
    def _build_extra_sequence(exam: ExamProject) -> list[tuple[int, int]]:
        sequence: list[tuple[int, int]] = []
        for student_index, student in enumerate(exam.students):
            for page in sorted(student.extra_pages):
                sequence.append((student_index, page))
        return sequence

    def _start_extra_mode(self) -> None:
        if not self._current_exam:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Klausur öffnen.")
            return
        sequence = self._build_extra_sequence(self._current_exam)
        if not sequence:
            messagebox.showinfo("Hinweis", "Für diese Klausur sind keine Extraseiten vorhanden.")
            return

        self._reading_active = False
        self._extra_mode_active = True
        self._stop_correction_mode(silent=True)
        self._extra_sequence = sequence
        self._extra_cursor = 0
        self._set_detail_submode("extra")
        self._render_current_extra_page()
        self._status_var.set("Extraseiten-Modus aktiv")

    def _change_reading_student(self, delta: int) -> None:
        if not self._reading_active or not self._current_exam or not self._current_exam.students:
            return
        self._save_selected_region()
        self._reading_student_cursor = (self._reading_student_cursor + delta) % len(self._current_exam.students)
        student = self._current_exam.students[self._reading_student_cursor]
        self._reading_page = min(self._reading_page, max(student.page_count, 1))
        self._render_current_reading_page()

    def _change_reading_page(self, delta: int) -> None:
        if not self._reading_active:
            return
        self._save_selected_region()
        student = self._get_reading_student()
        if student is None:
            return
        new_page = self._reading_page + delta
        self._reading_page = max(1, min(student.page_count, new_page))
        self._render_current_reading_page()

    def _get_reading_student(self) -> StudentExam | None:
        if not self._current_exam or not self._current_exam.students:
            return None
        return self._current_exam.students[self._reading_student_cursor]

    def _render_current_reading_page(self) -> None:
        student = self._get_reading_student()
        if student is None or self._current_exam is None:
            return
        self._render_pdf_page(student=student, page_number=self._reading_page)

        extra_marker = " (Extraseite)" if self._reading_page > self._current_exam.standard_page_count else ""
        self._reading_info_var.set(
            f"{student.display_name} | Seite {self._reading_page}/{student.page_count}{extra_marker}"
        )

    def _draw_existing_regions(self, student_pdf: str, page_number: int) -> None:
        if not self._current_exam:
            return
        for region in self._current_exam.regions:
            if region.student_pdf != student_pdf or region.page_number != page_number:
                continue
            x0 = region.box.x0 / self._x_factor
            y0 = region.box.y0 / self._y_factor
            x1 = region.box.x1 / self._x_factor
            y1 = region.box.y1 / self._y_factor
            is_selected = region.region_id == self._selected_region_id
            rect_id = self._reading_canvas.create_rectangle(
                x0,
                y0,
                x1,
                y1,
                outline="#d17a00" if is_selected else "#0b8f59",
                width=3 if is_selected else 2,
                tags=("region", f"region:{region.region_id}"),
            )
            self._reading_canvas.tag_bind(rect_id, "<Button-1>", self._on_canvas_region_click)

    def _on_canvas_region_click(self, event: tk.Event[tk.Misc]) -> None:
        current = self._reading_canvas.find_withtag("current")
        if not current:
            return
        tags = self._reading_canvas.gettags(current[0])
        region_tag = next((tag for tag in tags if tag.startswith("region:")), None)
        if region_tag is None:
            return
        region_id = region_tag.split(":", 1)[1]
        self._select_region_by_id(region_id)
        self._render_current_reading_page()

    def _on_canvas_press(self, event: tk.Event[tk.Misc]) -> None:
        if not self._reading_active or self._extra_mode_active:
            return
        self._drag_start = (float(event.x), float(event.y))
        if self._drag_rect_id is not None:
            self._reading_canvas.delete(self._drag_rect_id)
        self._drag_rect_id = self._reading_canvas.create_rectangle(
            event.x,
            event.y,
            event.x,
            event.y,
            outline="#1f6feb",
            width=2,
        )

    def _on_canvas_drag(self, event: tk.Event[tk.Misc]) -> None:
        if self._drag_start is None or self._drag_rect_id is None:
            return
        x0, y0 = self._drag_start
        self._reading_canvas.coords(self._drag_rect_id, x0, y0, event.x, event.y)

    def _on_canvas_release(self, event: tk.Event[tk.Misc]) -> None:
        if not self._reading_active or self._extra_mode_active or self._drag_start is None:
            return
        if self._drag_rect_id is None:
            self._drag_start = None
            return

        x0, y0 = self._drag_start
        x1, y1 = float(event.x), float(event.y)
        if abs(x1 - x0) < 5 or abs(y1 - y0) < 5:
            self._reading_canvas.delete(self._drag_rect_id)
            self._drag_rect_id = None
            self._drag_start = None
            return

        student = self._get_reading_student()
        if student is None or self._current_exam is None or self._controller is None:
            return
        task_specs = self._read_task_specs_from_editor() or []
        standard_region_count = sum(1 for region in self._current_exam.regions if not region.is_extra_page)
        next_area = self._index_to_area_label(standard_region_count)

        box = (
            min(x0, x1) * self._x_factor,
            min(y0, y1) * self._y_factor,
            max(x0, x1) * self._x_factor,
            max(y0, y1) * self._y_factor,
        )

        updated = self._controller.upsert_region_immediate(
            exam=self._current_exam,
            student_pdf=student.pdf_filename,
            page_number=self._reading_page,
            box=box,
            task_specs=task_specs,
            area_codes=[next_area],
        )
        if updated is not None:
            self._current_exam = updated
            self._apply_detail_labels(updated)
            target = next(
                (
                    region.region_id
                    for region in reversed(updated.regions)
                    if region.student_pdf == student.pdf_filename and region.page_number == self._reading_page
                ),
                None,
            )
            self._refresh_region_tree()
            if target:
                self._select_region_by_id(target)

        self._render_current_reading_page()
        self._drag_rect_id = None
        self._drag_start = None

    def _finish_reading_mode(self) -> None:
        if not self._current_exam or not self._controller:
            return
        updated = self._controller.finish_reading_mode(exam=self._current_exam)
        self._current_exam = updated
        self._apply_detail_labels(updated)
        self._reading_active = False
        self._reading_info_var.set("Einlesemodus: abgeschlossen")

    def _change_extra_page(self, delta: int) -> None:
        if not self._extra_mode_active or not self._extra_sequence:
            return
        self._extra_cursor = (self._extra_cursor + delta) % len(self._extra_sequence)
        self._render_current_extra_page()

    def _render_current_extra_page(self) -> None:
        if not self._current_exam or not self._extra_sequence:
            return

        student_index, page_number = self._extra_sequence[self._extra_cursor]
        student = self._current_exam.students[student_index]
        self._render_pdf_page(student=student, page_number=page_number)

        assigned = self._areas_for_extra_page(student.pdf_filename, page_number)
        assigned_text = f" | Bereich: {','.join(assigned)}" if assigned else " | Bereich: -"
        self._reading_info_var.set(
            f"Extraseite {self._extra_cursor + 1}/{len(self._extra_sequence)} | {student.display_name} | Seite {page_number}{assigned_text}"
        )

    def _areas_for_extra_page(self, student_pdf: str, page_number: int) -> list[str]:
        if not self._current_exam:
            return []
        result: list[str] = []
        for region in self._current_exam.regions:
            if region.is_extra_page and region.student_pdf == student_pdf and region.page_number == page_number:
                for code in region.assigned_area_codes:
                    if code not in result:
                        result.append(code)
        return result

    def _assign_current_extra_page(self) -> None:
        if not self._extra_mode_active or not self._extra_sequence or not self._current_exam or not self._controller:
            return

        student_index, page_number = self._extra_sequence[self._extra_cursor]
        student = self._current_exam.students[student_index]

        raw_areas = simpledialog.askstring(
            "Extraseite zuordnen",
            "Bereich(e) fuer Extraseite eingeben (z. B. A,B)",
            initialvalue="A",
        )
        if raw_areas is None:
            return
        area_codes = [item.strip().upper() for item in raw_areas.split(",") if item.strip()]

        if self._render_photo is None:
            return
        canvas_width = float(self._reading_canvas.winfo_width())
        canvas_height = float(self._reading_canvas.winfo_height())
        box = (
            0.0,
            0.0,
            canvas_width * self._x_factor,
            canvas_height * self._y_factor,
        )

        updated = self._controller.assign_extra_page_immediate(
            exam=self._current_exam,
            student_pdf=student.pdf_filename,
            page_number=page_number,
            box=box,
            area_codes=area_codes,
        )
        if updated is not None:
            self._current_exam = updated
            self._apply_detail_labels(updated)
            self._render_current_extra_page()

    def _render_pdf_page(self, *, student: StudentExam, page_number: int) -> None:
        if self._current_exam is None:
            return

        pdf_path = Path(self._current_exam.folder_path) / student.pdf_filename
        if not pdf_path.exists():
            self._reading_info_var.set(f"Datei fehlt: {student.pdf_filename}")
            self._reading_canvas.delete("all")
            return

        document = self._doc_cache.get(student.pdf_filename)
        if document is None:
            document = fitz.open(pdf_path)
            self._doc_cache[student.pdf_filename] = document

        try:
            page = document.load_page(page_number - 1)
            page_rect = page.rect
            target_width = 520.0
            scale = target_width / max(page_rect.width, 1.0)
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)

            self._x_factor = page_rect.width / max(pix.width, 1)
            self._y_factor = page_rect.height / max(pix.height, 1)

            self._render_photo = tk.PhotoImage(data=pix.tobytes("ppm"), format="ppm")
            self._reading_canvas.configure(width=pix.width, height=pix.height)
            self._reading_canvas.delete("all")
            self._canvas_image_id = self._reading_canvas.create_image(0, 0, anchor=tk.NW, image=self._render_photo)
            self._reading_canvas.configure(scrollregion=(0, 0, pix.width, pix.height))
        except Exception as exc:
            self._reading_canvas.delete("all")
            self._reading_info_var.set(f"Fehler beim PDF-Rendering: {exc}")
            return

        self._draw_existing_regions(student.pdf_filename, page_number)

    def _refresh_correction_area_choices(self, exam: ExamProject) -> None:
        areas = sorted(
            {
                code.strip().upper()
                for region in exam.regions
                for code in region.assigned_area_codes
                if code.strip()
            }
        )
        if not areas:
            areas = ["A"]
        self._correction_area_combo["values"] = tuple(areas)
        if self._correction_area_var.get() not in areas:
            self._correction_area_var.set(areas[0])

    def _start_correction_mode(self) -> None:
        if not self._current_exam:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Klausur öffnen.")
            return
        area = self._correction_area_var.get().strip().upper()
        if not area:
            messagebox.showinfo("Hinweis", "Bitte einen Bereich wählen.")
            return

        indices: list[int] = []
        for idx, student in enumerate(self._current_exam.students):
            has_area = any(
                region.student_pdf == student.pdf_filename and area in region.assigned_area_codes
                for region in self._current_exam.regions
            )
            if has_area:
                indices.append(idx)

        if not indices:
            messagebox.showinfo("Keine Fälle", f"Für Bereich {area} wurden noch keine Schüler:innen zugeordnet.")
            return

        self._correction_mode_active = True
        self._correction_student_indices = indices
        self._correction_cursor = 0
        self._student_cursor = indices[0]
        self._show_correction_controls()
        self._set_detail_submode("correction")
        self._refresh_active_student_label()
        self._focus_first_input_field()
        self._open_extra_pages_popup_for_current(notify_if_missing=False)
        self._status_var.set(f"Korrekturmodus aktiv für Bereich {area}")

    def _stop_correction_mode(self, *, silent: bool = False) -> None:
        self._correction_mode_active = False
        self._correction_student_indices = []
        self._correction_cursor = 0
        self._hide_correction_controls()
        if self._detail_submode == "correction":
            self._set_detail_submode("reading")
        self._close_extra_popup()
        self._refresh_active_student_label()
        if not silent:
            self._status_var.set("Korrekturmodus beendet")

    def _toggle_extra_pages_popup_for_current(self) -> None:
        if self._extra_popup is not None and self._extra_popup.winfo_exists():
            self._close_extra_popup()
            self._status_var.set("Extraseitenansicht geschlossen")
            return
        self._open_extra_pages_popup_for_current(notify_if_missing=True)

    def _open_extra_pages_popup_for_current(self, *, notify_if_missing: bool) -> None:
        if not self._current_exam or not self._current_exam.students:
            return
        current_student_index = self._student_cursor
        student = self._current_exam.students[self._student_cursor]
        if not student.extra_pages:
            self._close_extra_popup()
            if notify_if_missing:
                messagebox.showinfo("Hinweis", "Für die aktuelle Person sind keine Extraseiten vorhanden.")
            return

        pdf_path = Path(self._current_exam.folder_path) / student.pdf_filename
        if not pdf_path.exists():
            messagebox.showerror("Fehler", f"Datei fehlt: {student.pdf_filename}")
            return

        if self._extra_popup is None or not self._extra_popup.winfo_exists():
            popup = tk.Toplevel(self.root)
            popup.title(f"Extraseiten: {student.display_name}")
            popup.geometry("760x860")
            popup.transient(self.root)
            self._register_popup_window(popup)

            header = ttk.Frame(popup, padding=10)
            header.pack(fill=tk.X)
            self._extra_popup_info_var = tk.StringVar(value="")
            ttk.Label(header, textvariable=self._extra_popup_info_var, style="Muted.TLabel").pack(side=tk.LEFT)

            self._extra_popup_canvas = tk.Canvas(popup, bg="#f2ede3", highlightthickness=1, highlightbackground="#b8aa96")
            self._extra_popup_canvas.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

            nav = ttk.Frame(popup, padding=(10, 0, 10, 10))
            nav.pack(fill=tk.X)
            ttk.Button(nav, text="◀", style="SecondaryAction.TButton", command=lambda: self._change_extra_popup_page(-1)).pack(side=tk.LEFT)
            ttk.Button(nav, text="▶", style="SecondaryAction.TButton", command=lambda: self._change_extra_popup_page(1)).pack(side=tk.LEFT, padx=(8, 0))
            ttk.Button(nav, text="Schließen", style="SecondaryAction.TButton", command=self._close_extra_popup).pack(side=tk.RIGHT)

            popup.protocol("WM_DELETE_WINDOW", self._close_extra_popup)
            self._extra_popup = popup

        if self._extra_popup is not None:
            self._extra_popup.title(f"Extraseiten: {student.display_name}")
            self._extra_popup.deiconify()
            self._extra_popup.lift()

        if self._extra_popup_student_index != current_student_index:
            self._extra_popup_cursor = 0
        self._extra_popup_student_index = current_student_index
        self._render_extra_popup_page()

    def _change_extra_popup_page(self, delta: int) -> None:
        if not self._current_exam or self._extra_popup_student_index is None:
            return
        student = self._current_exam.students[self._extra_popup_student_index]
        if not student.extra_pages:
            return
        self._extra_popup_cursor = (self._extra_popup_cursor + delta) % len(student.extra_pages)
        self._render_extra_popup_page()

    def _render_extra_popup_page(self) -> None:
        if (
            not self._current_exam
            or self._extra_popup is None
            or not self._extra_popup.winfo_exists()
            or self._extra_popup_canvas is None
            or self._extra_popup_info_var is None
            or self._extra_popup_student_index is None
        ):
            return

        student = self._current_exam.students[self._extra_popup_student_index]
        if not student.extra_pages:
            return

        page_number = student.extra_pages[self._extra_popup_cursor]
        pdf_path = Path(self._current_exam.folder_path) / student.pdf_filename

        document = self._doc_cache.get(student.pdf_filename)
        if document is None:
            document = fitz.open(pdf_path)
            self._doc_cache[student.pdf_filename] = document

        page = document.load_page(page_number - 1)
        page_rect = page.rect
        scale = 700.0 / max(page_rect.width, 1.0)
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        try:
            self._popup_photo = tk.PhotoImage(data=pix.tobytes("ppm"), format="ppm")
            self._extra_popup_canvas.configure(width=pix.width, height=pix.height)
            self._extra_popup_canvas.delete("all")
            self._extra_popup_canvas.create_image(0, 0, anchor=tk.NW, image=self._popup_photo)
        except Exception as exc:
            self._extra_popup_canvas.delete("all")
            self._extra_popup_info_var.set(f"Fehler beim Popup-Rendering: {exc}")
            return

        areas = self._areas_for_extra_page(student.pdf_filename, page_number)
        area_text = ",".join(areas) if areas else "-"
        self._extra_popup_info_var.set(
            f"Extraseite {self._extra_popup_cursor + 1}/{len(student.extra_pages)} | Seite {page_number} | Bereich {area_text}"
        )

    def _close_extra_popup(self) -> None:
        if self._extra_popup is not None and self._extra_popup.winfo_exists():
            popup_id = str(self._extra_popup)
            self._popup_registry.close_popup(popup_id)
            self._tracked_popup_ids.discard(popup_id)
            self._extra_popup.destroy()
        self._extra_popup = None
        self._extra_popup_canvas = None
        self._extra_popup_info_var = None
        self._extra_popup_student_index = None
        self._extra_popup_cursor = 0

    def _focus_first_input_field(self) -> None:
        self._task_code_entry.focus_set()
        self._task_code_entry.selection_range(0, tk.END)

    def start_reading_mode_for_current_exam(self) -> None:
        self._start_reading_mode()

    def _show_detail_mode(self) -> None:
        if self._in_detail_mode:
            return
        panes = [str(widget) for widget in self._content_pane.panes()]
        if str(self._overview_panel) in panes:
            self._content_pane.forget(self._overview_panel)
        panes = [str(widget) for widget in self._content_pane.panes()]
        if str(self._detail_panel) not in panes:
            self._content_pane.add(self._detail_panel, weight=1)
        self._in_detail_mode = True
        self._back_button.state(["!disabled"])

    def _return_to_overview(self) -> None:
        self._current_exam = None
        self._detail_exam_file = None
        self._reading_active = False
        self._extra_mode_active = False
        self._correction_mode_active = False
        self._selected_region_id = None
        self._close_extra_popup()
        self._reading_canvas.delete("all")
        self._active_region_var.set("-")
        self._quick_tasks_var.set("")
        self._form_tasks_text.delete("1.0", tk.END)
        self._refresh_region_tree()
        panes = [str(widget) for widget in self._content_pane.panes()]
        if str(self._detail_panel) in panes:
            self._content_pane.forget(self._detail_panel)
        panes = [str(widget) for widget in self._content_pane.panes()]
        if str(self._overview_panel) not in panes:
            self._content_pane.add(self._overview_panel, weight=1)
        self._in_detail_mode = False
        self._back_button.state(["disabled"])
        self._status_var.set("Zur Uebersicht zurueckgekehrt")

    def _show_correction_controls(self) -> None:
        if self._correction_controls_frame is None:
            return
        self._correction_controls_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))

    def _hide_correction_controls(self) -> None:
        if self._correction_controls_frame is None:
            return
        self._correction_controls_frame.pack_forget()

    def _set_detail_submode(self, mode: str) -> None:
        self._detail_submode = mode

        if mode == "correction":
            self._reading_workspace_frame.pack_forget()
            self._show_correction_controls()
            return

        # Reading and extra share the same workspace but with different tool rows.
        self._hide_correction_controls()
        self._reading_workspace_frame.pack(fill=tk.BOTH, expand=True)

        if mode == "extra":
            self._reading_toolbar.pack_forget()
            self._mode_row.pack_forget()
            self._regions_editor.pack_forget()
            self._extra_toolbar.pack(fill=tk.X, pady=(6, 0))
            return

        # default reading mode
        self._extra_toolbar.pack_forget()
        self._reading_toolbar.pack(fill=tk.X)
        self._mode_row.pack(fill=tk.X, pady=(8, 0))
        self._regions_editor.pack(fill=tk.BOTH, pady=(10, 0))

    def _refresh_task_input_mode(self) -> None:
        mode = self._assignment_mode_var.get()
        if mode == "form":
            self._quick_tasks_entry.pack_forget()
            self._form_tasks_text.pack(fill=tk.X, pady=(4, 0))
        else:
            self._form_tasks_text.pack_forget()
            self._quick_tasks_entry.pack(fill=tk.X)

    def _read_task_specs_from_editor(self) -> list[tuple[str, float]] | None:
        if self._assignment_mode_var.get() == "form":
            raw = self._form_tasks_text.get("1.0", tk.END).strip()
            if not raw:
                return []
            items = [line.strip() for line in raw.splitlines() if line.strip()]
        else:
            raw = self._quick_tasks_var.get().strip()
            if not raw:
                return []
            items = [item.strip() for item in raw.split(";") if item.strip()]

        parsed: list[tuple[str, float]] = []
        for item in items:
            parts = [part.strip() for part in item.split(":")]
            if len(parts) != 2:
                messagebox.showerror("Ungueltiges Format", "Nutze CODE:Punkte, z. B. A1:3")
                return None
            code, points_text = parts
            try:
                max_points = float(points_text.replace(",", "."))
            except ValueError:
                messagebox.showerror("Ungueltige Punkte", f"'{points_text}' ist keine Zahl.")
                return None
            parsed.append((code.upper(), max_points))
        return parsed

    @staticmethod
    def _index_to_area_label(index: int) -> str:
        letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        result = ""
        value = index
        while True:
            value, remainder = divmod(value, 26)
            result = letters[remainder] + result
            if value == 0:
                break
            value -= 1
        return result

    def _refresh_region_tree(self) -> None:
        self._region_tree_rows.clear()
        for item in self._regions_tree.get_children():
            self._regions_tree.delete(item)

        if self._current_exam is None:
            return

        for region in self._current_exam.regions:
            area = region.assigned_area_codes[0] if region.assigned_area_codes else "-"
            row_id = self._regions_tree.insert(
                "",
                tk.END,
                values=(area, region.student_pdf, region.page_number),
            )
            self._region_tree_rows[row_id] = region.region_id

    def _select_region_by_id(self, region_id: str) -> None:
        for row_id, candidate in self._region_tree_rows.items():
            if candidate == region_id:
                self._regions_tree.selection_set(row_id)
                self._regions_tree.focus(row_id)
                self._on_region_selected(None)
                return

    def _on_region_selected(self, _event: object) -> None:
        if self._current_exam is None:
            return
        selection = self._regions_tree.selection()
        if not selection:
            self._selected_region_id = None
            self._active_region_var.set("-")
            return

        region_id = self._region_tree_rows.get(selection[0])
        if region_id is None:
            return
        region = next((item for item in self._current_exam.regions if item.region_id == region_id), None)
        if region is None:
            return

        self._selected_region_id = region_id
        area = region.assigned_area_codes[0] if region.assigned_area_codes else "-"
        self._active_region_var.set(area)

        quick_text = ";".join(f"{task.code}:{task.max_points:g}" for task in region.tasks)
        form_text = "\n".join(f"{task.code}:{task.max_points:g}" for task in region.tasks)
        self._quick_tasks_var.set(quick_text)
        self._form_tasks_text.delete("1.0", tk.END)
        self._form_tasks_text.insert("1.0", form_text)

    def _save_selected_region(self) -> None:
        if self._current_exam is None or self._selected_region_id is None or self._controller is None:
            return
        region = next((item for item in self._current_exam.regions if item.region_id == self._selected_region_id), None)
        if region is None:
            return

        task_specs = self._read_task_specs_from_editor()
        if task_specs is None:
            return
        updated = self._controller.upsert_region_immediate(
            exam=self._current_exam,
            student_pdf=region.student_pdf,
            page_number=region.page_number,
            box=(region.box.x0, region.box.y0, region.box.x1, region.box.y1),
            task_specs=task_specs,
            area_codes=region.assigned_area_codes,
            region_id=region.region_id,
        )
        if updated is None:
            return
        self._current_exam = updated
        self._refresh_region_tree()
        self._select_region_by_id(region.region_id)
        self._apply_detail_labels(updated)
        self._render_current_reading_page()

    def _delete_selected_region(self) -> None:
        if self._current_exam is None or self._selected_region_id is None or self._controller is None:
            return
        updated = self._controller.delete_region_immediate(exam=self._current_exam, region_id=self._selected_region_id)
        self._current_exam = updated

        ordered = [region for region in self._current_exam.regions if not region.is_extra_page]
        for idx, region in enumerate(ordered):
            region.assigned_area_codes = [self._index_to_area_label(idx)]
        self._controller.save_exam_immediate(exam=self._current_exam)

        self._selected_region_id = None
        self._active_region_var.set("-")
        self._quick_tasks_var.set("")
        self._form_tasks_text.delete("1.0", tk.END)
        self._refresh_region_tree()
        self._apply_detail_labels(self._current_exam)
        self._render_current_reading_page()

    def _on_delete_region_key(self, _event: tk.Event[tk.Misc]) -> None:
        self._delete_selected_region()

