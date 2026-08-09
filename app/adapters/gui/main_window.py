from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import fitz

from app.adapters.bootstrap.wiring import GuiDependencies
from app.adapters.gui.dialog_services import messagebox, simpledialog
from app.app_info import APP_INFO
from bw_libs.shared_gui_core import ensure_bw_gui_on_path
from bw_gui.contracts.keybinding import (
    UI_MODE_DIALOG,
    UI_MODE_EDITOR,
    UI_MODE_GLOBAL,
    UI_MODE_OFFLINE,
    UI_MODE_PREVIEW,
    KeyBindingDefinition,
    KeybindingRegistry,
    KeybindingRuntimeContext,
)
from bw_gui.contracts.hsm import (
    ESCAPE_CLOSE_POPUP,
    ESCAPE_EXIT_INLINE_EDITOR,
    ESCAPE_POP_PARENT,
    build_ui_hsm_contract,
)
from bw_gui.contracts.popup import POPUP_KIND_MODAL, POPUP_KIND_NON_MODAL, PopupPolicy, PopupPolicyRegistry
from bw_gui.laufkern import aggregate_completion, emit_tracking_artifact, verify_manifest, verify_reachability
from app.adapters.gui.ui_intents import UiIntent
from app.adapters.gui.laufkern_manifest_provider import build_runtime_shortcut_manifest
from app.adapters.gui.view_models import ExamOverviewRow
from app.core.domain.models import ExamProject, PdfAnnotation, StudentExam, TaskDefinition
from app.core.domain.progress import ProgressCalculator
from app.infrastructure.repositories.json_app_settings_repository import AppRuntimeSettings

ensure_bw_gui_on_path()
from bw_gui.runtime import BwBaseWindow, ui, widgets
from bw_gui.dialogs import SettingsDialogSpec as SharedSettingsDialogSpec
from bw_gui.dialogs import SettingsFieldSpec as SharedSettingsFieldSpec
from bw_gui.dialogs import SettingsSectionSpec as SharedSettingsSectionSpec
from bw_gui.dialogs import open_tabbed_settings_dialog
from bw_gui.menu import MenuItem as SharedMenuItem
from bw_gui.menu import section_spec
from bw_gui.shortcuts import compose_hover_text
from bw_gui.widgets import HoverTooltip as SharedHoverTooltip

from bw_gui.theming import apply_window_theme
from bw_gui.theming import configure_ttk_theme
from bw_gui.theming import normalize_theme_key
from bw_gui.theming import theme_canvas
from bw_gui.theming._theme_manager import get_theme

if TYPE_CHECKING:
    from app.adapters.gui.ui_intent_controller import UiIntentController


@dataclass(slots=True)
class DraftRegion:
    draft_id: str
    student_pdf: str
    page_number: int
    box: tuple[float, float, float, float]
    area_codes: list[str]
    task_specs: list[tuple[str, float]]


@dataclass(slots=True)
class CorrectionTemplate:
    area_code: str
    page_number: int
    box: tuple[float, float, float, float]
    tasks: list[TaskDefinition]


CORRECTION_ZOOM_MIN_PERCENT = 10
CORRECTION_ZOOM_MAX_PERCENT = 240

CORRECTION_MARKER_TOOLS: tuple[tuple[str, str, str], ...] = (
    ("check", "✓", "Richtig"),
    ("wrong", "✗", "Falsch"),
    ("follow", "↻", "Folgefehler"),
    ("partial", "△", "Teilrichtig"),
    ("swap_h", "⇄", "Vertauschung horizontal"),
    ("swap_v", "⇅", "Vertauschung vertikal"),
    ("hint", "!", "Hinweis"),
    ("question", "?", "Unklar"),
)

CORRECTION_MARKER_COLORS: dict[str, str] = {
    "Rot": "#d62828",
    "Pink": "#ff4fa3",
    "Blau": "#1d4ed8",
    "Gruen": "#2a9d8f",
    "Orange": "#f77f00",
    "Violett": "#7b2cbf",
    "Schwarz": "#111111",
}

CORRECTION_DEFAULT_COLOR_NAME = "Rot"
CORRECTION_DEFAULT_FONT_SIZE_PT = 14.0
CORRECTION_ALT_MODIFIER_MASKS: tuple[int, ...] = (0x0008, 0x20000)
CORRECTION_EXPORT_TEXT_WIDTH_PADDING_EM = 0.4
CORRECTION_EXPORT_TEXT_HEIGHT_EM = 1.4
CORRECTION_EXPORT_TEXT_Y_SHIFT_EM = 0.4
CORRECTION_EXPORT_TEXT_ROT_X_SHIFT_FACTOR = 0.32
CORRECTION_EXPORT_TEXT_ROT90_Y_CORRECTION_EM = 0.25
CORRECTION_EXPORT_TEXT_ROT180_Y_CORRECTION_EM = 0.5
CORRECTION_EXPORT_SYMBOL_HEIGHT_EM = 1.3
CORRECTION_EXPORT_SYMBOL_Y_SHIFT_EM = 0.1
CORRECTION_EXPORT_SYMBOL_ROT90_X_SHIFT_EM = 0.08
CORRECTION_EXPORT_SYMBOL_ROT180_Y_CORRECTION_EM = 0.15


class MainWindow(BwBaseWindow):
    def __init__(self, deps: GuiDependencies) -> None:
        self.deps = deps
        _cfg = getattr(
            deps,
            "shell_config",
            None,
        )
        _title = _cfg.title if _cfg else APP_INFO.window_title
        _geometry = _cfg.geometry if _cfg else "1180x740"
        _min_width = _cfg.min_width if _cfg else 980
        _min_height = _cfg.min_height if _cfg else 640
        self._tooltip_theme_key = "sand_terracotta"

        self._rows_by_tree_id: dict[str, ExamOverviewRow] = {}
        self._controller = None
        self._correction_controls_frame: widgets.Frame | None = None
        self._in_detail_mode = False
        self._active_view = "overview"
        self._selected_region_id: str | None = None
        self._selected_region_kind: str | None = None
        self._region_tree_rows: dict[str, tuple[str, str]] = {}
        self._draft_regions: dict[str, DraftRegion] = {}

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
        self._extra_overview_frame: widgets.Frame | None = None
        self._extra_mode_active = False
        self._extra_sequence: list[tuple[int, int]] = []
        self._extra_cursor = 0
        self._doc_cache: dict[str, fitz.Document] = {}
        self._render_photo: ui.PhotoImage | None = None
        self._x_factor = 1.0
        self._y_factor = 1.0
        self._drag_start: tuple[float, float] | None = None
        self._drag_rect_id: int | None = None
        self._popup_photo: ui.PhotoImage | None = None
        self._extra_popup: ui.Toplevel | None = None
        self._extra_popup_canvas: ui.Canvas | None = None
        self._extra_popup_info_var: ui.StringVar | None = None
        self._extra_popup_student_index: int | None = None
        self._extra_popup_cursor = 0
        self._canvas_image_id: int | None = None
        self._redraw_target_region_kind: str | None = None
        self._redraw_target_region_id: str | None = None
        self._redraw_on_next_box: bool = False
        self._correction_templates: dict[str, CorrectionTemplate] = {}
        self._correction_task_items: list[tuple[str, float]] = []
        self._correction_photo: ui.PhotoImage | None = None
        self._correction_zoom_percent = 100
        self._correction_comment_entry: widgets.Entry | None = None
        self._correction_marker_tool_key = "check"
        settings = self.deps.runtime_settings
        self._default_annotation_color_hex = self._normalize_marker_color_hex(settings.default_annotation_color)
        self._default_annotation_font_size = self._normalize_marker_font_size(settings.default_annotation_pdf_font_size)
        self._correction_selected_annotation_id: str | None = None
        self._correction_drag_annotation_id: str | None = None
        self._correction_drag_offset_pdf: tuple[float, float] | None = None
        self._correction_drag_alt_override = False
        self._correction_annotation_items: dict[str, int] = {}
        self._correction_clip_box: tuple[float, float, float, float] | None = None
        self._correction_scale = 1.0
        self._annotation_clipboard: dict[str, object] | None = None
        self._correction_finished_check: widgets.Checkbutton | None = None
        self._save_correction_button: widgets.Button | None = None
        self._runtime_shortcuts = KeybindingRegistry()
        self._shortcut_runtime_debug_window: ui.Toplevel | None = None
        self._shortcut_runtime_debug_table: widgets.Treeview | None = None
        self._laufkern_tracking_run_id = "runtime-shortcuts"
        self._laufkern_tracking_sequence = 0
        self._laufkern_tracking_step_ids: dict[str, str] = {}
        self._laufkern_tracking_artifacts = []
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
        self._menu_bar = None
        self._hover_tooltips: list[object] = []
        self._exam_index_dir_value = str(self.deps.exam_repository.index_root)
        self._hsm_contract = build_ui_hsm_contract(
            intents=[
                UiIntent.GLOBAL_CREATE_EXAM,
                UiIntent.GLOBAL_EXPORT,
                UiIntent.GLOBAL_ESCAPE,
                UiIntent.GLOBAL_UNDO,
                UiIntent.GLOBAL_REDO,
                UiIntent.DETAIL_NAVIGATE_LEFT,
                UiIntent.DETAIL_NAVIGATE_RIGHT,
                UiIntent.DETAIL_NAVIGATE_UP,
                UiIntent.DETAIL_NAVIGATE_DOWN,
                UiIntent.DETAIL_NAVIGATE_CTRL_UP,
                UiIntent.DETAIL_NAVIGATE_CTRL_DOWN,
                UiIntent.CORRECTION_TOGGLE_FINISHED,
                UiIntent.CORRECTION_ZOOM_IN,
                UiIntent.CORRECTION_ZOOM_OUT,
                UiIntent.CORRECTION_ZOOM_RESET,
                UiIntent.CORRECTION_COPY_ANNOTATION,
                UiIntent.CORRECTION_CUT_ANNOTATION,
                UiIntent.CORRECTION_PASTE_ANNOTATION,
                UiIntent.DEBUG_RUNTIME_OVERLAY,
                UiIntent.DEBUG_RUNTIME_OFFLINE,
            ]
        )

        super().__init__(
            title=_title,
            geometry=_geometry,
            theme_key=self._tooltip_theme_key,
            min_width=_min_width,
            min_height=_min_height,
        )

    def build_menu(self) -> list:
        return [
            section_spec("file", self._menu_items_file, label="Datei", alt="d"),
            section_spec("edit", self._menu_items_edit, label="Bearbeiten", alt="e"),
            section_spec("view", self._menu_items_mode, label="Ansicht", alt="a"),
            section_spec("debug", self._menu_items_debug, label="Debug", alt="b"),
            section_spec("help", self._menu_items_help, label="Hilfe", alt="h"),
        ]

    def build_content(self, frame) -> None:
        self.root = self
        self._status_var = ui.StringVar(value="Bereit")
        self._reading_mode_title_var = ui.StringVar(value="Einlesen")
        self._reading_info_var = ui.StringVar(value="Einlesemodus: nicht aktiv")
        self._assignment_mode_var = ui.StringVar(value="quick")
        self._superpage_var = ui.BooleanVar(value=False)
        self._extra_overview_var = ui.StringVar(value="")
        self._correction_zoom_info_var = ui.StringVar(value="Zoom: 100%")
        self._correction_comment_var = ui.StringVar(value="")
        self._correction_marker_color_name_var = ui.StringVar(
            value=self._marker_color_name_for_hex(self._default_annotation_color_hex)
        )
        self._correction_marker_info_var = ui.StringVar(value="Markierung: Richtig")
        self._correction_sync_info_var = ui.StringVar(value="Sync: keine Auswahl")
        self._correction_finished_var = ui.BooleanVar(value=False)
        self._correction_finished_hint_var = ui.StringVar(value="Fertigstatus nicht aktiv")
        self._shortcut_debug_offline_var = ui.BooleanVar(value=False)
        self._shortcut_runtime_debug_context_var = ui.StringVar(value="")
        self._shortcut_runtime_debug_summary_var = ui.StringVar(value="")
        self._build_styles()
        self._build_layout(frame)
        self.after_idle(self._initial_load)

    def open_settings(self) -> None:
        self._open_settings_dialog()

    def apply_theme(self, theme_key: str) -> None:
        super().apply_theme(theme_key)
        self._tooltip_theme_key = normalize_theme_key(theme_key)
        self._build_styles()

    def _initial_load(self) -> None:
        if self._controller:
            self._controller.refresh_exam_overview()

    def _attach_hover_help(self, widget: ui.Widget, *, label: str, shortcut: str | None = None) -> None:
        """Attach hover help; shortcut details are shown here, not in button labels."""

        shortcut_text = (shortcut or "").strip()
        text = compose_hover_text(label, shortcut_text)
        tooltip = SharedHoverTooltip(widget, text, theme_key=self._tooltip_theme_key)
        self._hover_tooltips.append(tooltip)

    def _menu_create_exam(self) -> None:
        if self._controller is not None:
            self._controller.create_exam()

    def _menu_open_selected_exam(self) -> None:
        if self._controller is not None:
            self._controller.open_selected_exam()

    def _menu_export_scores(self) -> None:
        if self._controller is None:
            return
        exam = self._current_exam
        if exam is None:
            selected = self.get_selected_row()
            if selected is None:
                messagebox.showinfo("Hinweis", "Bitte zuerst eine Klausur auswählen.")
                return
            try:
                exam = self.deps.load_exam_usecase.execute(exam_file=selected.source_file)
            except Exception as exc:
                messagebox.showerror("Fehler", f"Klausur konnte nicht geladen werden: {exc}")
                return
        self._controller.export_scores_for_exam(exam=exam)

    def _menu_undo(self) -> None:
        if self._controller is not None:
            self._controller.undo()

    def _menu_redo(self) -> None:
        if self._controller is not None:
            self._controller.redo()

    def _menu_items_file(self):
        return (
            SharedMenuItem(type="command", label="Neue Klausur (Strg+N)", command=self._menu_create_exam),
            SharedMenuItem(type="command", label="Ausgewaehlte Klausur oeffnen", command=self._menu_open_selected_exam),
            SharedMenuItem(type="command", label="Punkte exportieren (Strg+E)", command=self._menu_export_scores),
            SharedMenuItem(type="separator"),
            SharedMenuItem(type="command", label="Beenden", command=self.destroy),
        )

    def _menu_items_edit(self):
        can_undo = self._controller is not None and self._controller.can_undo()
        can_redo = self._controller is not None and self._controller.can_redo()
        undo_label = self._controller.undo_label() if self._controller is not None else None
        redo_label = self._controller.redo_label() if self._controller is not None else None

        undo_text = "Rueckgaengig (Strg+Z)"
        redo_text = "Wiederholen (Strg+Y)"
        if undo_label:
            undo_text = f"Rueckgaengig: {undo_label} (Strg+Z)"
        if redo_label:
            redo_text = f"Wiederholen: {redo_label} (Strg+Y)"

        undo_item = (
            SharedMenuItem(type="command", label=undo_text, command=self._menu_undo)
            if can_undo
            else SharedMenuItem(type="disabled", label="Rueckgaengig (leer)")
        )
        redo_item = (
            SharedMenuItem(type="command", label=redo_text, command=self._menu_redo)
            if can_redo
            else SharedMenuItem(type="disabled", label="Wiederholen (leer)")
        )
        return (undo_item, redo_item)

    def _menu_items_mode(self):
        return (
            SharedMenuItem(type="command", label="Einlesemodus starten", command=self._start_reading_mode),
            SharedMenuItem(type="command", label="Korrekturmodus starten", command=self._start_correction_mode),
            SharedMenuItem(type="command", label="Extraseiten-Modus starten", command=self._start_extra_mode),
            SharedMenuItem(type="separator"),
            SharedMenuItem(type="command", label="Zur Übersicht", command=self._return_to_overview),
        )

    def _menu_items_debug(self):
        return (
            SharedMenuItem(
                type="command",
                label="Shortcut-Runtime-Debug anzeigen (Strg+Shift+D)",
                command=self._open_shortcut_runtime_debug_dialog,
            ),
            SharedMenuItem(
                type="command",
                label="Offline simulieren umschalten (Strg+Shift+O)",
                command=self._toggle_runtime_offline,
            ),
        )

    def _menu_items_help(self):
        return (
            SharedMenuItem(type="command", label="Ueber Korrektor", command=self._menu_show_about),
        )

    def _menu_show_about(self) -> None:
        messagebox.showinfo(
            "Ueber Korrektor",
            f"{APP_INFO.name}\nVersion: {APP_INFO.version}",
            parent=self.root,
        )

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
            modes=(UI_MODE_PREVIEW, UI_MODE_EDITOR),
            allow_when_text_input=True,
        )
        self._bind_runtime_shortcut(
            "<Right>",
            self._on_right_key,
            binding_id="detail.right",
            intent=UiIntent.DETAIL_NAVIGATE_RIGHT,
            modes=(UI_MODE_PREVIEW, UI_MODE_EDITOR),
            allow_when_text_input=True,
        )
        self._bind_runtime_shortcut(
            "<Up>",
            self._on_up_key,
            binding_id="detail.up",
            intent=UiIntent.DETAIL_NAVIGATE_UP,
            modes=(UI_MODE_PREVIEW, UI_MODE_EDITOR),
            allow_when_text_input=True,
        )
        self._bind_runtime_shortcut(
            "<Down>",
            self._on_down_key,
            binding_id="detail.down",
            intent=UiIntent.DETAIL_NAVIGATE_DOWN,
            modes=(UI_MODE_PREVIEW, UI_MODE_EDITOR),
            allow_when_text_input=True,
        )
        self._bind_runtime_shortcut(
            "<Control-Up>",
            self._on_ctrl_up_key,
            binding_id="detail.ctrl_up",
            intent=UiIntent.DETAIL_NAVIGATE_CTRL_UP,
            modes=(UI_MODE_PREVIEW, UI_MODE_EDITOR),
            allow_when_text_input=True,
        )
        self._bind_runtime_shortcut(
            "<Control-Down>",
            self._on_ctrl_down_key,
            binding_id="detail.ctrl_down",
            intent=UiIntent.DETAIL_NAVIGATE_CTRL_DOWN,
            modes=(UI_MODE_PREVIEW, UI_MODE_EDITOR),
            allow_when_text_input=True,
        )
        self._bind_runtime_shortcut(
            "<Control-space>",
            self._on_ctrl_space_key,
            binding_id="correction.toggle_finished",
            intent=UiIntent.CORRECTION_TOGGLE_FINISHED,
            modes=(UI_MODE_PREVIEW, UI_MODE_EDITOR),
        )
        self._bind_runtime_shortcut(
            "<Control-e>",
            self._on_ctrl_e_key,
            binding_id="global.export",
            intent=UiIntent.GLOBAL_EXPORT,
            modes=(UI_MODE_GLOBAL, UI_MODE_PREVIEW, UI_MODE_DIALOG, UI_MODE_EDITOR),
            allow_when_text_input=True,
        )
        self._bind_runtime_shortcut(
            "<Control-plus>",
            self._on_ctrl_plus_key,
            binding_id="correction.zoom_in",
            intent=UiIntent.CORRECTION_ZOOM_IN,
            modes=(UI_MODE_PREVIEW, UI_MODE_EDITOR),
            allow_when_text_input=True,
        )
        self._bind_runtime_shortcut(
            "<Control-equal>",
            self._on_ctrl_plus_key,
            binding_id="correction.zoom_in_equal",
            intent=UiIntent.CORRECTION_ZOOM_IN,
            modes=(UI_MODE_PREVIEW, UI_MODE_EDITOR),
            allow_when_text_input=True,
        )
        self._bind_runtime_shortcut(
            "<Control-KP_Add>",
            self._on_ctrl_plus_key,
            binding_id="correction.zoom_in_numpad",
            intent=UiIntent.CORRECTION_ZOOM_IN,
            modes=(UI_MODE_PREVIEW, UI_MODE_EDITOR),
            allow_when_text_input=True,
        )
        self._bind_runtime_shortcut(
            "<Control-minus>",
            self._on_ctrl_minus_key,
            binding_id="correction.zoom_out",
            intent=UiIntent.CORRECTION_ZOOM_OUT,
            modes=(UI_MODE_PREVIEW, UI_MODE_EDITOR),
            allow_when_text_input=True,
        )
        self._bind_runtime_shortcut(
            "<Control-KP_Subtract>",
            self._on_ctrl_minus_key,
            binding_id="correction.zoom_out_numpad",
            intent=UiIntent.CORRECTION_ZOOM_OUT,
            modes=(UI_MODE_PREVIEW, UI_MODE_EDITOR),
            allow_when_text_input=True,
        )
        self._bind_runtime_shortcut(
            "<Control-Key-0>",
            self._on_ctrl_zero_key,
            binding_id="correction.zoom_reset",
            intent=UiIntent.CORRECTION_ZOOM_RESET,
            modes=(UI_MODE_PREVIEW, UI_MODE_EDITOR),
            allow_when_text_input=True,
        )
        self._bind_runtime_shortcut(
            "<Control-c>",
            self._on_ctrl_c_key,
            binding_id="correction.copy_annotation",
            intent=UiIntent.CORRECTION_COPY_ANNOTATION,
            modes=(UI_MODE_PREVIEW, UI_MODE_EDITOR),
        )
        self._bind_runtime_shortcut(
            "<Control-x>",
            self._on_ctrl_x_key,
            binding_id="correction.cut_annotation",
            intent=UiIntent.CORRECTION_CUT_ANNOTATION,
            modes=(UI_MODE_PREVIEW, UI_MODE_EDITOR),
        )
        self._bind_runtime_shortcut(
            "<Control-v>",
            self._on_ctrl_v_key,
            binding_id="correction.paste_annotation",
            intent=UiIntent.CORRECTION_PASTE_ANNOTATION,
            modes=(UI_MODE_PREVIEW, UI_MODE_EDITOR),
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
        self._bind_runtime_shortcut(
            "<Control-z>",
            lambda _event: self._controller.undo(),
            binding_id="global.undo",
            intent=UiIntent.GLOBAL_UNDO,
            modes=(UI_MODE_GLOBAL, UI_MODE_PREVIEW, UI_MODE_DIALOG, UI_MODE_EDITOR),
            allow_when_text_input=True,
        )
        self._bind_runtime_shortcut(
            "<Control-y>",
            lambda _event: self._controller.redo(),
            binding_id="global.redo",
            intent=UiIntent.GLOBAL_REDO,
            modes=(UI_MODE_GLOBAL, UI_MODE_PREVIEW, UI_MODE_DIALOG, UI_MODE_EDITOR),
            allow_when_text_input=True,
        )

    def start(self) -> None:
        if self._controller:
            self._controller.refresh_exam_overview()

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
            if not isinstance(child, ui.Toplevel):
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

    def _register_popup_window(self, window: ui.Toplevel, *, policy_id: str = "dialog.modal") -> None:
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
        return isinstance(widget, (ui.Entry, widgets.Entry, ui.Text, widgets.Combobox, ui.Spinbox))

    def _build_runtime_context(self, event: ui.Event[ui.Misc] | None = None) -> KeybindingRuntimeContext:
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
            try:
                result = handler(event)
            except Exception:
                self._record_laufkern_intent_dispatch(intent, success=False)
                raise

            self._record_laufkern_intent_dispatch(intent, success=True)
            return result

        self.root.bind_all(sequence, _wrapped)

    def _build_laufkern_manifest(self):
        """Build one declarative LaufKern manifest from registered runtime shortcuts."""

        return build_runtime_shortcut_manifest(self._runtime_shortcuts)

    def _summarize_laufkern_reachability(self, *, context: KeybindingRuntimeContext) -> str:
        """Return compact LaufKern reachability summary for current runtime state."""

        manifest = self._build_laufkern_manifest()
        manifest_ok, manifest_errors = verify_manifest(manifest)
        if not manifest_ok:
            return f"LaufKern manifest-errors={len(manifest_errors)}"

        results = verify_reachability(manifest=manifest, context=context)
        reachable = sum(1 for result in results if result.reachable)
        return f"LaufKern intents {reachable}/{len(results)} erreichbar"

    def _laufkern_step_id_for_intent(self, intent: str) -> str:
        """Return stable runtime-tracking step id for one intent during this session."""

        existing = self._laufkern_tracking_step_ids.get(intent)
        if existing is not None:
            return existing

        next_index = len(self._laufkern_tracking_step_ids) + 1
        step_id = f"LK-D-RTC-{next_index:03d}"
        self._laufkern_tracking_step_ids[intent] = step_id
        return step_id

    def _record_laufkern_intent_dispatch(self, intent: str, *, success: bool) -> None:
        """Record runtime intent dispatch result as LaufKern tracking artifact."""

        self._laufkern_tracking_sequence += 1
        artifact = emit_tracking_artifact(
            run_id=self._laufkern_tracking_run_id,
            repo_name="korrektor",
            step_id=self._laufkern_step_id_for_intent(intent),
            phase="D",
            state="done" if success else "failed",
            sequence=self._laufkern_tracking_sequence,
            mandatory=True,
            producer="laufkern-runtime",
            evidence_ref=intent,
        )
        self._laufkern_tracking_artifacts.append(artifact)

    def _summarize_laufkern_completion(self) -> str:
        """Return compact completion status summary from tracked runtime artifacts."""

        if not self._laufkern_tracking_artifacts:
            return "LK completion n/a"

        summary = aggregate_completion(
            self._laufkern_tracking_artifacts,
            trusted_producers={"laufkern-runtime"},
        )
        return f"LK completion {summary.status} {summary.completed_steps}/{summary.mandatory_steps}"

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

    def _build_settings_dialog_spec(self):
        """Build shared settings schema for Korrektor runtime options."""

        return SharedSettingsDialogSpec(
            sections=(
                SharedSettingsSectionSpec(
                    key="ui",
                    label="UI",
                    fields=(
                        SharedSettingsFieldSpec(
                            key="assignment_mode",
                            label="Zuordnungsmodus (Detailansicht)",
                            field_type="enum",
                            enum_values=("quick", "form"),
                            default=self._assignment_mode_var.get(),
                        ),
                        SharedSettingsFieldSpec(
                            key="exam_index_dir",
                            label="Ablageordner Klausur-JSON",
                            field_type="string",
                            default=self._exam_index_dir_value,
                            hint="Ein einzelner Ordner fuer alle Klausur-JSON-Dateien.",
                        ),
                        SharedSettingsFieldSpec(
                            key="default_annotation_color",
                            label="Standardfarbe Markierungen",
                            field_type="enum",
                            enum_values=tuple(CORRECTION_MARKER_COLORS.keys()),
                            default=self._marker_color_name_for_hex(self._default_annotation_color_hex),
                        ),
                        SharedSettingsFieldSpec(
                            key="default_annotation_pdf_font_size",
                            label="Standardgroesse Markierungen (pt im PDF)",
                            field_type="string",
                            default=f"{self._default_annotation_font_size:.0f}",
                            hint="Gueltiger Bereich: 8 bis 96 pt.",
                        ),
                    ),
                ),
                SharedSettingsSectionSpec(
                    key="debug",
                    label="Debug",
                    fields=(
                        SharedSettingsFieldSpec(
                            key="runtime_offline",
                            label="Runtime offline simulieren",
                            field_type="bool",
                            default=bool(self._shortcut_debug_offline_var.get()),
                        ),
                    ),
                ),
            )
        )

    def _settings_dialog_values(self) -> dict[str, object]:
        """Collect current runtime values for shared settings dialog defaults."""

        return {
            "assignment_mode": self._assignment_mode_var.get(),
            "exam_index_dir": self._exam_index_dir_value,
            "default_annotation_color": self._marker_color_name_for_hex(self._default_annotation_color_hex),
            "default_annotation_pdf_font_size": f"{self._default_annotation_font_size:.0f}",
            "runtime_offline": bool(self._shortcut_debug_offline_var.get()),
        }

    def _apply_settings_dialog_payload(self, payload: dict[str, object]) -> None:
        """Apply committed settings payload to runtime state."""

        if not isinstance(payload, dict):
            return

        self._build_styles()

        assignment_mode = str(payload.get("assignment_mode", self._assignment_mode_var.get()) or "quick")
        if assignment_mode not in {"quick", "form"}:
            assignment_mode = "quick"
        self._assignment_mode_var.set(assignment_mode)

        requested_exam_index_dir = str(payload.get("exam_index_dir", self._exam_index_dir_value) or "").strip()
        if requested_exam_index_dir and self._controller is not None:
            normalized = self._controller.update_exam_index_dir(requested_exam_index_dir)
            if normalized is not None:
                self._exam_index_dir_value = str(normalized)

        selected_color_name = str(
            payload.get("default_annotation_color", self._marker_color_name_for_hex(self._default_annotation_color_hex))
            or CORRECTION_DEFAULT_COLOR_NAME
        ).strip()
        if selected_color_name not in CORRECTION_MARKER_COLORS:
            selected_color_name = CORRECTION_DEFAULT_COLOR_NAME
        self._default_annotation_color_hex = CORRECTION_MARKER_COLORS[selected_color_name]
        self._correction_marker_color_name_var.set(selected_color_name)

        requested_size = payload.get("default_annotation_pdf_font_size", self._default_annotation_font_size)
        self._default_annotation_font_size = self._normalize_marker_font_size(requested_size)

        try:
            current_index_dir = Path(self._exam_index_dir_value).resolve()
            persisted_settings = self.deps.settings_repository.save(
                AppRuntimeSettings(
                    exam_index_dir=current_index_dir,
                    default_annotation_color=self._default_annotation_color_hex,
                    default_annotation_pdf_font_size=self._default_annotation_font_size,
                )
            )
            self._default_annotation_color_hex = self._normalize_marker_color_hex(
                persisted_settings.default_annotation_color
            )
            self._default_annotation_font_size = self._normalize_marker_font_size(
                persisted_settings.default_annotation_pdf_font_size
            )
            self._exam_index_dir_value = str(persisted_settings.exam_index_dir)
        except Exception as exc:
            messagebox.showerror("Fehler", f"Einstellungen konnten nicht gespeichert werden: {exc}")
            return

        self._shortcut_debug_offline_var.set(bool(payload.get("runtime_offline", self._shortcut_debug_offline_var.get())))
        self._refresh_shortcut_runtime_debug_dialog()
        self.set_status("Einstellungen aktualisiert")

    def _open_settings_dialog(self) -> None:
        """Open shared tabbed settings dialog for runtime UI options."""

        spec = self._build_settings_dialog_spec()

        open_tabbed_settings_dialog(
            self.root,
            title="Einstellungen",
            theme_key=self._tooltip_theme_key,
            spec=spec,
            initial_values=self._settings_dialog_values(),
            on_commit=self._apply_settings_dialog_payload,
        )

    def _build_styles(self) -> None:
        """Apply the bw_gui baseline and the single korrektor-specific App.TFrame style."""
        apply_window_theme(self.root, self._tooltip_theme_key)
        configure_ttk_theme(self.root, self._tooltip_theme_key)
        theme = get_theme(self._tooltip_theme_key)
        widgets.Style(self.root).configure("App.TFrame", background=theme["bg_main"])
        self._apply_canvas_theme_tokens()

    def _canvas_theme_tokens(self) -> tuple[str, str]:
        """Return (bg_surface, border) for constructing canvas widgets in _build_layout."""
        theme = get_theme(self._tooltip_theme_key)
        return theme["bg_surface"], theme["border"]

    def _apply_canvas_theme_tokens(self) -> None:
        """Re-theme all canvas widgets to match the current theme."""
        tk = self._tooltip_theme_key
        for attr in ("_reading_canvas", "_correction_canvas"):
            canvas = getattr(self, attr, None)
            if canvas is not None:
                try:
                    theme_canvas(canvas, tk)
                except Exception:
                    pass
        if self._extra_popup_canvas is not None:
            try:
                theme_canvas(self._extra_popup_canvas, tk)
            except Exception:
                pass

    def _build_layout(self, frame=None) -> None:
        shell = widgets.Frame(frame if frame is not None else self, style="App.TFrame", padding=16)
        shell.pack(fill=ui.BOTH, expand=True)

        self._view_stack = widgets.Frame(shell, style="App.TFrame")
        self._view_stack.pack(fill=ui.BOTH, expand=True, pady=(0, 10))

        self._overview_view = widgets.Frame(self._view_stack, style="Surface.TFrame", padding=12)
        self._detail_view = widgets.Frame(self._view_stack, style="Surface.TFrame", padding=12)
        self._reading_view = widgets.Frame(self._view_stack, style="Surface.TFrame", padding=12)
        self._correction_view = widgets.Frame(self._view_stack, style="Surface.TFrame", padding=12)

        widgets.Label(self._overview_view, text="Uebersicht", style="Title.TLabel").pack(anchor=ui.W)

        overview_actions = widgets.Frame(self._overview_view, style="Surface.TFrame")
        overview_actions.pack(fill=ui.X, pady=(8, 10))

        create_exam_button = widgets.Button(
            overview_actions,
            text="Neue Klausur",
            style="PrimaryAction.TButton",
            command=lambda: self._controller and self._controller.create_exam(),
        )
        create_exam_button.pack(side=ui.LEFT)
        self._attach_hover_help(create_exam_button, label="Neue Klausur erstellen", shortcut="Ctrl+N")

        open_exam_button = widgets.Button(
            overview_actions,
            text="Klausur oeffnen",
            style="SecondaryAction.TButton",
            command=lambda: self._controller and self._controller.open_selected_exam(),
        )
        open_exam_button.pack(side=ui.LEFT, padx=(10, 0))
        self._attach_hover_help(open_exam_button, label="Ausgewaehlte Klausur oeffnen", shortcut="Enter")

        delete_exam_button = widgets.Button(
            overview_actions,
            text="Klausur loeschen",
            style="SecondaryAction.TButton",
            command=lambda: self._controller and self._controller.delete_selected_exam(),
        )
        delete_exam_button.pack(side=ui.LEFT, padx=(10, 0))
        self._attach_hover_help(delete_exam_button, label="Ausgewaehlte Klausur loeschen", shortcut=None)

        self._tree = widgets.Treeview(
            self._overview_view,
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
            self._tree.column(key, width=widths[key], anchor=ui.CENTER if key != "name" else ui.W)
        self._tree.pack(fill=ui.BOTH, expand=True)
        self._tree.bind("<Double-1>", lambda _event: self._controller and self._controller.open_selected_exam())
        self._tree.bind("<Return>", lambda _event: self._controller and self._controller.open_selected_exam())

        widgets.Label(self._detail_view, text="Klausur-Details", style="Title.TLabel").pack(anchor=ui.W)

        detail_actions = widgets.Frame(self._detail_view, style="Surface.TFrame")
        detail_actions.pack(fill=ui.X, pady=(8, 10))

        back_button = widgets.Button(
            detail_actions,
            text="Zur Übersicht",
            style="SecondaryAction.TButton",
            command=self._return_to_overview,
        )
        back_button.pack(side=ui.LEFT)
        self._attach_hover_help(back_button, label="Zur Gesamtübersicht wechseln", shortcut="Esc")

        mode_reading_button = widgets.Button(
            detail_actions,
            text="Einlesen",
            style="SecondaryAction.TButton",
            command=self._start_reading_mode,
        )
        mode_reading_button.pack(side=ui.LEFT, padx=(8, 0))
        self._attach_hover_help(mode_reading_button, label="In den Einlesemodus wechseln", shortcut=None)

        mode_extra_button = widgets.Button(
            detail_actions,
            text="Extraseiten",
            style="SecondaryAction.TButton",
            command=self._start_extra_mode,
        )
        mode_extra_button.pack(side=ui.LEFT, padx=(8, 0))
        self._attach_hover_help(mode_extra_button, label="In den Extraseitenmodus wechseln", shortcut=None)

        mode_correction_button = widgets.Button(
            detail_actions,
            text="Korrektur",
            style="SecondaryAction.TButton",
            command=self._start_correction_mode,
        )
        mode_correction_button.pack(side=ui.LEFT, padx=(8, 0))
        self._attach_hover_help(mode_correction_button, label="In den Korrekturmodus wechseln", shortcut=None)

        export_detail_button = widgets.Button(
            detail_actions,
            text="Export",
            style="SecondaryAction.TButton",
            command=self._menu_export_scores,
        )
        export_detail_button.pack(side=ui.RIGHT)
        self._attach_hover_help(export_detail_button, label="Punkte als CSV exportieren", shortcut="Strg+E")

        self._detail_name = ui.StringVar(value="-")
        self._detail_pages = ui.StringVar(value="Standardseiten: -")
        self._detail_students = ui.StringVar(value="Schüler:innen: -")
        self._detail_regions = ui.StringVar(value="Fertig korrigiert -")
        self._detail_status = ui.StringVar(value="Status: -")
        self._active_student = ui.StringVar(value="Aktive Person: -")

        for variable in [
            self._detail_name,
            self._detail_pages,
            self._detail_students,
            self._detail_regions,
            self._detail_status,
            self._active_student,
        ]:
            widgets.Label(self._detail_view, textvariable=variable, style="Muted.TLabel").pack(anchor=ui.W, pady=4)

        self._correction_controls_frame = widgets.Frame(self._detail_view, style="Surface.TFrame")
        self._correction_controls_frame.pack(fill=ui.X, pady=(10, 0))

        widgets.Separator(self._correction_controls_frame).pack(fill=ui.X, pady=(0, 10))
        widgets.Label(self._correction_controls_frame, text="Schnellkorrektur", style="Muted.TLabel").pack(anchor=ui.W)

        correction_header = widgets.Frame(self._correction_controls_frame, style="Surface.TFrame")
        correction_header.pack(fill=ui.X, pady=(6, 6))
        widgets.Label(correction_header, text="Bereich", style="Muted.TLabel").pack(side=ui.LEFT)
        self._correction_area_var = ui.StringVar(value="A")
        self._correction_area_combo = widgets.Combobox(
            correction_header,
            textvariable=self._correction_area_var,
            state="readonly",
            width=8,
            values=("A",),
        )
        self._correction_area_combo.pack(side=ui.LEFT, padx=(8, 8))
        start_correction_button = widgets.Button(
            correction_header,
            text="Korrekturmodus",
            style="SecondaryAction.TButton",
            command=self._start_correction_mode,
        )
        start_correction_button.pack(side=ui.LEFT)
        self._attach_hover_help(start_correction_button, label="Korrekturmodus starten", shortcut=None)

        stop_correction_button = widgets.Button(
            correction_header,
            text="Modus beenden",
            style="SecondaryAction.TButton",
            command=self._stop_correction_mode,
        )
        stop_correction_button.pack(side=ui.LEFT, padx=(8, 0))
        self._attach_hover_help(stop_correction_button, label="Aktiven Modus beenden", shortcut="Esc")

        show_extras_button = widgets.Button(
            correction_header,
            text="Extraseiten ansehen",
            style="SecondaryAction.TButton",
            command=self._toggle_extra_pages_popup_for_current,
        )
        show_extras_button.pack(side=ui.RIGHT)
        self._attach_hover_help(show_extras_button, label="Extraseiten-Popup der aktuellen Person oeffnen", shortcut=None)

        form = widgets.Frame(self._correction_controls_frame, style="Surface.TFrame")
        form.pack(fill=ui.X, pady=(8, 0))
        form.columnconfigure(1, weight=1)

        widgets.Label(form, text="Aufgabe", style="Muted.TLabel").grid(row=0, column=0, sticky=ui.W, padx=(0, 6), pady=4)
        widgets.Label(form, text="Max", style="Muted.TLabel").grid(row=1, column=0, sticky=ui.W, padx=(0, 6), pady=4)
        widgets.Label(form, text="Erreicht", style="Muted.TLabel").grid(row=2, column=0, sticky=ui.W, padx=(0, 6), pady=4)

        self._task_code_var = ui.StringVar(value="A1")
        self._max_points_var = ui.StringVar(value="0")
        self._points_var = ui.StringVar(value="")

        self._task_code_entry = widgets.Entry(form, textvariable=self._task_code_var)
        self._max_points_entry = widgets.Entry(form, textvariable=self._max_points_var)
        self._points_entry = widgets.Entry(form, textvariable=self._points_var)

        self._task_code_entry.grid(row=0, column=1, sticky=ui.EW, pady=4)
        self._max_points_entry.grid(row=1, column=1, sticky=ui.EW, pady=4)
        self._points_entry.grid(row=2, column=1, sticky=ui.EW, pady=4)

        self._task_code_entry.bind("<Escape>", self._on_points_escape)
        self._max_points_entry.bind("<Escape>", self._on_points_escape)
        self._points_entry.bind("<FocusOut>", self._on_points_focus_out)
        self._points_entry.bind("<Return>", self._on_points_commit)
        self._points_entry.bind("<Escape>", self._on_points_escape)

        nav = widgets.Frame(self._correction_controls_frame, style="Surface.TFrame")
        nav.pack(fill=ui.X, pady=(10, 0))
        prev_student_button = widgets.Button(
            nav,
            text="◀ Person",
            style="SecondaryAction.TButton",
            command=lambda: self._move_student(-1),
        )
        prev_student_button.pack(side=ui.LEFT)
        self._attach_hover_help(prev_student_button, label="Vorherige Person", shortcut="Links")

        next_student_button = widgets.Button(
            nav,
            text="Person ▶",
            style="SecondaryAction.TButton",
            command=lambda: self._move_student(1),
        )
        next_student_button.pack(side=ui.LEFT, padx=(8, 0))
        self._attach_hover_help(next_student_button, label="Naechste Person", shortcut="Rechts")

        widgets.Label(self._reading_view, textvariable=self._reading_mode_title_var, style="Title.TLabel").pack(anchor=ui.W)
        widgets.Label(self._reading_view, textvariable=self._reading_info_var, style="Muted.TLabel").pack(anchor=ui.W, pady=(4, 8))

        reading_nav = widgets.Frame(self._reading_view, style="Surface.TFrame")
        reading_nav.pack(fill=ui.X, pady=(0, 8))

        back_to_detail_button = widgets.Button(
            reading_nav,
            text="Zurueck zur Klausur",
            style="SecondaryAction.TButton",
            command=self._leave_reading_view,
        )
        back_to_detail_button.pack(side=ui.LEFT)
        self._attach_hover_help(back_to_detail_button, label="Zur Klausurdetailansicht zurueck", shortcut="Esc")

        finish_reading_button = widgets.Button(
            reading_nav,
            text="Einlesen abschliessen",
            style="PrimaryAction.TButton",
            command=self._finish_reading_mode,
        )
        finish_reading_button.pack(side=ui.RIGHT)
        self._attach_hover_help(finish_reading_button, label="Einlesemodus abschliessen", shortcut=None)

        self._reading_toolbar = widgets.Frame(self._reading_view, style="Surface.TFrame")
        self._reading_toolbar.pack(fill=ui.X)
        prev_page_button = widgets.Button(
            self._reading_toolbar,
            text="◀ Seite",
            style="SecondaryAction.TButton",
            command=lambda: self._change_reading_page(-1),
        )
        prev_page_button.pack(side=ui.LEFT)
        self._attach_hover_help(prev_page_button, label="Vorherige Seite", shortcut="Links")

        next_page_button = widgets.Button(
            self._reading_toolbar,
            text="Seite ▶",
            style="SecondaryAction.TButton",
            command=lambda: self._change_reading_page(1),
        )
        next_page_button.pack(side=ui.LEFT, padx=(8, 0))
        self._attach_hover_help(next_page_button, label="Naechste Seite", shortcut="Rechts")

        prev_reading_student_button = widgets.Button(
            self._reading_toolbar,
            text="◀ Schüler:in",
            style="SecondaryAction.TButton",
            command=lambda: self._change_reading_student(-1),
        )
        prev_reading_student_button.pack(side=ui.LEFT, padx=(14, 0))
        self._attach_hover_help(prev_reading_student_button, label="Vorherige Person im Einlesen", shortcut=None)

        next_reading_student_button = widgets.Button(
            self._reading_toolbar,
            text="Schüler:in ▶",
            style="SecondaryAction.TButton",
            command=lambda: self._change_reading_student(1),
        )
        next_reading_student_button.pack(side=ui.LEFT, padx=(8, 0))
        self._attach_hover_help(next_reading_student_button, label="Naechste Person im Einlesen", shortcut=None)

        self._superpage_toggle = widgets.Checkbutton(
            self._reading_toolbar,
            text="Superseite",
            variable=self._superpage_var,
            command=self._on_superpage_toggle,
        )
        self._superpage_toggle.pack(side=ui.RIGHT)
        self._attach_hover_help(
            self._superpage_toggle,
            label="Alle PDFs der aktuellen Seite als dunkle Superposition anzeigen",
            shortcut=None,
        )

        self._extra_toolbar = widgets.Frame(self._reading_view, style="Surface.TFrame")
        self._extra_toolbar.pack(fill=ui.X, pady=(6, 0))
        prev_extra_page_button = widgets.Button(
            self._extra_toolbar,
            text="◀ Extraseite",
            style="SecondaryAction.TButton",
            command=lambda: self._change_extra_page(-1),
        )
        prev_extra_page_button.pack(side=ui.LEFT)
        self._attach_hover_help(prev_extra_page_button, label="Vorherige Extraseite", shortcut=None)

        next_extra_page_button = widgets.Button(
            self._extra_toolbar,
            text="Extraseite ▶",
            style="SecondaryAction.TButton",
            command=lambda: self._change_extra_page(1),
        )
        next_extra_page_button.pack(side=ui.LEFT, padx=(8, 0))
        self._attach_hover_help(next_extra_page_button, label="Naechste Extraseite", shortcut=None)

        assign_extra_page_button = widgets.Button(
            self._extra_toolbar,
            text="Bereich zuordnen",
            style="PrimaryAction.TButton",
            command=self._assign_current_extra_page,
        )
        assign_extra_page_button.pack(side=ui.RIGHT)
        self._attach_hover_help(assign_extra_page_button, label="Aktuelle Extraseite einem Bereich zuordnen", shortcut=None)

        self._mode_row = widgets.Frame(self._reading_view, style="Surface.TFrame")
        self._mode_row.pack(fill=ui.X, pady=(8, 0))
        widgets.Label(self._mode_row, text="Zuordnung:", style="Muted.TLabel").pack(side=ui.LEFT)
        widgets.Radiobutton(self._mode_row, text="Schnell (Code:Punkte)", value="quick", variable=self._assignment_mode_var).pack(side=ui.LEFT, padx=(8, 0))
        widgets.Radiobutton(self._mode_row, text="Formular", value="form", variable=self._assignment_mode_var).pack(side=ui.LEFT, padx=(8, 0))
        self._assignment_mode_var.trace_add("write", lambda *_args: self._refresh_task_input_mode())

        reading_split = widgets.PanedWindow(self._reading_view, orient=ui.HORIZONTAL)
        reading_split.pack(fill=ui.BOTH, expand=True, pady=(10, 0))

        canvas_panel = widgets.Frame(reading_split, style="Surface.TFrame", padding=(0, 0, 8, 0))
        editor_panel = widgets.Frame(reading_split, style="Surface.TFrame", padding=(8, 0, 0, 0))
        reading_split.add(canvas_panel, weight=3)
        reading_split.add(editor_panel, weight=2)

        canvas_container = widgets.Frame(canvas_panel, style="Surface.TFrame")
        canvas_container.pack(fill=ui.BOTH, expand=True)

        canvas_scroll_x = widgets.Scrollbar(canvas_container, orient=ui.HORIZONTAL)
        canvas_scroll_y = widgets.Scrollbar(canvas_container, orient=ui.VERTICAL)

        canvas_bg, canvas_border = self._canvas_theme_tokens()
        self._reading_canvas = ui.Canvas(
            canvas_container,
            width=520,
            height=360,
            bg=canvas_bg,
            highlightthickness=1,
            highlightbackground=canvas_border,
            xscrollcommand=canvas_scroll_x.set,
            yscrollcommand=canvas_scroll_y.set,
        )
        canvas_scroll_x.config(command=self._reading_canvas.xview)
        canvas_scroll_y.config(command=self._reading_canvas.yview)

        canvas_scroll_x.pack(side=ui.BOTTOM, fill=ui.X)
        canvas_scroll_y.pack(side=ui.RIGHT, fill=ui.Y)
        self._reading_canvas.pack(side=ui.LEFT, fill=ui.BOTH, expand=True)
        self._reading_canvas.bind("<ButtonPress-1>", self._on_canvas_press)
        self._reading_canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self._reading_canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self._reading_canvas.bind("<MouseWheel>", self._on_canvas_mousewheel)
        self._reading_canvas.bind("<Shift-MouseWheel>", self._on_canvas_shift_mousewheel)

        self._regions_editor = widgets.Frame(editor_panel, style="Surface.TFrame")
        self._regions_editor.pack(fill=ui.BOTH, pady=(10, 0))

        self._extra_overview_frame = widgets.Frame(self._regions_editor, style="Surface.TFrame")
        widgets.Label(self._extra_overview_frame, text="Vorhandene Bereiche/Aufgaben", style="Muted.TLabel").pack(anchor=ui.W)
        widgets.Label(
            self._extra_overview_frame,
            textvariable=self._extra_overview_var,
            style="Muted.TLabel",
            justify=ui.LEFT,
        ).pack(anchor=ui.W, fill=ui.X, pady=(2, 0))
        self._extra_overview_frame.pack_forget()

        regions_tree_shell = widgets.Frame(self._regions_editor, style="Surface.TFrame")
        regions_tree_shell.pack(fill=ui.BOTH, expand=True)

        self._regions_tree = widgets.Treeview(
            regions_tree_shell,
            columns=("area", "tasks", "page"),
            show="headings",
            height=5,
        )
        self._regions_tree.heading("area", text="Bereich")
        self._regions_tree.heading("tasks", text="Aufgaben")
        self._regions_tree.heading("page", text="Seite")
        self._regions_tree.column("area", width=80, anchor=ui.CENTER)
        self._regions_tree.column("tasks", width=220, anchor=ui.W)
        self._regions_tree.column("page", width=80, anchor=ui.CENTER)

        regions_tree_scroll = widgets.Scrollbar(regions_tree_shell, orient=ui.VERTICAL)
        self._regions_tree.configure(yscrollcommand=regions_tree_scroll.set)
        regions_tree_scroll.configure(command=self._regions_tree.yview)
        self._regions_tree.pack(side=ui.LEFT, fill=ui.BOTH, expand=True)
        regions_tree_scroll.pack(side=ui.RIGHT, fill=ui.Y)

        self._regions_tree.bind("<<TreeviewSelect>>", self._on_region_selected)
        self.root.bind_all("<Delete>", self._on_delete_region_key)

        editor_head = widgets.Frame(self._regions_editor, style="Surface.TFrame")
        editor_head.pack(fill=ui.X, pady=(8, 4))
        widgets.Label(editor_head, text="Aktiver Bereich:", style="Muted.TLabel").pack(side=ui.LEFT)
        self._active_region_var = ui.StringVar(value="-")
        widgets.Label(editor_head, textvariable=self._active_region_var, style="Status.TLabel").pack(side=ui.LEFT, padx=(8, 0))

        self._task_input_container = widgets.Frame(self._regions_editor, style="Surface.TFrame")
        self._task_input_container.pack(fill=ui.X)

        self._quick_tasks_var = ui.StringVar(value="")
        self._quick_tasks_entry = widgets.Entry(self._task_input_container, textvariable=self._quick_tasks_var)
        self._quick_tasks_entry.pack(fill=ui.X)

        self._form_tasks_text = ui.Text(self._task_input_container, height=4, wrap="word")

        self._task_input_example_var = ui.StringVar(value="")
        self._task_input_example_label = widgets.Label(
            self._task_input_container,
            textvariable=self._task_input_example_var,
            style="Muted.TLabel",
            justify=ui.LEFT,
        )
        self._task_input_example_label.pack(fill=ui.X, pady=(4, 0))

        self._extra_area_container = widgets.Frame(self._regions_editor, style="Surface.TFrame")
        widgets.Label(self._extra_area_container, text="Bereich(e) fuer Extraseite", style="Muted.TLabel").pack(anchor=ui.W)
        self._extra_area_codes_var = ui.StringVar(value="")
        self._extra_area_entry = widgets.Entry(self._extra_area_container, textvariable=self._extra_area_codes_var)
        self._extra_area_entry.pack(fill=ui.X, pady=(4, 0))
        self._extra_area_hint_var = ui.StringVar(value="Nur bestehende Bereiche, z. B. A,B")
        widgets.Label(
            self._extra_area_container,
            textvariable=self._extra_area_hint_var,
            style="Muted.TLabel",
            justify=ui.LEFT,
        ).pack(anchor=ui.W, pady=(4, 0))
        self._extra_area_container.pack_forget()

        region_actions = widgets.Frame(self._regions_editor, style="Surface.TFrame")
        region_actions.pack(fill=ui.X, pady=(6, 0))
        save_region_button = widgets.Button(
            region_actions,
            text="Speichern",
            style="SecondaryAction.TButton",
            command=self._save_selected_region,
        )
        save_region_button.pack(side=ui.LEFT)
        self._attach_hover_help(save_region_button, label="Aktiven Bereich speichern", shortcut=None)

        delete_region_button = widgets.Button(
            region_actions,
            text="Loeschen",
            style="SecondaryAction.TButton",
            command=self._delete_selected_region,
        )
        delete_region_button.pack(side=ui.LEFT, padx=(8, 0))
        self._attach_hover_help(delete_region_button, label="Aktiven Bereich loeschen", shortcut="Entf")

        redraw_region_button = widgets.Button(
            region_actions,
            text="Bereich neu ziehen",
            style="SecondaryAction.TButton",
            command=self._arm_redraw_selected_region,
        )
        redraw_region_button.pack(side=ui.LEFT, padx=(8, 0))
        self._attach_hover_help(
            redraw_region_button,
            label="Naechste gezogene Box ueberschreibt den ausgewaehlten Bereich",
            shortcut=None,
        )

        self._refresh_task_input_mode()

        widgets.Label(self._correction_view, text="Korrektur", style="Title.TLabel").pack(anchor=ui.W)
        self._correction_info_var = ui.StringVar(value="Korrektur: nicht aktiv")
        widgets.Label(self._correction_view, textvariable=self._correction_info_var, style="Muted.TLabel").pack(anchor=ui.W, pady=(4, 8))

        correction_actions = widgets.Frame(self._correction_view, style="Surface.TFrame")
        correction_actions.pack(fill=ui.X, pady=(0, 8))

        correction_back_button = widgets.Button(
            correction_actions,
            text="Zurueck zur Klausur",
            style="SecondaryAction.TButton",
            command=self._stop_correction_mode,
        )
        correction_back_button.pack(side=ui.LEFT)
        self._attach_hover_help(correction_back_button, label="Korrekturansicht verlassen", shortcut="Esc")

        widgets.Label(correction_actions, text="Bereich", style="Muted.TLabel").pack(side=ui.LEFT, padx=(14, 4))
        self._correction_area_combo_view = widgets.Combobox(
            correction_actions,
            textvariable=self._correction_area_var,
            state="readonly",
            width=10,
            values=("A",),
        )
        self._correction_area_combo_view.pack(side=ui.LEFT)
        self._correction_area_combo_view.bind("<<ComboboxSelected>>", self._on_correction_area_changed)

        widgets.Label(correction_actions, text="Aufgabe", style="Muted.TLabel").pack(side=ui.LEFT, padx=(12, 4))
        self._correction_task_var = ui.StringVar(value="")
        self._correction_task_combo = widgets.Combobox(
            correction_actions,
            textvariable=self._correction_task_var,
            state="readonly",
            width=20,
            values=(),
        )
        self._correction_task_combo.pack(side=ui.LEFT)
        self._correction_task_combo.bind("<<ComboboxSelected>>", self._on_correction_task_changed)

        self._correction_max_points_var = ui.StringVar(value="Max: -")
        widgets.Label(correction_actions, textvariable=self._correction_max_points_var, style="Status.TLabel").pack(side=ui.LEFT, padx=(12, 0))

        correction_zoom_actions = widgets.Frame(correction_actions, style="Surface.TFrame")
        correction_zoom_actions.pack(side=ui.RIGHT)
        widgets.Label(correction_zoom_actions, textvariable=self._correction_zoom_info_var, style="Muted.TLabel").pack(side=ui.RIGHT, padx=(8, 0))
        reset_correction_zoom_button = widgets.Button(
            correction_zoom_actions,
            text="100%",
            style="SecondaryAction.TButton",
            command=self._reset_correction_zoom,
        )
        reset_correction_zoom_button.pack(side=ui.RIGHT)
        self._attach_hover_help(reset_correction_zoom_button, label="Korrektur-Zoom auf 100% setzen", shortcut="Strg+0")

        zoom_in_correction_button = widgets.Button(
            correction_zoom_actions,
            text="+",
            style="SecondaryAction.TButton",
            command=lambda: self._change_correction_zoom(10),
            width=3,
        )
        zoom_in_correction_button.pack(side=ui.RIGHT, padx=(8, 0))
        self._attach_hover_help(zoom_in_correction_button, label="Korrektur-Zoom vergroessern", shortcut="Strg++")

        zoom_out_correction_button = widgets.Button(
            correction_zoom_actions,
            text="-",
            style="SecondaryAction.TButton",
            command=lambda: self._change_correction_zoom(-10),
            width=3,
        )
        zoom_out_correction_button.pack(side=ui.RIGHT, padx=(8, 0))
        self._attach_hover_help(zoom_out_correction_button, label="Korrektur-Zoom verkleinern", shortcut="Strg+-")

        correction_split = widgets.PanedWindow(self._correction_view, orient=ui.HORIZONTAL)
        correction_split.pack(fill=ui.BOTH, expand=True)

        correction_canvas_panel = widgets.Frame(correction_split, style="Surface.TFrame", padding=(0, 0, 8, 0))
        correction_form_panel = widgets.Frame(correction_split, style="Surface.TFrame", padding=(8, 0, 0, 0))
        correction_split.add(correction_canvas_panel, weight=3)
        correction_split.add(correction_form_panel, weight=2)

        correction_canvas_bg, correction_canvas_border = self._canvas_theme_tokens()
        self._correction_canvas = ui.Canvas(
            correction_canvas_panel,
            width=520,
            height=360,
            bg=correction_canvas_bg,
            highlightthickness=1,
            highlightbackground=correction_canvas_border,
        )
        self._correction_canvas.pack(fill=ui.BOTH, expand=True)
        self._correction_canvas.bind("<MouseWheel>", self._on_correction_mousewheel)
        self._correction_canvas.bind("<Shift-MouseWheel>", self._on_correction_mousewheel)
        self._correction_canvas.bind("<Control-MouseWheel>", self._on_correction_mousewheel)
        self._correction_canvas.bind("<Button-4>", self._on_correction_mousewheel)
        self._correction_canvas.bind("<Button-5>", self._on_correction_mousewheel)
        self._correction_canvas.bind("<Shift-Button-4>", self._on_correction_mousewheel)
        self._correction_canvas.bind("<Shift-Button-5>", self._on_correction_mousewheel)
        self._correction_canvas.bind("<Control-Button-4>", self._on_correction_mousewheel)
        self._correction_canvas.bind("<Control-Button-5>", self._on_correction_mousewheel)
        self._correction_canvas.bind("<Button-1>", self._on_correction_canvas_press)
        self._correction_canvas.bind("<B1-Motion>", self._on_correction_canvas_drag)
        self._correction_canvas.bind("<ButtonRelease-1>", self._on_correction_canvas_release)

        correction_form = widgets.Frame(correction_form_panel, style="Surface.TFrame")
        correction_form.pack(fill=ui.X, pady=(8, 0))
        correction_form.columnconfigure(1, weight=1)
        correction_form.columnconfigure(2, weight=0)

        widgets.Label(correction_form, text="Erreichte Punkte", style="Muted.TLabel").grid(
            row=0,
            column=0,
            sticky=ui.W,
            padx=(0, 6),
            pady=4,
        )
        self._correction_points_var = ui.StringVar(value="")
        self._correction_points_entry = widgets.Entry(correction_form, textvariable=self._correction_points_var)
        self._correction_points_entry.grid(row=0, column=1, sticky=ui.EW, pady=4)
        self._correction_points_entry.bind("<FocusOut>", self._on_correction_points_focus_out)
        self._correction_points_entry.bind("<Return>", self._on_correction_points_commit)
        self._correction_points_entry.bind("<Escape>", self._on_correction_points_escape)

        widgets.Label(correction_form, text="Kommentar", style="Muted.TLabel").grid(
            row=1,
            column=0,
            sticky=ui.W,
            padx=(0, 6),
            pady=4,
        )
        self._correction_comment_entry = widgets.Entry(correction_form, textvariable=self._correction_comment_var)
        self._correction_comment_entry.grid(row=1, column=1, sticky=ui.EW, pady=4)
        self._correction_comment_entry.bind("<FocusOut>", self._on_correction_comment_focus_out)
        self._correction_comment_entry.bind("<Return>", self._on_correction_comment_commit)
        self._correction_comment_entry.bind("<Escape>", self._on_correction_comment_escape)

        insert_comment_button = widgets.Button(
            correction_form,
            text="Einfuegen",
            style="SecondaryAction.TButton",
            command=self._insert_current_comment_into_preview_center,
        )
        insert_comment_button.grid(row=1, column=2, padx=(8, 0), sticky=ui.E)
        self._attach_hover_help(insert_comment_button, label="Kommentar in der Vorschau-Mitte einfuegen")

        self._correction_finished_check = widgets.Checkbutton(
            correction_form,
            text="Fertig korrigiert",
            variable=self._correction_finished_var,
            command=self._on_correction_finished_toggled,
            state="disabled",
        )
        self._correction_finished_check.grid(row=3, column=0, columnspan=3, sticky=ui.W, pady=(4, 0))
        widgets.Label(
            correction_form,
            textvariable=self._correction_finished_hint_var,
            style="Muted.TLabel",
        ).grid(row=4, column=0, columnspan=3, sticky=ui.W, pady=(2, 0))

        marker_controls = widgets.Frame(correction_form_panel, style="Surface.TFrame")
        marker_controls.pack(fill=ui.X, pady=(10, 0))

        widgets.Label(marker_controls, text="Markierungen", style="Muted.TLabel").pack(anchor=ui.W)

        color_row = widgets.Frame(marker_controls, style="Surface.TFrame")
        color_row.pack(fill=ui.X, pady=(4, 0))
        widgets.Label(color_row, text="Farbe", style="Muted.TLabel").pack(side=ui.LEFT)
        color_combo = widgets.Combobox(
            color_row,
            textvariable=self._correction_marker_color_name_var,
            values=tuple(CORRECTION_MARKER_COLORS.keys()),
            state="readonly",
            width=12,
        )
        color_combo.pack(side=ui.LEFT, padx=(8, 0))
        color_combo.bind("<<ComboboxSelected>>", self._on_correction_marker_color_changed)

        marker_row = widgets.Frame(marker_controls, style="Surface.TFrame")
        marker_row.pack(fill=ui.X, pady=(6, 0))
        for tool_key, glyph, label in CORRECTION_MARKER_TOOLS:
            marker_button = widgets.Button(
                marker_row,
                text=glyph,
                style="SecondaryAction.TButton",
                width=3,
                command=lambda value=tool_key: self._set_correction_marker_tool(value),
            )
            marker_button.pack(side=ui.LEFT, padx=(0, 4))
            self._attach_hover_help(marker_button, label=f"Markierung: {label}")

        transform_row = widgets.Frame(marker_controls, style="Surface.TFrame")
        transform_row.pack(fill=ui.X, pady=(6, 0))

        shrink_button = widgets.Button(
            transform_row,
            text="A-",
            style="SecondaryAction.TButton",
            width=4,
            command=lambda: self._resize_selected_correction_annotation(-2.0),
        )
        shrink_button.pack(side=ui.LEFT, padx=(0, 4))
        self._attach_hover_help(shrink_button, label="Ausgewaehlte Markierung verkleinern")

        grow_button = widgets.Button(
            transform_row,
            text="A+",
            style="SecondaryAction.TButton",
            width=4,
            command=lambda: self._resize_selected_correction_annotation(2.0),
        )
        grow_button.pack(side=ui.LEFT, padx=(0, 4))
        self._attach_hover_help(grow_button, label="Ausgewaehlte Markierung vergroessern")

        rotate_left_button = widgets.Button(
            transform_row,
            text="↺",
            style="SecondaryAction.TButton",
            width=4,
            command=lambda: self._rotate_selected_correction_annotation(90.0),
        )
        rotate_left_button.pack(side=ui.LEFT, padx=(8, 4))
        self._attach_hover_help(rotate_left_button, label="Ausgewaehlte Markierung nach links drehen")

        rotate_right_button = widgets.Button(
            transform_row,
            text="↻",
            style="SecondaryAction.TButton",
            width=4,
            command=lambda: self._rotate_selected_correction_annotation(-90.0),
        )
        rotate_right_button.pack(side=ui.LEFT, padx=(0, 4))
        self._attach_hover_help(rotate_right_button, label="Ausgewaehlte Markierung nach rechts drehen")

        sync_button = widgets.Button(
            transform_row,
            text="Durchdruecken",
            style="SecondaryAction.TButton",
            command=self._toggle_selected_annotation_sync,
        )
        sync_button.pack(side=ui.LEFT, padx=(12, 0))
        self._attach_hover_help(sync_button, label="Auswahl auf alle Personen spiegeln oder wieder lokal machen")

        widgets.Label(
            marker_controls,
            textvariable=self._correction_marker_info_var,
            style="Muted.TLabel",
        ).pack(anchor=ui.W, pady=(4, 0))
        widgets.Label(
            marker_controls,
            textvariable=self._correction_sync_info_var,
            style="Muted.TLabel",
        ).pack(anchor=ui.W, pady=(2, 0))
        widgets.Label(
            marker_controls,
            text="Zwischenablage: Strg+C kopieren, Strg+X ausschneiden, Strg+V einfuegen",
            style="Muted.TLabel",
        ).pack(anchor=ui.W, pady=(2, 0))

        correction_buttons = widgets.Frame(correction_form_panel, style="Surface.TFrame")
        correction_buttons.pack(fill=ui.X, pady=(10, 0))

        save_comments_button = widgets.Button(
            correction_buttons,
            text="PDF ueberschreiben",
            style="SecondaryAction.TButton",
            command=self._save_correction_annotations_to_pdfs,
        )
        save_comments_button.pack(side=ui.LEFT)
        self._attach_hover_help(save_comments_button, label="Original-PDF mit Markierungen ueberschreiben")

        prev_correction_student_button = widgets.Button(
            correction_buttons,
            text="◀ Person",
            style="SecondaryAction.TButton",
            command=lambda: self._change_correction_student(-1),
        )
        prev_correction_student_button.pack(side=ui.RIGHT)
        self._attach_hover_help(prev_correction_student_button, label="Vorherige Person in Korrektur", shortcut="Links")

        next_correction_student_button = widgets.Button(
            correction_buttons,
            text="Person ▶",
            style="SecondaryAction.TButton",
            command=lambda: self._change_correction_student(1),
        )
        next_correction_student_button.pack(side=ui.RIGHT, padx=(0, 8))
        self._attach_hover_help(next_correction_student_button, label="Naechste Person in Korrektur", shortcut="Rechts")

        widgets.Separator(shell).pack(fill=ui.X, pady=(10, 8))
        widgets.Label(shell, textvariable=self._status_var, style="Status.TLabel").pack(anchor=ui.W)

        self._hide_correction_controls()
        self._set_detail_submode("reading")
        self._show_view("overview")

    def render_overview_rows(self, rows: list[ExamOverviewRow]) -> None:
        self._rows_by_tree_id.clear()
        for item in self._tree.get_children():
            self._tree.delete(item)

        for row in rows:
            tree_id = self._tree.insert(
                "",
                ui.END,
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
        self._superpage_var.set(False)
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
        self._draft_regions.clear()
        self._hide_correction_controls()
        self._close_extra_popup()
        self._selected_region_id = None
        self._selected_region_kind = None
        self._clear_pending_redraw()
        self._refresh_region_tree()
        self._show_detail_mode()

    def on_exam_deleted(self, exam_id: str) -> None:
        if self._current_exam is None:
            return
        if self._current_exam.exam_id != exam_id:
            return
        self._return_to_overview()

    def on_exam_index_dir_changed(self, index_root: Path) -> None:
        self._exam_index_dir_value = str(index_root)
        self._return_to_overview()

    def sync_current_exam_from_repository(self) -> None:
        if self._current_exam is None:
            return

        exam_file = self.deps.exam_repository.index_root / f"{self._current_exam.exam_id}.json"
        if not exam_file.exists():
            self._return_to_overview()
            return

        exam = self.deps.exam_repository.load_exam(exam_file)
        self.open_exam_detail(exam, exam_file)

    def _apply_detail_labels(self, exam: ExamProject) -> None:
        progress = ProgressCalculator().compute(exam)

        self._detail_name.set(f"Name: {exam.exam_name}")
        self._detail_pages.set(f"Standardseiten: {exam.standard_page_count}")
        self._detail_students.set(f"Schüler:innen: {len(exam.students)}")
        self._detail_regions.set(f"Fertig korrigiert {progress.fully_finished_area_count}/{progress.total_area_count}")
        flags = []
        if progress.has_unassigned_extra_pages:
            flags.append("Extraseiten offen")
        if progress.has_missing_page_markings:
            flags.append("Seitenmarkierung fehlt")
        self._detail_status.set("Status: " + (", ".join(flags) if flags else "Keine offenen Warnungen"))
        self._refresh_active_student_label()

    def _on_escape(self, _event: ui.Event[ui.Misc]) -> None:
        self._sync_popup_sessions_from_windows()
        widget = self.root.focus_get()
        action = self._hsm_contract.resolve_escape_action(
            has_popup=self._popup_registry.has_active_popup(),
            has_inline_editor=isinstance(widget, (ui.Entry, widgets.Entry))
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
                    if not isinstance(child, ui.Toplevel):
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
            if isinstance(widget, (ui.Entry, widgets.Entry)):
                self.root.focus_set()
                return

            if self._correction_mode_active:
                self._stop_correction_mode()
                return

            if self._reading_active or self._extra_mode_active:
                self._leave_reading_view()
                return

        if action != ESCAPE_POP_PARENT or self._current_exam is None:
            self._status_var.set("Bereits in Gesamtübersicht")
            return

        self._current_exam = None
        self._detail_name.set("-")
        self._detail_pages.set("Standardseiten: -")
        self._detail_students.set("Schüler:innen: -")
        self._detail_regions.set("Fertig korrigiert -")
        self._detail_status.set("Status: -")
        self._active_student.set("Aktive Person: -")
        self._reading_active = False
        self._extra_mode_active = False
        self._extra_sequence = []
        self._correction_mode_active = False
        self._correction_student_indices = []
        self._reading_info_var.set("Einlesemodus: nicht aktiv")
        self._draft_regions.clear()
        self._reading_canvas.delete("all")
        self._hide_correction_controls()
        self._close_extra_popup()
        self._return_to_overview()

    def set_status(self, text: str) -> None:
        self._status_var.set(text)

    def _refresh_active_student_label(self) -> None:
        if self._active_view not in {"reading", "correction"}:
            self._active_student.set("Aktive Person: -")
            return

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

        if not self._reading_active and not self._extra_mode_active:
            self._active_student.set("Aktive Person: -")
            return

        if self._extra_mode_active and self._extra_sequence:
            student_index, _page_number = self._extra_sequence[self._extra_cursor]
            student = self._current_exam.students[student_index]
            self._active_student.set(
                f"Aktive Person: {student.display_name} ({self._extra_cursor + 1}/{len(self._extra_sequence)})"
            )
            return

        student = self._current_exam.students[self._reading_student_cursor]
        self._active_student.set(
            f"Aktive Person: {student.display_name} ({self._reading_student_cursor + 1}/{len(self._current_exam.students)})"
        )

    def _on_points_focus_out(self, _event: ui.Event[ui.Misc]) -> None:
        self._commit_points_if_possible()

    def _on_points_commit(self, _event: ui.Event[ui.Misc]) -> None:
        self._commit_points_if_possible()
        self.root.focus_set()

    def _on_points_escape(self, _event: ui.Event[ui.Misc]) -> None:
        self._commit_points_if_possible()
        self.root.focus_set()

    def _move_student(self, delta: int) -> None:
        if not self._current_exam or not self._current_exam.students:
            return
        self._commit_points_if_possible()
        if self._correction_mode_active and self._correction_student_indices:
            self._change_correction_student(delta)
            return
        self._student_cursor = (self._student_cursor + delta) % len(self._current_exam.students)
        self._refresh_active_student_label()
        self._focus_first_input_field()

    def _on_left_key(self, _event: ui.Event[ui.Misc]) -> None:
        if self._is_editable_widget(self.root.focus_get()) and not (
            self._active_view == "correction" and self._correction_mode_active
        ):
            return
        if self._active_view == "correction" and self._correction_mode_active:
            self._change_correction_student(-1)
            return
        if self._active_view == "reading" and self._detail_submode == "extra" and self._extra_mode_active:
            self._change_extra_page(-1)
            return
        if self._active_view == "reading" and self._detail_submode == "reading" and self._reading_active:
            self._change_reading_page(-1)
            return
        self._move_student(-1)

    def _on_right_key(self, _event: ui.Event[ui.Misc]) -> None:
        if self._is_editable_widget(self.root.focus_get()) and not (
            self._active_view == "correction" and self._correction_mode_active
        ):
            return
        if self._active_view == "correction" and self._correction_mode_active:
            self._change_correction_student(1)
            return
        if self._active_view == "reading" and self._detail_submode == "extra" and self._extra_mode_active:
            self._change_extra_page(1)
            return
        if self._active_view == "reading" and self._detail_submode == "reading" and self._reading_active:
            self._change_reading_page(1)
            return
        self._move_student(1)

    def _on_up_key(self, _event: ui.Event[ui.Misc]) -> None:
        if self._is_editable_widget(self.root.focus_get()) and not (
            self._active_view == "correction" and self._correction_mode_active
        ):
            return
        if self._active_view == "correction" and self._correction_mode_active:
            self._cycle_correction_task(-1)

    def _on_down_key(self, _event: ui.Event[ui.Misc]) -> None:
        if self._is_editable_widget(self.root.focus_get()) and not (
            self._active_view == "correction" and self._correction_mode_active
        ):
            return
        if self._active_view == "correction" and self._correction_mode_active:
            self._cycle_correction_task(1)

    def _on_ctrl_up_key(self, _event: ui.Event[ui.Misc]) -> None:
        if self._is_editable_widget(self.root.focus_get()) and not (
            self._active_view == "correction" and self._correction_mode_active
        ):
            return
        if self._active_view == "correction" and self._correction_mode_active:
            self._cycle_correction_area(-1)

    def _on_ctrl_down_key(self, _event: ui.Event[ui.Misc]) -> None:
        if self._is_editable_widget(self.root.focus_get()) and not (
            self._active_view == "correction" and self._correction_mode_active
        ):
            return
        if self._active_view == "correction" and self._correction_mode_active:
            self._cycle_correction_area(1)

    def _on_ctrl_space_key(self, _event: ui.Event[ui.Misc]):
        if self._active_view != "correction" or not self._correction_mode_active:
            return None
        if self._correction_finished_check is None:
            return "break"
        if str(self._correction_finished_check.cget("state")) == "disabled":
            return "break"
        self._correction_finished_var.set(not bool(self._correction_finished_var.get()))
        self._on_correction_finished_toggled()
        return "break"

    def _on_ctrl_e_key(self, _event: ui.Event[ui.Misc]):
        self._menu_export_scores()
        return "break"

    def _on_ctrl_plus_key(self, _event: ui.Event[ui.Misc]):
        if self._active_view != "correction" or not self._correction_mode_active:
            return None
        self._change_correction_zoom(10)
        return "break"

    def _on_ctrl_minus_key(self, _event: ui.Event[ui.Misc]):
        if self._active_view != "correction" or not self._correction_mode_active:
            return None
        self._change_correction_zoom(-10)
        return "break"

    def _on_ctrl_zero_key(self, _event: ui.Event[ui.Misc]):
        if self._active_view != "correction" or not self._correction_mode_active:
            return None
        self._reset_correction_zoom()
        return "break"

    def _on_ctrl_c_key(self, _event: ui.Event[ui.Misc]):
        if self._active_view != "correction" or not self._correction_mode_active:
            return None
        self._copy_selected_correction_annotation()
        return "break"

    def _on_ctrl_x_key(self, _event: ui.Event[ui.Misc]):
        if self._active_view != "correction" or not self._correction_mode_active:
            return None
        self._cut_selected_correction_annotation()
        return "break"

    def _on_ctrl_v_key(self, _event: ui.Event[ui.Misc]):
        if self._active_view != "correction" or not self._correction_mode_active:
            return None
        self._paste_correction_annotation()
        return "break"

    def _refresh_correction_zoom_label(self) -> None:
        self._correction_zoom_info_var.set(f"Zoom: {self._correction_zoom_percent}%")

    def _change_correction_zoom(self, delta: int) -> None:
        target = max(CORRECTION_ZOOM_MIN_PERCENT, min(CORRECTION_ZOOM_MAX_PERCENT, self._correction_zoom_percent + delta))
        if target == self._correction_zoom_percent:
            return
        self._correction_zoom_percent = target
        self._refresh_correction_zoom_label()
        self._render_correction_preview()

    def _reset_correction_zoom(self) -> None:
        if self._correction_zoom_percent == 100:
            return
        self._correction_zoom_percent = 100
        self._refresh_correction_zoom_label()
        self._render_correction_preview()

    def _commit_points_if_possible(self) -> None:
        if self._correction_mode_active:
            self._save_current_correction_score()
            self._save_current_correction_comment()
            return
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
        self._selected_region_id = None
        self._selected_region_kind = None
        self._set_detail_submode("reading")
        self._show_view("reading")
        self._refresh_region_tree()
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
        self._superpage_var.set(False)
        self._stop_correction_mode(silent=True)
        self._extra_sequence = sequence
        self._extra_cursor = 0
        self._selected_region_id = None
        self._selected_region_kind = None
        self._set_detail_submode("extra")
        self._show_view("reading")
        self._refresh_region_tree()
        self._render_current_extra_page()
        self._status_var.set("Extraseiten-Modus aktiv")

    def _change_reading_student(self, delta: int) -> None:
        if not self._reading_active or not self._current_exam or not self._current_exam.students:
            return
        self._reading_student_cursor = (self._reading_student_cursor + delta) % len(self._current_exam.students)
        if not bool(self._superpage_var.get()):
            student = self._current_exam.students[self._reading_student_cursor]
            self._reading_page = min(self._reading_page, max(student.page_count, 1))
        self._render_current_reading_page()

    def _change_reading_page(self, delta: int) -> None:
        if not self._reading_active:
            return
        new_page = self._reading_page + delta
        if bool(self._superpage_var.get()):
            max_page = self._max_available_page()
        else:
            student = self._get_reading_student()
            if student is None:
                return
            max_page = max(student.page_count, 1)
        self._reading_page = max(1, min(max_page, new_page))
        self._render_current_reading_page()

    def _get_reading_student(self) -> StudentExam | None:
        if not self._current_exam or not self._current_exam.students:
            return None
        return self._current_exam.students[self._reading_student_cursor]

    def _render_current_reading_page(self) -> None:
        student = self._get_reading_student()
        if student is None or self._current_exam is None:
            return

        if bool(self._superpage_var.get()):
            used = self._render_superposed_page(page_number=self._reading_page)
            max_page = self._max_available_page()
            if used > 0:
                self._reading_info_var.set(
                    f"Superseite | Seite {self._reading_page}/{max_page} | Quellen: {used}"
                )
            return

        self._render_pdf_page(student=student, page_number=self._reading_page)

        extra_marker = " (Extraseite)" if self._reading_page > self._current_exam.standard_page_count else ""
        self._reading_info_var.set(
            f"{student.display_name} | Seite {self._reading_page}/{student.page_count}{extra_marker}"
        )

    def _on_superpage_toggle(self) -> None:
        if not self._reading_active:
            self._superpage_var.set(False)
            return
        if bool(self._superpage_var.get()):
            self._reading_page = min(self._reading_page, self._max_available_page())
            self._status_var.set("Superseite aktiv")
        else:
            student = self._get_reading_student()
            if student is not None:
                self._reading_page = min(self._reading_page, max(student.page_count, 1))
            self._status_var.set("Superseite aus")
        self._render_current_reading_page()

    def _max_available_page(self) -> int:
        if self._current_exam is None or not self._current_exam.students:
            return 1
        return max(max(student.page_count, 1) for student in self._current_exam.students)

    def _render_superposed_page(self, *, page_number: int) -> int:
        if self._current_exam is None:
            return 0

        pixmaps: list[fitz.Pixmap] = []
        reference_rect: fitz.Rect | None = None
        target_width = 520.0

        for student in self._current_exam.students:
            if page_number > student.page_count:
                continue
            pdf_path = Path(self._current_exam.folder_path) / student.pdf_filename
            if not pdf_path.exists():
                continue

            document = self._doc_cache.get(student.pdf_filename)
            if document is None:
                try:
                    document = fitz.open(pdf_path)
                except Exception:
                    continue
                self._doc_cache[student.pdf_filename] = document

            try:
                page = document.load_page(page_number - 1)
            except Exception:
                continue

            if reference_rect is None:
                reference_rect = page.rect
            scale = target_width / max(reference_rect.width, 1.0)

            try:
                pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csGRAY, alpha=False)
            except Exception:
                continue

            if not pixmaps:
                pixmaps.append(pix)
                continue

            first = pixmaps[0]
            if pix.width == first.width and pix.height == first.height and pix.n == first.n:
                pixmaps.append(pix)

        if not pixmaps or reference_rect is None:
            self._reading_canvas.delete("all")
            self._reading_info_var.set("Superseite: Keine renderbaren Seiten vorhanden")
            return 0

        first = pixmaps[0]
        merged = bytearray(first.width * first.height)
        for y in range(first.height):
            source_start = y * first.stride
            target_start = y * first.width
            merged[target_start : target_start + first.width] = first.samples[source_start : source_start + first.width]

        for pix in pixmaps[1:]:
            for y in range(pix.height):
                source_start = y * pix.stride
                target_start = y * pix.width
                row = pix.samples[source_start : source_start + pix.width]
                for x, value in enumerate(row):
                    index = target_start + x
                    if value < merged[index]:
                        merged[index] = value

        pgm_header = f"P5 {first.width} {first.height} 255\n".encode("ascii")
        self._render_photo = ui.PhotoImage(data=pgm_header + bytes(merged), format="ppm")

        self._x_factor = reference_rect.width / max(first.width, 1)
        self._y_factor = reference_rect.height / max(first.height, 1)
        self._reading_canvas.configure(width=first.width, height=first.height)
        self._reading_canvas.delete("all")
        self._canvas_image_id = self._reading_canvas.create_image(0, 0, anchor=ui.NW, image=self._render_photo)
        self._reading_canvas.configure(scrollregion=(0, 0, first.width, first.height))
        self._draw_existing_regions("", page_number)
        return len(pixmaps)

    def _draw_existing_regions(self, student_pdf: str, page_number: int) -> None:
        if not self._current_exam:
            return

        if self._extra_mode_active:
            for assignment in self._current_exam.extra_page_assignments:
                if assignment.student_pdf != student_pdf or assignment.page_number != page_number:
                    continue
                x0 = assignment.box.x0 / self._x_factor
                y0 = assignment.box.y0 / self._y_factor
                x1 = assignment.box.x1 / self._x_factor
                y1 = assignment.box.y1 / self._y_factor
                is_selected = (
                    self._selected_region_kind == "extra"
                    and assignment.assignment_id == self._selected_region_id
                )
                rect_id = self._reading_canvas.create_rectangle(
                    x0,
                    y0,
                    x1,
                    y1,
                    outline="#d17a00" if is_selected else "#0b8f59",
                    width=3 if is_selected else 2,
                    tags=("region", f"extra:{assignment.assignment_id}"),
                )
                self._reading_canvas.tag_bind(rect_id, "<Button-1>", self._on_canvas_region_click)
        else:
            for region in self._current_exam.regions:
                if region.page_number != page_number:
                    continue
                x0 = region.box.x0 / self._x_factor
                y0 = region.box.y0 / self._y_factor
                x1 = region.box.x1 / self._x_factor
                y1 = region.box.y1 / self._y_factor
                is_selected = (
                    self._selected_region_kind == "region"
                    and region.region_id == self._selected_region_id
                )
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

        for draft in self._draft_regions.values():
            if self._extra_mode_active:
                if draft.student_pdf != student_pdf or draft.page_number != page_number:
                    continue
            else:
                if draft.student_pdf:
                    continue
                if draft.page_number != page_number:
                    continue
            x0 = draft.box[0] / self._x_factor
            y0 = draft.box[1] / self._y_factor
            x1 = draft.box[2] / self._x_factor
            y1 = draft.box[3] / self._y_factor
            is_selected = self._selected_region_kind == "draft" and draft.draft_id == self._selected_region_id
            rect_id = self._reading_canvas.create_rectangle(
                x0,
                y0,
                x1,
                y1,
                outline="#d17a00" if is_selected else "#1f6feb",
                dash=(4, 2),
                width=3 if is_selected else 2,
                tags=("region", f"draft:{draft.draft_id}"),
            )
            self._reading_canvas.tag_bind(rect_id, "<Button-1>", self._on_canvas_region_click)

    def _on_canvas_region_click(self, event: ui.Event[ui.Misc]) -> None:
        current = self._reading_canvas.find_withtag("current")
        if not current:
            return
        tags = self._reading_canvas.gettags(current[0])
        region_tag = next(
            (tag for tag in tags if tag.startswith("region:") or tag.startswith("extra:") or tag.startswith("draft:")),
            None,
        )
        if region_tag is None:
            return
        region_id = region_tag.split(":", 1)[1]
        self._select_region_by_id(region_id)
        self._rerender_active_page()

    def _on_canvas_press(self, event: ui.Event[ui.Misc]) -> None:
        if not self._reading_active and not self._extra_mode_active:
            return
        x = float(self._reading_canvas.canvasx(event.x))
        y = float(self._reading_canvas.canvasy(event.y))
        self._drag_start = (x, y)
        if self._drag_rect_id is not None:
            self._reading_canvas.delete(self._drag_rect_id)
        self._drag_rect_id = self._reading_canvas.create_rectangle(
            x,
            y,
            x,
            y,
            outline="#1f6feb",
            width=2,
        )

    def _on_canvas_drag(self, event: ui.Event[ui.Misc]) -> None:
        if self._drag_start is None or self._drag_rect_id is None:
            return
        x0, y0 = self._drag_start
        x1 = float(self._reading_canvas.canvasx(event.x))
        y1 = float(self._reading_canvas.canvasy(event.y))
        self._reading_canvas.coords(self._drag_rect_id, x0, y0, x1, y1)

    def _on_canvas_release(self, event: ui.Event[ui.Misc]) -> None:
        if (not self._reading_active and not self._extra_mode_active) or self._drag_start is None:
            return
        if self._drag_rect_id is None:
            self._drag_start = None
            return

        x0, y0 = self._drag_start
        x1 = float(self._reading_canvas.canvasx(event.x))
        y1 = float(self._reading_canvas.canvasy(event.y))
        if abs(x1 - x0) < 5 or abs(y1 - y0) < 5:
            self._reading_canvas.delete(self._drag_rect_id)
            self._drag_rect_id = None
            self._drag_start = None
            return

        context = self._current_canvas_context()
        if context is None:
            self._reading_canvas.delete(self._drag_rect_id)
            self._drag_rect_id = None
            self._drag_start = None
            return
        student, page_number = context

        box = (
            min(x0, x1) * self._x_factor,
            min(y0, y1) * self._y_factor,
            max(x0, x1) * self._x_factor,
            max(y0, y1) * self._y_factor,
        )

        if self._try_apply_pending_redraw(student_pdf=student.pdf_filename, page_number=page_number, box=box):
            self._reading_canvas.delete(self._drag_rect_id)
            self._drag_rect_id = None
            self._drag_start = None
            self._rerender_active_page()
            return

        draft_id = f"draft-{uuid4().hex[:10]}"
        draft_student_pdf = student.pdf_filename if self._extra_mode_active else ""
        draft = DraftRegion(
            draft_id=draft_id,
            student_pdf=draft_student_pdf,
            page_number=page_number,
            box=box,
            area_codes=[self._next_area_label()],
            task_specs=[],
        )
        self._draft_regions[draft_id] = draft

        self._selected_region_id = draft_id
        self._selected_region_kind = "draft"
        self._active_region_var.set("Draft")
        self._quick_tasks_var.set("")
        self._form_tasks_text.delete("1.0", ui.END)
        self._refresh_region_tree()
        self._select_region_by_id(draft_id)

        self._rerender_active_page()
        self._drag_rect_id = None
        self._drag_start = None
        if self._extra_mode_active:
            self._status_var.set("Extraseiten-Bereich markiert. Bereich(e) eintragen und Speichern klicken.")
        else:
            self._status_var.set("Bereich markiert. Jetzt Aufgaben eintragen und Speichern klicken.")

    def _arm_redraw_selected_region(self) -> None:
        if self._selected_region_id is None or self._selected_region_kind not in {"region", "extra"}:
            messagebox.showinfo("Hinweis", "Bitte zuerst einen bestehenden Bereich auswaehlen (kein Draft).")
            return
        if self._extra_mode_active and self._selected_region_kind != "extra":
            messagebox.showinfo("Hinweis", "Im Extraseitenmodus kann nur eine Extraseiten-Zuordnung neu gezogen werden.")
            return
        if not self._extra_mode_active and self._selected_region_kind != "region":
            messagebox.showinfo("Hinweis", "Im Einlesemodus kann nur ein Standardbereich neu gezogen werden.")
            return
        self._redraw_target_region_kind = self._selected_region_kind
        self._redraw_target_region_id = self._selected_region_id
        self._redraw_on_next_box = True
        self._status_var.set("Neuziehen aktiv: Die naechste gezogene Box ueberschreibt den ausgewaehlten Bereich.")

    def _clear_pending_redraw(self) -> None:
        self._redraw_target_region_kind = None
        self._redraw_target_region_id = None
        self._redraw_on_next_box = False

    def _try_apply_pending_redraw(
        self,
        *,
        student_pdf: str,
        page_number: int,
        box: tuple[float, float, float, float],
    ) -> bool:
        if not self._redraw_on_next_box or self._redraw_target_region_id is None:
            return False
        if self._controller is None or self._current_exam is None:
            self._clear_pending_redraw()
            return False

        if self._redraw_target_region_kind == "extra":
            assignment = next(
                (item for item in self._current_exam.extra_page_assignments if item.assignment_id == self._redraw_target_region_id),
                None,
            )
            if assignment is None:
                self._clear_pending_redraw()
                messagebox.showerror("Bereich fehlt", "Die ausgewaehlte Extraseiten-Zuordnung konnte nicht gefunden werden.")
                return False

            updated = self._controller.assign_extra_page_immediate(
                exam=self._current_exam,
                student_pdf=student_pdf,
                page_number=page_number,
                box=box,
                area_codes=assignment.assigned_area_codes,
                assignment_id=assignment.assignment_id,
            )
            self._clear_pending_redraw()
            if updated is None:
                return True

            self._current_exam = updated
            self._refresh_region_tree()
            self._select_region_by_id(assignment.assignment_id)
            self._apply_detail_labels(updated)
            area_text = assignment.assigned_area_codes[0] if assignment.assigned_area_codes else assignment.assignment_id
            self._status_var.set(f"Extraseiten-Bereich {area_text} neu gezogen und ueberschrieben.")
            return True

        region = next(
            (item for item in self._current_exam.regions if item.region_id == self._redraw_target_region_id),
            None,
        )
        if region is None:
            self._clear_pending_redraw()
            messagebox.showerror("Bereich fehlt", "Der ausgewaehlte Bereich konnte nicht mehr gefunden werden.")
            return False

        task_specs = [(task.code, float(task.max_points)) for task in region.tasks]
        updated = self._controller.upsert_region_immediate(
            exam=self._current_exam,
            student_pdf="",
            page_number=page_number,
            box=box,
            task_specs=task_specs,
            area_codes=region.assigned_area_codes,
            region_id=region.region_id,
        )
        self._clear_pending_redraw()
        if updated is None:
            return True

        self._current_exam = updated
        self._refresh_region_tree()
        self._select_region_by_id(region.region_id)
        self._apply_detail_labels(updated)
        area_text = region.assigned_area_codes[0] if region.assigned_area_codes else region.region_id
        self._status_var.set(f"Bereich {area_text} neu gezogen und ueberschrieben.")
        return True

    def _on_canvas_mousewheel(self, event: ui.Event[ui.Misc]) -> None:
        if not self._reading_active and not self._extra_mode_active:
            return
        step = int(-1 * (event.delta / 120)) if event.delta else 0
        if step:
            self._reading_canvas.yview_scroll(step, "units")

    def _on_canvas_shift_mousewheel(self, event: ui.Event[ui.Misc]) -> None:
        if not self._reading_active and not self._extra_mode_active:
            return
        step = int(-1 * (event.delta / 120)) if event.delta else 0
        if step:
            self._reading_canvas.xview_scroll(step, "units")

    @staticmethod
    def _wheel_direction(event: ui.Event[ui.Misc]) -> int:
        if getattr(event, "num", None) == 4:
            return 1
        if getattr(event, "num", None) == 5:
            return -1
        delta = getattr(event, "delta", 0)
        if delta > 0:
            return 1
        if delta < 0:
            return -1
        return 0

    def _on_correction_mousewheel(self, event: ui.Event[ui.Misc]):
        if self._active_view != "correction" or not self._correction_mode_active:
            return None

        direction = self._wheel_direction(event)
        if direction == 0:
            return "break"

        state = getattr(event, "state", 0)
        shift_pressed = bool(state & 0x0001)
        control_pressed = bool(state & 0x0004)
        if control_pressed:
            self._change_correction_zoom(10 if direction > 0 else -10)
            return "break"

        scroll_units = -direction
        if shift_pressed:
            self._correction_canvas.xview_scroll(scroll_units, "units")
        else:
            self._correction_canvas.yview_scroll(scroll_units, "units")
        return "break"

    def _current_canvas_context(self) -> tuple[StudentExam, int] | None:
        if self._current_exam is None:
            return None
        if self._extra_mode_active and self._extra_sequence:
            student_index, page_number = self._extra_sequence[self._extra_cursor]
            return self._current_exam.students[student_index], page_number
        student = self._get_reading_student()
        if student is None:
            return None
        return student, self._reading_page

    def _rerender_active_page(self) -> None:
        if self._extra_mode_active:
            self._render_current_extra_page()
            return
        self._render_current_reading_page()

    def _next_area_label(self) -> str:
        if self._current_exam is None:
            return "A"
        if self._extra_mode_active:
            existing = self._existing_standard_areas()
            return existing[0] if existing else "A"
        standard_region_count = len(self._current_exam.regions)
        standard_draft_count = sum(
            1
            for draft in self._draft_regions.values()
            if self._current_exam is not None and draft.student_pdf == ""
        )
        return self._index_to_area_label(standard_region_count + standard_draft_count)

    def _finish_reading_mode(self) -> None:
        if not self._current_exam or not self._controller:
            return
        updated = self._controller.finish_reading_mode(exam=self._current_exam)
        self._current_exam = updated
        self._apply_detail_labels(updated)
        self._reading_active = False
        self._reading_info_var.set("Einlesemodus: abgeschlossen")
        self._show_detail_mode()

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
        for assignment in self._current_exam.extra_page_assignments:
            if assignment.student_pdf == student_pdf and assignment.page_number == page_number:
                for code in assignment.assigned_area_codes:
                    if code not in result:
                        result.append(code)
        return result

    def _assign_current_extra_page(self) -> None:
        if not self._extra_mode_active or not self._extra_sequence or not self._current_exam or not self._controller:
            return

        student_index, page_number = self._extra_sequence[self._extra_cursor]
        student = self._current_exam.students[student_index]

        default_areas = ",".join(self._existing_standard_areas()[:1] or ["A"])
        raw_areas = simpledialog.askstring(
            "Extraseite zuordnen",
            "Bestehende Bereich(e) fuer Extraseite eingeben (z. B. A,B)",
            initialvalue=default_areas,
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

            self._render_photo = ui.PhotoImage(data=pix.tobytes("ppm"), format="ppm")
            self._reading_canvas.configure(width=pix.width, height=pix.height)
            self._reading_canvas.delete("all")
            self._canvas_image_id = self._reading_canvas.create_image(0, 0, anchor=ui.NW, image=self._render_photo)
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
        values = tuple(areas)
        self._correction_area_combo["values"] = values
        if hasattr(self, "_correction_area_combo_view"):
            self._correction_area_combo_view["values"] = values
        if self._correction_area_var.get() not in areas:
            self._correction_area_var.set(areas[0])

    def _existing_standard_areas(self) -> list[str]:
        if self._current_exam is None:
            return []
        return sorted(
            {
                code.strip().upper()
                for region in self._current_exam.regions
                for code in region.assigned_area_codes
                if code.strip()
            }
        )

    def _start_correction_mode(self) -> None:
        if not self._current_exam:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Klausur öffnen.")
            return
        templates = self._build_correction_templates(self._current_exam)
        if not templates:
            messagebox.showinfo("Keine Bereiche", "Bitte zuerst Standardbereiche im Einlesemodus markieren und speichern.")
            return

        area = self._correction_area_var.get().strip().upper()
        if area not in templates:
            area = sorted(templates.keys())[0]
            self._correction_area_var.set(area)

        indices = list(range(len(self._current_exam.students)))
        if not indices:
            messagebox.showinfo("Keine Fälle", "Diese Klausur enthält keine Schüler:innen.")
            return

        self._reading_active = False
        self._extra_mode_active = False
        self._extra_sequence = []
        self._close_extra_popup()
        self._correction_mode_active = True
        self._correction_zoom_percent = 100
        self._refresh_correction_zoom_label()
        self._correction_selected_annotation_id = None
        self._correction_drag_annotation_id = None
        self._correction_drag_offset_pdf = None
        self._correction_templates = templates
        self._correction_student_indices = indices
        self._correction_cursor = 0
        self._student_cursor = indices[0]
        self._set_correction_marker_tool(self._correction_marker_tool_key)
        self._show_view("correction")
        self._refresh_active_student_label()
        self._refresh_correction_task_choices(load_saved_points=True)
        self._refresh_correction_completion_controls()
        self._focus_first_input_field()
        self._status_var.set(f"Korrekturmodus aktiv für Bereich {area}")

    def _stop_correction_mode(self, *, silent: bool = False) -> None:
        self._commit_points_if_possible()
        self._correction_mode_active = False
        self._correction_templates = {}
        self._correction_task_items = []
        self._correction_student_indices = []
        self._correction_cursor = 0
        self._correction_clip_box = None
        self._correction_scale = 1.0
        self._correction_selected_annotation_id = None
        self._correction_drag_annotation_id = None
        self._correction_drag_offset_pdf = None
        self._correction_annotation_items.clear()
        self._correction_finished_var.set(False)
        self._refresh_correction_completion_controls()
        self._close_extra_popup()
        self._refresh_active_student_label()
        self._show_detail_mode()
        if not silent:
            self._status_var.set("Korrekturmodus beendet")

    @staticmethod
    def _build_correction_templates(exam: ExamProject) -> dict[str, CorrectionTemplate]:
        templates: dict[str, CorrectionTemplate] = {}
        ordered_regions = sorted(
            (region for region in exam.regions if region.assigned_area_codes),
            key=lambda item: (item.assigned_area_codes[0], item.page_number, item.region_id),
        )
        for region in ordered_regions:
            area_code = region.assigned_area_codes[0].strip().upper()
            if not area_code or area_code in templates:
                continue
            templates[area_code] = CorrectionTemplate(
                area_code=area_code,
                page_number=region.page_number,
                box=(region.box.x0, region.box.y0, region.box.x1, region.box.y1),
                tasks=[TaskDefinition(code=task.code, name=task.name, max_points=task.max_points) for task in region.tasks],
            )
        return templates

    def _refresh_correction_task_choices(self, *, load_saved_points: bool) -> None:
        area_code = self._correction_area_var.get().strip().upper()
        template = self._correction_templates.get(area_code)
        if template is None:
            self._correction_task_items = []
            self._correction_selected_annotation_id = None
            self._correction_task_combo["values"] = ()
            self._correction_task_var.set("")
            self._correction_max_points_var.set("Max: -")
            self._correction_points_var.set("")
            self._correction_comment_var.set("")
            self._render_correction_preview()
            return

        self._correction_task_items = [(task.code, float(task.max_points)) for task in template.tasks]
        labels = tuple(f"{code} ({max_points:g})" for code, max_points in self._correction_task_items)
        self._correction_task_combo["values"] = labels
        if labels:
            current = self._correction_task_var.get()
            if current not in labels:
                self._correction_task_var.set(labels[0])
        else:
            self._correction_task_var.set("")
        self._refresh_correction_task_meta(load_saved_points=load_saved_points)
        self._render_correction_preview()
        self._refresh_correction_completion_controls()

    def _refresh_correction_task_meta(self, *, load_saved_points: bool) -> None:
        task_code, max_points = self._selected_correction_task()
        if task_code is None:
            self._correction_max_points_var.set("Max: -")
            if load_saved_points:
                self._correction_points_var.set("")
                self._correction_comment_var.set("")
            self._refresh_correction_completion_controls()
            return

        self._correction_max_points_var.set(f"Max: {max_points:g}")
        if not load_saved_points or self._controller is None or self._current_exam is None:
            return
        student = self._current_correction_student()
        if student is None:
            return
        existing_points = self._controller.load_saved_points(
            exam=self._current_exam,
            student_id=student.student_id,
            task_code=task_code,
        )
        existing_comment = self._controller.load_saved_comment(
            exam=self._current_exam,
            student_id=student.student_id,
            task_code=task_code,
        )
        self._correction_points_var.set(existing_points if existing_points is not None else "")
        self._correction_comment_var.set(existing_comment if existing_comment is not None else "")
        self._refresh_correction_completion_controls()

    def _cycle_combobox_value(self, combo: widgets.Combobox, value_var: ui.StringVar, delta: int) -> bool:
        values = tuple(str(item) for item in combo.cget("values"))
        if not values:
            return False
        current = value_var.get()
        if current in values:
            current_index = values.index(current)
        else:
            current_index = 0
        value_var.set(values[(current_index + delta) % len(values)])
        return True

    def _cycle_correction_task(self, delta: int) -> None:
        if not self._correction_mode_active:
            return
        self._save_current_correction_score()
        self._save_current_correction_comment()
        if not self._cycle_combobox_value(self._correction_task_combo, self._correction_task_var, delta):
            return
        self._correction_selected_annotation_id = None
        self._refresh_correction_task_meta(load_saved_points=True)
        self._focus_first_input_field()

    def _cycle_correction_area(self, delta: int) -> None:
        if not self._correction_mode_active:
            return
        self._save_current_correction_score()
        self._save_current_correction_comment()
        if not self._cycle_combobox_value(self._correction_area_combo_view, self._correction_area_var, delta):
            return
        self._correction_selected_annotation_id = None
        self._refresh_correction_task_choices(load_saved_points=True)
        self._focus_first_input_field()

    def _all_tasks_scored_for_current_area(self) -> bool:
        if self._controller is None or self._current_exam is None:
            return False
        student = self._current_correction_student()
        if student is None:
            return False
        if not self._correction_task_items:
            return False
        return all(
            self._controller.load_saved_points(
                exam=self._current_exam,
                student_id=student.student_id,
                task_code=code,
            )
            is not None
            for code, _max_points in self._correction_task_items
        )

    def _is_current_person_area_finished(self) -> bool:
        if self._controller is None or self._current_exam is None:
            return False
        student = self._current_correction_student()
        if student is None:
            return False
        return self._controller.is_person_area_finished(
            exam=self._current_exam,
            student_id=student.student_id,
            area_code=self._correction_area_var.get(),
        )

    def _refresh_correction_completion_controls(self) -> None:
        if self._correction_finished_check is None:
            return

        can_toggle = self._correction_mode_active and self._all_tasks_scored_for_current_area()
        is_finished = self._is_current_person_area_finished() if self._correction_mode_active else False
        self._correction_finished_var.set(is_finished)

        self._correction_finished_check.configure(state="normal" if (can_toggle or is_finished) else "disabled")
        if is_finished:
            self._correction_finished_hint_var.set("Fertig markiert: Punkteingabe ist gesperrt")
        elif can_toggle:
            self._correction_finished_hint_var.set("Alle Aufgaben bewertet: Fertig kann gesetzt werden")
        else:
            self._correction_finished_hint_var.set("Fertig wird aktiv, sobald alle Aufgaben bewertet sind")

        self._correction_points_entry.configure(state="disabled" if is_finished else "normal")
        if self._save_correction_button is not None:
            self._save_correction_button.configure(state="disabled" if is_finished else "normal")

    def _on_correction_finished_toggled(self) -> None:
        if not self._correction_mode_active or self._controller is None or self._current_exam is None:
            return

        student = self._current_correction_student()
        if student is None:
            return

        requested = bool(self._correction_finished_var.get())
        if requested and not self._all_tasks_scored_for_current_area():
            self._correction_finished_var.set(False)
            messagebox.showinfo("Hinweis", "Bitte zuerst alle Aufgaben im Bereich bewerten.")
            self._refresh_correction_completion_controls()
            return

        updated = self._controller.set_person_area_finished_immediate(
            exam=self._current_exam,
            student_id=student.student_id,
            area_code=self._correction_area_var.get(),
            is_finished=requested,
        )
        if updated is None:
            self._refresh_correction_completion_controls()
            return

        self._current_exam = updated
        self._apply_detail_labels(updated)
        self._refresh_correction_completion_controls()

    def _current_correction_student(self) -> StudentExam | None:
        if not self._current_exam or not self._correction_student_indices:
            return None
        index = self._correction_student_indices[self._correction_cursor]
        return self._current_exam.students[index]

    def _selected_correction_task(self) -> tuple[str | None, float]:
        selected = self._correction_task_var.get().strip()
        for code, max_points in self._correction_task_items:
            if selected.startswith(f"{code} ") or selected == code:
                return code, max_points
        return None, 0.0

    @staticmethod
    def _marker_tool_lookup(tool_key: str) -> tuple[str, str] | None:
        for key, glyph, label in CORRECTION_MARKER_TOOLS:
            if key == tool_key:
                return glyph, label
        return None

    def _set_correction_marker_tool(self, tool_key: str) -> None:
        lookup = self._marker_tool_lookup(tool_key)
        if lookup is None:
            return
        _glyph, label = lookup
        self._correction_marker_tool_key = tool_key
        self._correction_marker_info_var.set(f"Markierung: {label}")

    def _on_correction_marker_color_changed(self, _event: ui.Event[ui.Misc]) -> None:
        color_name = self._correction_marker_color_name_var.get()
        if color_name not in CORRECTION_MARKER_COLORS:
            color_name = CORRECTION_DEFAULT_COLOR_NAME
            self._correction_marker_color_name_var.set(color_name)

        annotation = self._selected_correction_annotation()
        if annotation is None:
            return

        color_hex = CORRECTION_MARKER_COLORS.get(color_name, CORRECTION_MARKER_COLORS[CORRECTION_DEFAULT_COLOR_NAME])
        for item in self._sync_group_members(annotation, include_detached=True):
            item.color_hex = color_hex
        self._render_correction_annotations()
        self._status_var.set("Markierungsfarbe aktualisiert")

    @staticmethod
    def _normalize_marker_color_hex(raw_color: object) -> str:
        value = str(raw_color or "").strip().lower()
        if len(value) == 7 and value.startswith("#"):
            return value
        return CORRECTION_MARKER_COLORS[CORRECTION_DEFAULT_COLOR_NAME]

    @staticmethod
    def _normalize_marker_font_size(raw_size: object) -> float:
        try:
            size = float(raw_size)
        except (TypeError, ValueError):
            size = CORRECTION_DEFAULT_FONT_SIZE_PT
        return max(8.0, min(96.0, size))

    @staticmethod
    def _marker_color_name_for_hex(color_hex: str) -> str:
        normalized = MainWindow._normalize_marker_color_hex(color_hex)
        for name, hex_value in CORRECTION_MARKER_COLORS.items():
            if hex_value.lower() == normalized:
                return name
        return CORRECTION_DEFAULT_COLOR_NAME

    @staticmethod
    def _event_has_alt_modifier(event: ui.Event[ui.Misc]) -> bool:
        state = int(getattr(event, "state", 0) or 0)
        return any(bool(state & mask) for mask in CORRECTION_ALT_MODIFIER_MASKS)

    def _current_marker_color_hex(self) -> str:
        selected = self._correction_marker_color_name_var.get()
        if selected in CORRECTION_MARKER_COLORS:
            return CORRECTION_MARKER_COLORS[selected]
        return self._default_annotation_color_hex

    @staticmethod
    def _hex_to_rgb_fraction(color_hex: str) -> tuple[float, float, float]:
        raw = color_hex.strip().lstrip("#")
        if len(raw) != 6:
            return (0.0, 0.0, 0.0)
        try:
            red = int(raw[0:2], 16) / 255.0
            green = int(raw[2:4], 16) / 255.0
            blue = int(raw[4:6], 16) / 255.0
        except ValueError:
            return (0.0, 0.0, 0.0)
        return red, green, blue

    def _current_correction_annotations(self) -> list[PdfAnnotation]:
        if self._current_exam is None:
            return []
        student = self._current_correction_student()
        area_code = self._correction_area_var.get().strip().upper()
        template = self._current_correction_template()
        if student is None or template is None:
            return []
        return [
            item
            for item in self._current_exam.pdf_annotations
            if item.student_pdf == student.pdf_filename and item.page_number == template.page_number
            and (not item.area_code or item.area_code == area_code)
        ]

    def _current_correction_template(self) -> CorrectionTemplate | None:
        area_code = self._correction_area_var.get().strip().upper()
        return self._correction_templates.get(area_code)

    def _selected_correction_annotation(self) -> PdfAnnotation | None:
        if self._correction_selected_annotation_id is None:
            return None
        annotation = self._annotation_by_id(self._correction_selected_annotation_id)
        if annotation is None:
            return None

        visible_ids = {item.annotation_id for item in self._current_correction_annotations()}
        if annotation.annotation_id not in visible_ids:
            return None
        return annotation

    def _sync_group_members(self, annotation: PdfAnnotation, *, include_detached: bool) -> list[PdfAnnotation]:
        if self._current_exam is None or not annotation.sync_group_id:
            return [annotation]

        members = [item for item in self._current_exam.pdf_annotations if item.sync_group_id == annotation.sync_group_id]
        if include_detached:
            return members
        return [item for item in members if not item.position_detached]

    def _delete_annotation_or_group(self, annotation: PdfAnnotation) -> int:
        if self._current_exam is None:
            return 0

        before = len(self._current_exam.pdf_annotations)
        if annotation.sync_group_id:
            self._current_exam.pdf_annotations = [
                item for item in self._current_exam.pdf_annotations if item.sync_group_id != annotation.sync_group_id
            ]
        else:
            self._current_exam.pdf_annotations = [
                item for item in self._current_exam.pdf_annotations if item.annotation_id != annotation.annotation_id
            ]
        removed = before - len(self._current_exam.pdf_annotations)
        if removed > 0:
            self._correction_selected_annotation_id = None
        return removed

    def _refresh_correction_sync_info(self) -> None:
        annotation = self._selected_correction_annotation()
        if annotation is None:
            self._correction_sync_info_var.set("Sync: keine Auswahl")
            return

        if not annotation.sync_group_id:
            self._correction_sync_info_var.set("Sync: lokal")
            return

        members = self._sync_group_members(annotation, include_detached=True)
        detached_suffix = " | Position lokal geloest (Alt-Drag)" if annotation.position_detached else ""
        self._correction_sync_info_var.set(f"Sync: aktiv ({len(members)} Kopien){detached_suffix}")

    def _toggle_selected_annotation_sync(self) -> None:
        annotation = self._selected_correction_annotation()
        if annotation is None:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Markierung auswaehlen.")
            return

        if annotation.sync_group_id:
            removed = self._disable_selected_annotation_sync(annotation)
            if removed <= 0:
                return
            self._render_correction_annotations()
            self._status_var.set("Durchdruecken deaktiviert: Kopien bei anderen Personen entfernt")
            return

        created = self._enable_selected_annotation_sync(annotation)
        if created <= 0:
            return
        self._render_correction_annotations()
        self._status_var.set(f"Durchgedrueckt: {created} Kopien erzeugt")

    def _enable_selected_annotation_sync(self, annotation: PdfAnnotation) -> int:
        if self._current_exam is None:
            return 0

        template = self._current_correction_template()
        if template is None:
            return 0

        sync_group_id = f"sg-{uuid4().hex[:12]}"
        annotation.sync_group_id = sync_group_id
        annotation.position_detached = False

        created = 0
        for student_index in self._correction_student_indices:
            student = self._current_exam.students[student_index]
            if student.pdf_filename == annotation.student_pdf:
                continue
            clone = PdfAnnotation(
                annotation_id=f"ann-{uuid4().hex[:12]}",
                student_pdf=student.pdf_filename,
                page_number=template.page_number,
                annotation_type=annotation.annotation_type,
                content=annotation.content,
                color_hex=annotation.color_hex,
                x=annotation.x,
                y=annotation.y,
                task_code=annotation.task_code,
                area_code=annotation.area_code,
                font_size=annotation.font_size,
                rotation_deg=annotation.rotation_deg,
                sync_group_id=sync_group_id,
                position_detached=False,
            )
            self._current_exam.pdf_annotations.append(clone)
            created += 1
        return created

    def _disable_selected_annotation_sync(self, annotation: PdfAnnotation) -> int:
        if self._current_exam is None or not annotation.sync_group_id:
            return 0

        before = len(self._current_exam.pdf_annotations)
        sync_group_id = annotation.sync_group_id
        self._current_exam.pdf_annotations = [
            item
            for item in self._current_exam.pdf_annotations
            if item.sync_group_id != sync_group_id or item.annotation_id == annotation.annotation_id
        ]
        annotation.sync_group_id = ""
        annotation.position_detached = False
        return before - len(self._current_exam.pdf_annotations)

    def _copy_selected_correction_annotation(self) -> bool:
        annotation = self._selected_correction_annotation()
        if annotation is None:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Markierung auswaehlen.")
            return False

        clip_box = self._resolve_annotation_clip_box(annotation, self._correction_templates)
        if clip_box is None:
            messagebox.showinfo("Hinweis", "Die Markierung liegt ausserhalb eines gueltigen Bereichs.")
            return False

        width = max(1e-6, clip_box[2] - clip_box[0])
        height = max(1e-6, clip_box[3] - clip_box[1])
        rel_x = (annotation.x - clip_box[0]) / width
        rel_y = (annotation.y - clip_box[1]) / height

        self._annotation_clipboard = {
            "annotation_type": annotation.annotation_type,
            "content": annotation.content,
            "color_hex": self._normalize_marker_color_hex(annotation.color_hex),
            "font_size": self._normalize_marker_font_size(annotation.font_size),
            "rotation_deg": self._normalize_rotation_deg(annotation.rotation_deg),
            "task_code": annotation.task_code,
            "rel_x": rel_x,
            "rel_y": rel_y,
        }
        self._status_var.set("Markierung kopiert")
        return True

    def _cut_selected_correction_annotation(self) -> bool:
        if not self._copy_selected_correction_annotation():
            return False
        annotation = self._selected_correction_annotation()
        if annotation is None:
            return False

        removed = self._delete_annotation_or_group(annotation)
        if removed <= 0:
            return False
        self._render_correction_annotations()
        if annotation.sync_group_id:
            self._status_var.set(f"Sync-Gruppe ausgeschnitten ({removed} Markierungen)")
        else:
            self._status_var.set("Markierung ausgeschnitten")
        return True

    def _paste_correction_annotation(self) -> bool:
        if self._current_exam is None:
            return False
        if not self._annotation_clipboard:
            messagebox.showinfo("Hinweis", "Zwischenablage ist leer.")
            return False

        student = self._current_correction_student()
        template = self._current_correction_template()
        area_code = self._correction_area_var.get().strip().upper()
        if student is None or template is None:
            return False

        rel_x = float(self._annotation_clipboard.get("rel_x", 0.5))
        rel_y = float(self._annotation_clipboard.get("rel_y", 0.5))
        x0, y0, x1, y1 = template.box
        target_x = x0 + rel_x * (x1 - x0)
        target_y = y0 + rel_y * (y1 - y0)

        annotation = PdfAnnotation(
            annotation_id=f"ann-{uuid4().hex[:12]}",
            student_pdf=student.pdf_filename,
            page_number=template.page_number,
            annotation_type=str(self._annotation_clipboard.get("annotation_type", "symbol")),
            content=str(self._annotation_clipboard.get("content", "")).strip(),
            color_hex=self._normalize_marker_color_hex(self._annotation_clipboard.get("color_hex")),
            x=target_x,
            y=target_y,
            task_code=str(self._annotation_clipboard.get("task_code", "")).strip().upper(),
            area_code=area_code,
            font_size=self._normalize_marker_font_size(self._annotation_clipboard.get("font_size", 14.0)),
            rotation_deg=self._normalize_rotation_deg(float(self._annotation_clipboard.get("rotation_deg", 0.0))),
            sync_group_id="",
            position_detached=False,
        )
        self._upsert_annotation(annotation)
        self._correction_selected_annotation_id = annotation.annotation_id
        self._render_correction_annotations()
        self._status_var.set("Markierung eingefuegt")
        return True

    def _annotation_by_id(self, annotation_id: str) -> PdfAnnotation | None:
        if self._current_exam is None:
            return None
        return next((item for item in self._current_exam.pdf_annotations if item.annotation_id == annotation_id), None)

    def _canvas_to_pdf_coords(self, x: float, y: float) -> tuple[float, float] | None:
        if self._correction_clip_box is None or self._correction_scale <= 0:
            return None
        clip_x0, clip_y0, _clip_x1, _clip_y1 = self._correction_clip_box
        return clip_x0 + (x / self._correction_scale), clip_y0 + (y / self._correction_scale)

    def _pdf_to_canvas_coords(self, x: float, y: float) -> tuple[float, float] | None:
        if self._correction_clip_box is None or self._correction_scale <= 0:
            return None
        clip_x0, clip_y0, _clip_x1, _clip_y1 = self._correction_clip_box
        return (x - clip_x0) * self._correction_scale, (y - clip_y0) * self._correction_scale

    def _upsert_annotation(self, annotation: PdfAnnotation) -> None:
        if self._current_exam is None:
            return
        for index, existing in enumerate(self._current_exam.pdf_annotations):
            if existing.annotation_id == annotation.annotation_id:
                self._current_exam.pdf_annotations[index] = annotation
                return
        self._current_exam.pdf_annotations.append(annotation)

    @staticmethod
    def _point_in_box(x: float, y: float, box: tuple[float, float, float, float]) -> bool:
        x0, y0, x1, y1 = box
        return x0 <= x <= x1 and y0 <= y <= y1

    def _resolve_annotation_clip_box(
        self,
        annotation: PdfAnnotation,
        templates: dict[str, CorrectionTemplate],
    ) -> tuple[float, float, float, float] | None:
        if annotation.area_code:
            template = templates.get(annotation.area_code)
            if template is None or template.page_number != annotation.page_number:
                return None
            return template.box

        for template in templates.values():
            if template.page_number != annotation.page_number:
                continue
            if self._point_in_box(annotation.x, annotation.y, template.box):
                return template.box
        return None

    @staticmethod
    def _estimate_annotation_rect(annotation: PdfAnnotation, fontsize: int) -> fitz.Rect:
        fontsize_f = max(8.0, float(fontsize))
        lines = annotation.content.splitlines() or [annotation.content or " "]
        longest_line = max(lines, key=len)
        text_width = fitz.get_text_length(longest_line, fontname="helv", fontsize=fontsize_f)
        rotation_deg = int(MainWindow._normalize_rotation_deg(annotation.rotation_deg))

        width = max(24.0, text_width + (fontsize_f * CORRECTION_EXPORT_TEXT_WIDTH_PADDING_EM))
        center_x = annotation.x
        if annotation.annotation_type == "symbol":
            height = max(12.0, fontsize_f * CORRECTION_EXPORT_SYMBOL_HEIGHT_EM)
            center_y = annotation.y + (fontsize_f * CORRECTION_EXPORT_SYMBOL_Y_SHIFT_EM)
            if rotation_deg == 90:
                center_x += fontsize_f * CORRECTION_EXPORT_SYMBOL_ROT90_X_SHIFT_EM
            elif rotation_deg == 270:
                center_x -= fontsize_f * CORRECTION_EXPORT_SYMBOL_ROT90_X_SHIFT_EM
            elif rotation_deg == 180:
                center_y -= fontsize_f * CORRECTION_EXPORT_SYMBOL_ROT180_Y_CORRECTION_EM
        else:
            line_count = max(1, len(lines))
            height = max(12.0, fontsize_f * CORRECTION_EXPORT_TEXT_HEIGHT_EM * line_count)
            center_y = annotation.y + (fontsize_f * CORRECTION_EXPORT_TEXT_Y_SHIFT_EM)
            if rotation_deg == 90:
                center_x += width * CORRECTION_EXPORT_TEXT_ROT_X_SHIFT_FACTOR
                center_y -= fontsize_f * CORRECTION_EXPORT_TEXT_ROT90_Y_CORRECTION_EM
            elif rotation_deg == 270:
                center_x -= width * CORRECTION_EXPORT_TEXT_ROT_X_SHIFT_FACTOR
                center_y -= fontsize_f * CORRECTION_EXPORT_TEXT_ROT90_Y_CORRECTION_EM
            elif rotation_deg == 180:
                center_y -= fontsize_f * CORRECTION_EXPORT_TEXT_ROT180_Y_CORRECTION_EM
        return fitz.Rect(
            center_x - (width / 2.0),
            center_y - (height / 2.0),
            center_x + (width / 2.0),
            center_y + (height / 2.0),
        )

    def _delete_selected_correction_annotation(self) -> bool:
        annotation = self._selected_correction_annotation()
        if annotation is None:
            return False
        removed = self._delete_annotation_or_group(annotation)
        if removed <= 0:
            return False
        self._render_correction_annotations()
        if annotation.sync_group_id:
            self._status_var.set(f"Sync-Gruppe geloescht ({removed} Markierungen)")
        else:
            self._status_var.set("Markierung geloescht")
        return True

    def _resize_selected_correction_annotation(self, delta: float) -> None:
        annotation = self._selected_correction_annotation()
        if annotation is None:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Markierung auswaehlen.")
            return
        next_size = max(8.0, min(96.0, float(annotation.font_size) + delta))
        for item in self._sync_group_members(annotation, include_detached=True):
            item.font_size = next_size
        self._render_correction_annotations()
        self._status_var.set(f"Markierungsgroesse: {next_size:.0f}pt")

    def _rotate_selected_correction_annotation(self, delta_deg: float) -> None:
        annotation = self._selected_correction_annotation()
        if annotation is None:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Markierung auswaehlen.")
            return
        current = self._normalize_rotation_deg(annotation.rotation_deg)
        next_rotation = self._normalize_rotation_deg(current + delta_deg)
        for item in self._sync_group_members(annotation, include_detached=True):
            item.rotation_deg = next_rotation
        self._render_correction_annotations()
        self._status_var.set(f"Markierungswinkel: {next_rotation:.0f}°")

    @staticmethod
    def _normalize_rotation_deg(raw_deg: float) -> float:
        # PDF freetext rotation is reliable for 90-degree steps.
        snapped = int(round(float(raw_deg) / 90.0)) * 90
        return float(snapped % 360)

    def _render_correction_annotations(self) -> None:
        if self._correction_canvas is None:
            return
        self._correction_canvas.delete("correction_annotation")
        self._correction_annotation_items.clear()
        annotations = self._current_correction_annotations()
        visible_ids = {item.annotation_id for item in annotations}
        if self._correction_selected_annotation_id not in visible_ids:
            self._correction_selected_annotation_id = None
        if not annotations:
            self._refresh_correction_sync_info()
            return

        for annotation in annotations:
            canvas_pos = self._pdf_to_canvas_coords(annotation.x, annotation.y)
            if canvas_pos is None:
                continue
            canvas_x, canvas_y = canvas_pos
            font_size = max(8, int(round(float(annotation.font_size) * self._correction_scale)))
            item_id = self._correction_canvas.create_text(
                canvas_x,
                canvas_y,
                text=annotation.content,
                fill=annotation.color_hex,
                font=("Segoe UI", font_size, "bold"),
                anchor=ui.CENTER,
                angle=self._normalize_rotation_deg(annotation.rotation_deg),
                tags=("correction_annotation", f"annotation:{annotation.annotation_id}"),
            )
            self._correction_annotation_items[annotation.annotation_id] = item_id
            if annotation.annotation_id == self._correction_selected_annotation_id:
                bbox = self._correction_canvas.bbox(item_id)
                if bbox is not None:
                    self._correction_canvas.create_rectangle(
                        bbox[0] - 4,
                        bbox[1] - 2,
                        bbox[2] + 4,
                        bbox[3] + 2,
                        outline="#f4a261",
                        width=2,
                        tags=("correction_annotation",),
                    )
                    self._correction_canvas.tag_raise(item_id)
                self._refresh_correction_sync_info()

    def _insert_current_comment_into_preview_center(self) -> None:
        if not self._correction_mode_active:
            return
        comment = self._correction_comment_var.get().strip()
        if not comment:
            messagebox.showinfo("Hinweis", "Bitte zuerst einen Kommentar eintragen.")
            return
        self._save_current_correction_comment()
        if self._correction_canvas is None:
            return
        center_x = float(self._correction_canvas.canvasx(self._correction_canvas.winfo_width() / 2.0))
        center_y = float(self._correction_canvas.canvasy(self._correction_canvas.winfo_height() / 2.0))
        created = self._place_annotation_from_canvas(
            canvas_x=center_x,
            canvas_y=center_y,
            annotation_type="text",
            content=comment,
        )
        if created:
            self._status_var.set("Kommentar in Vorschau-Mitte eingefuegt")

    def _place_annotation_from_canvas(
        self,
        *,
        canvas_x: float,
        canvas_y: float,
        annotation_type: str,
        content: str,
    ) -> bool:
        if self._current_exam is None:
            return False
        student = self._current_correction_student()
        area_code = self._correction_area_var.get().strip().upper()
        template = self._correction_templates.get(area_code)
        if student is None or template is None:
            return False
        pdf_pos = self._canvas_to_pdf_coords(canvas_x, canvas_y)
        if pdf_pos is None:
            return False

        task_code, _max_points = self._selected_correction_task()
        default_font_size = self._default_annotation_font_size
        annotation = PdfAnnotation(
            annotation_id=f"ann-{uuid4().hex[:12]}",
            student_pdf=student.pdf_filename,
            page_number=template.page_number,
            annotation_type=annotation_type,
            content=content,
            color_hex=self._current_marker_color_hex(),
            x=pdf_pos[0],
            y=pdf_pos[1],
            task_code=task_code or "",
            area_code=area_code,
            font_size=default_font_size,
            rotation_deg=0.0,
            sync_group_id="",
            position_detached=False,
        )
        self._upsert_annotation(annotation)
        self._correction_selected_annotation_id = annotation.annotation_id
        self._render_correction_annotations()
        return True

    def _on_correction_canvas_press(self, event: ui.Event[ui.Misc]):
        if not self._correction_mode_active:
            return None
        self._correction_drag_alt_override = False
        self._correction_canvas.focus_set()
        canvas_x = float(self._correction_canvas.canvasx(event.x))
        canvas_y = float(self._correction_canvas.canvasy(event.y))

        item_under_cursor = self._correction_canvas.find_withtag("current")
        if item_under_cursor:
            item_id = item_under_cursor[0]
            annotation_id = next(
                (key for key, value in self._correction_annotation_items.items() if value == item_id),
                None,
            )
            if annotation_id is not None:
                self._correction_selected_annotation_id = annotation_id
                annotation = self._annotation_by_id(annotation_id)
                pdf_pos = self._canvas_to_pdf_coords(canvas_x, canvas_y)
                if annotation is not None and pdf_pos is not None:
                    self._correction_drag_annotation_id = annotation_id
                    self._correction_drag_offset_pdf = (annotation.x - pdf_pos[0], annotation.y - pdf_pos[1])
                    self._correction_drag_alt_override = self._event_has_alt_modifier(event)
                self._render_correction_annotations()
                return "break"

        lookup = self._marker_tool_lookup(self._correction_marker_tool_key)
        if lookup is None:
            return "break"
        glyph, label = lookup
        if self._place_annotation_from_canvas(
            canvas_x=canvas_x,
            canvas_y=canvas_y,
            annotation_type="symbol",
            content=glyph,
        ):
            self._status_var.set(f"Markierung gesetzt: {label}")
        return "break"

    def _on_correction_canvas_drag(self, event: ui.Event[ui.Misc]):
        if not self._correction_mode_active or self._current_exam is None:
            return None
        if self._correction_drag_annotation_id is None or self._correction_drag_offset_pdf is None:
            return None
        annotation = self._annotation_by_id(self._correction_drag_annotation_id)
        if annotation is None:
            return "break"

        canvas_x = float(self._correction_canvas.canvasx(event.x))
        canvas_y = float(self._correction_canvas.canvasy(event.y))
        pdf_pos = self._canvas_to_pdf_coords(canvas_x, canvas_y)
        if pdf_pos is None:
            return "break"
        target_x = pdf_pos[0] + self._correction_drag_offset_pdf[0]
        target_y = pdf_pos[1] + self._correction_drag_offset_pdf[1]
        dx = target_x - annotation.x
        dy = target_y - annotation.y
        if abs(dx) < 1e-9 and abs(dy) < 1e-9:
            return "break"

        if annotation.sync_group_id and not self._correction_drag_alt_override and not annotation.position_detached:
            for item in self._sync_group_members(annotation, include_detached=False):
                item.x += dx
                item.y += dy
        else:
            annotation.x = target_x
            annotation.y = target_y
            if annotation.sync_group_id and self._correction_drag_alt_override:
                annotation.position_detached = True
        self._render_correction_annotations()
        return "break"

    def _on_correction_canvas_release(self, _event: ui.Event[ui.Misc]):
        if not self._correction_mode_active:
            return None
        self._correction_drag_annotation_id = None
        self._correction_drag_offset_pdf = None
        self._correction_drag_alt_override = False
        return "break"

    def _save_correction_annotations_to_pdfs(self) -> None:
        if self._current_exam is None or self._controller is None:
            return

        self._save_current_correction_comment()

        grouped: dict[str, list[PdfAnnotation]] = {}
        for annotation in self._current_exam.pdf_annotations:
            grouped.setdefault(annotation.student_pdf, []).append(annotation)

        templates = self._build_correction_templates(self._current_exam)

        if not grouped:
            messagebox.showinfo("Hinweis", "Keine Markierungen zum Speichern vorhanden.")
            return

        failures: list[str] = []
        skipped_annotations: list[str] = []
        for student_pdf, annotations in grouped.items():
            pdf_path = Path(self._current_exam.folder_path) / student_pdf
            if not pdf_path.exists():
                failures.append(f"Datei fehlt: {student_pdf}")
                continue

            exportable_annotations: list[PdfAnnotation] = []
            for annotation in annotations:
                clip_box = self._resolve_annotation_clip_box(annotation, templates)
                if clip_box is None or not self._point_in_box(annotation.x, annotation.y, clip_box):
                    skipped_annotations.append(
                        f"{student_pdf} S{annotation.page_number}: {annotation.content} ({annotation.annotation_id})"
                    )
                    continue
                exportable_annotations.append(annotation)

            cached_document = self._doc_cache.pop(student_pdf, None)
            if cached_document is not None:
                try:
                    cached_document.close()
                except Exception:
                    pass

            temp_path = pdf_path.with_name(f"{pdf_path.stem}.korrektor.tmp.pdf")
            document: fitz.Document | None = None
            try:
                document = fitz.open(pdf_path)
                for page_index in range(document.page_count):
                    page = document.load_page(page_index)
                    existing = list(page.annots() or [])
                    for existing_annot in existing:
                        info = existing_annot.info or {}
                        subject = str(info.get("subject", ""))
                        if subject.startswith("KORREKTOR_MARKER:"):
                            page.delete_annot(existing_annot)

                for annotation in exportable_annotations:
                    if annotation.page_number < 1 or annotation.page_number > document.page_count:
                        continue
                    page = document.load_page(annotation.page_number - 1)
                    fontsize = max(8, int(round(float(annotation.font_size))))
                    rect = self._estimate_annotation_rect(annotation, fontsize)
                    annot = page.add_freetext_annot(
                        rect,
                        annotation.content,
                        fontsize=fontsize,
                        fontname="helv",
                        text_color=self._hex_to_rgb_fraction(annotation.color_hex),
                        rotate=int(self._normalize_rotation_deg(annotation.rotation_deg)),
                        align=1,
                    )
                    annot.set_info(
                        title="Korrektor",
                        subject=f"KORREKTOR_MARKER:{annotation.annotation_id}",
                        content=annotation.content,
                    )
                    annot.update()

                document.save(temp_path, garbage=4, deflate=True)
                document.close()
                document = None
                os.replace(temp_path, pdf_path)
            except Exception as exc:
                failures.append(f"{student_pdf}: {exc}")
                try:
                    if temp_path.exists():
                        temp_path.unlink()
                except Exception:
                    pass
            finally:
                if document is not None:
                    try:
                        document.close()
                    except Exception:
                        pass

        if failures:
            messagebox.showerror("PDF-Speichern fehlgeschlagen", "\n".join(failures))
            return

        self._current_exam = self._controller.save_exam_immediate(exam=self._current_exam)
        self._apply_detail_labels(self._current_exam)
        self._render_correction_preview()
        if skipped_annotations:
            preview = "\n".join(skipped_annotations[:8])
            remaining = len(skipped_annotations) - 8
            suffix = f"\n... und {remaining} weitere" if remaining > 0 else ""
            messagebox.showwarning(
                "Exporthinweis",
                "Markierungen ausserhalb des aktiven Vorschau-Bereichs wurden beim PDF-Ueberschreiben ignoriert:\n"
                + preview
                + suffix,
            )
        self._status_var.set("Original-PDF mit Markierungen ueberschrieben")

    def _render_correction_preview(self) -> None:
        if self._current_exam is None:
            return
        student = self._current_correction_student()
        area_code = self._correction_area_var.get().strip().upper()
        template = self._correction_templates.get(area_code)
        if student is None or template is None:
            self._correction_canvas.delete("all")
            self._correction_clip_box = None
            self._correction_info_var.set("Korrektur: keine Daten")
            return

        pdf_path = Path(self._current_exam.folder_path) / student.pdf_filename
        if not pdf_path.exists():
            self._correction_canvas.delete("all")
            self._correction_clip_box = None
            self._correction_info_var.set(f"Datei fehlt: {student.pdf_filename}")
            return

        document = self._doc_cache.get(student.pdf_filename)
        if document is None:
            document = fitz.open(pdf_path)
            self._doc_cache[student.pdf_filename] = document

        try:
            page = document.load_page(template.page_number - 1)
            page_rect = page.rect
            clip = fitz.Rect(*template.box)
            clip = clip.intersect(page_rect)
            if clip.is_empty:
                clip = page_rect
            target_width = 560.0
            scale = (target_width / max(clip.width, 1.0)) * (self._correction_zoom_percent / 100.0)
            try:
                pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=clip, alpha=False, annots=False)
            except TypeError:
                pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=clip, alpha=False)
            self._correction_clip_box = (float(clip.x0), float(clip.y0), float(clip.x1), float(clip.y1))
            self._correction_scale = scale
            self._correction_photo = ui.PhotoImage(data=pix.tobytes("ppm"), format="ppm")
            self._correction_canvas.delete("all")
            self._correction_canvas.create_image(0, 0, anchor=ui.NW, image=self._correction_photo)
            self._correction_canvas.configure(scrollregion=(0, 0, pix.width, pix.height))
            self._render_correction_annotations()
            self._correction_info_var.set(
                f"Bereich {area_code} | {student.display_name} ({self._correction_cursor + 1}/{len(self._correction_student_indices)}) | Seite {template.page_number}"
            )
        except Exception as exc:
            self._correction_canvas.delete("all")
            self._correction_clip_box = None
            self._correction_info_var.set(f"Fehler beim Korrektur-Rendering: {exc}")

    def _change_correction_student(self, delta: int) -> None:
        if not self._correction_mode_active or not self._correction_student_indices:
            return
        self._save_current_correction_score()
        self._save_current_correction_comment()
        self._correction_cursor = (self._correction_cursor + delta) % len(self._correction_student_indices)
        self._student_cursor = self._correction_student_indices[self._correction_cursor]
        self._correction_selected_annotation_id = None
        self._refresh_active_student_label()
        self._refresh_correction_task_meta(load_saved_points=True)
        self._render_correction_preview()
        self._refresh_correction_completion_controls()
        self._focus_first_input_field()

    def _save_current_correction_score(self) -> bool:
        if not self._correction_mode_active or self._controller is None or self._current_exam is None:
            return False
        if self._is_current_person_area_finished():
            return False
        student = self._current_correction_student()
        if student is None:
            return False
        task_code, max_points = self._selected_correction_task()
        if task_code is None:
            return False
        saved = self._controller.save_score_immediate(
            exam=self._current_exam,
            student_id=student.student_id,
            task_code=task_code,
            points_text=self._correction_points_var.get(),
            max_points_text=f"{max_points:g}",
        )
        self._refresh_correction_completion_controls()
        return saved

    def _save_current_correction_comment(self) -> bool:
        if not self._correction_mode_active or self._controller is None or self._current_exam is None:
            return False
        student = self._current_correction_student()
        if student is None:
            return False
        task_code, _max_points = self._selected_correction_task()
        if task_code is None:
            return False
        updated = self._controller.set_task_comment_immediate(
            exam=self._current_exam,
            student_id=student.student_id,
            task_code=task_code,
            comment_text=self._correction_comment_var.get(),
        )
        if updated is None:
            return False
        self._current_exam = updated
        self._apply_detail_labels(updated)
        return True

    def _on_correction_area_changed(self, _event: ui.Event[ui.Misc]) -> None:
        if not self._correction_mode_active:
            return
        self._save_current_correction_score()
        self._save_current_correction_comment()
        self._correction_selected_annotation_id = None
        self._refresh_correction_task_choices(load_saved_points=True)
        self._refresh_correction_completion_controls()
        self._focus_first_input_field()

    def _on_correction_task_changed(self, _event: ui.Event[ui.Misc]) -> None:
        if not self._correction_mode_active:
            return
        self._save_current_correction_score()
        self._save_current_correction_comment()
        self._correction_selected_annotation_id = None
        self._refresh_correction_task_meta(load_saved_points=True)
        self._refresh_correction_completion_controls()
        self._focus_first_input_field()

    def _on_correction_points_focus_out(self, _event: ui.Event[ui.Misc]) -> None:
        self._save_current_correction_score()

    def _on_correction_points_commit(self, _event: ui.Event[ui.Misc]) -> None:
        self._save_current_correction_score()
        self.root.focus_set()

    def _on_correction_points_escape(self, _event: ui.Event[ui.Misc]) -> None:
        self._save_current_correction_score()
        self.root.focus_set()

    def _on_correction_comment_focus_out(self, _event: ui.Event[ui.Misc]) -> None:
        self._save_current_correction_comment()

    def _on_correction_comment_commit(self, _event: ui.Event[ui.Misc]) -> None:
        self._save_current_correction_comment()
        self.root.focus_set()

    def _on_correction_comment_escape(self, _event: ui.Event[ui.Misc]) -> None:
        self._save_current_correction_comment()
        self.root.focus_set()

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
            popup = ui.Toplevel(self.root)
            popup.title(f"Extraseiten: {student.display_name}")
            popup.geometry("760x860")
            popup.transient(self.root)
            self._register_popup_window(popup)

            header = widgets.Frame(popup, padding=10)
            header.pack(fill=ui.X)
            self._extra_popup_info_var = ui.StringVar(value="")
            widgets.Label(header, textvariable=self._extra_popup_info_var, style="Muted.TLabel").pack(side=ui.LEFT)

            canvas_bg, canvas_border = self._canvas_theme_tokens()
            self._extra_popup_canvas = ui.Canvas(
                popup,
                bg=canvas_bg,
                highlightthickness=1,
                highlightbackground=canvas_border,
            )
            self._extra_popup_canvas.pack(fill=ui.BOTH, expand=True, padx=10, pady=(0, 10))

            nav = widgets.Frame(popup, padding=(10, 0, 10, 10))
            nav.pack(fill=ui.X)
            popup_prev_button = widgets.Button(
                nav,
                text="◀",
                style="SecondaryAction.TButton",
                command=lambda: self._change_extra_popup_page(-1),
            )
            popup_prev_button.pack(side=ui.LEFT)
            self._attach_hover_help(popup_prev_button, label="Vorherige Extraseite", shortcut="Links")

            popup_next_button = widgets.Button(
                nav,
                text="▶",
                style="SecondaryAction.TButton",
                command=lambda: self._change_extra_popup_page(1),
            )
            popup_next_button.pack(side=ui.LEFT, padx=(8, 0))
            self._attach_hover_help(popup_next_button, label="Naechste Extraseite", shortcut="Rechts")

            popup_close_button = widgets.Button(
                nav,
                text="Schließen",
                style="SecondaryAction.TButton",
                command=self._close_extra_popup,
            )
            popup_close_button.pack(side=ui.RIGHT)
            self._attach_hover_help(popup_close_button, label="Extraseiten-Popup schliessen", shortcut="Esc")

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
            self._popup_photo = ui.PhotoImage(data=pix.tobytes("ppm"), format="ppm")
            self._extra_popup_canvas.configure(width=pix.width, height=pix.height)
            self._extra_popup_canvas.delete("all")
            self._extra_popup_canvas.create_image(0, 0, anchor=ui.NW, image=self._popup_photo)
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
        if self._correction_mode_active:
            if str(self._correction_points_entry.cget("state")) == "disabled":
                if self._correction_finished_check is not None:
                    self._correction_finished_check.focus_set()
                return
            self._correction_points_entry.focus_set()
            self._correction_points_entry.selection_range(0, ui.END)
            return
        self._task_code_entry.focus_set()
        self._task_code_entry.selection_range(0, ui.END)

    def start_reading_mode_for_current_exam(self) -> None:
        self._start_reading_mode()

    def _show_detail_mode(self) -> None:
        if self._current_exam is None:
            return
        self._show_view("detail")
        self._in_detail_mode = True
        self._set_detail_submode("reading")

    def _show_view(self, view_name: str) -> None:
        frames = {
            "overview": self._overview_view,
            "detail": self._detail_view,
            "reading": self._reading_view,
            "correction": self._correction_view,
        }
        target = frames.get(view_name)
        if target is None:
            return

        for frame in frames.values():
            frame.pack_forget()
        target.pack(fill=ui.BOTH, expand=True)
        self._active_view = view_name
        self._refresh_active_student_label()

    def _leave_reading_view(self) -> None:
        self._reading_active = False
        self._extra_mode_active = False
        self._superpage_var.set(False)
        self._extra_sequence = []
        self._reading_mode_title_var.set("Einlesen")
        self._clear_pending_redraw()
        self._close_extra_popup()
        self._reading_info_var.set("Einlesemodus: bereit")
        self._status_var.set("Einlesemodus verlassen")
        self._show_detail_mode()

    def _return_to_overview(self) -> None:
        self._current_exam = None
        self._detail_exam_file = None
        self._reading_active = False
        self._extra_mode_active = False
        self._correction_mode_active = False
        self._superpage_var.set(False)
        self._selected_region_id = None
        self._selected_region_kind = None
        self._clear_pending_redraw()
        self._draft_regions.clear()
        self._detail_name.set("-")
        self._detail_pages.set("Standardseiten: -")
        self._detail_students.set("Schüler:innen: -")
        self._detail_regions.set("Fertig korrigiert -")
        self._detail_status.set("Status: -")
        self._active_student.set("Aktive Person: -")
        self._correction_zoom_percent = 100
        self._refresh_correction_zoom_label()
        self._reading_mode_title_var.set("Einlesen")
        self._reading_info_var.set("Einlesemodus: nicht aktiv")
        if hasattr(self, "_correction_info_var"):
            self._correction_info_var.set("Korrektur: nicht aktiv")
        if hasattr(self, "_correction_points_var"):
            self._correction_points_var.set("")
        if hasattr(self, "_correction_comment_var"):
            self._correction_comment_var.set("")
        if hasattr(self, "_correction_finished_var"):
            self._correction_finished_var.set(False)
        self._close_extra_popup()
        self._reading_canvas.delete("all")
        if hasattr(self, "_correction_canvas"):
            self._correction_canvas.delete("all")
        self._active_region_var.set("-")
        self._quick_tasks_var.set("")
        self._form_tasks_text.delete("1.0", ui.END)
        if hasattr(self, "_extra_area_codes_var"):
            self._extra_area_codes_var.set("")
        self._refresh_region_tree()
        self._show_view("overview")
        self._in_detail_mode = False
        self._status_var.set("Zur Übersicht zurueckgekehrt")

    def _show_correction_controls(self) -> None:
        if self._correction_controls_frame is None:
            return
        self._correction_controls_frame.pack(fill=ui.BOTH, expand=True, pady=(10, 0))

    def _hide_correction_controls(self) -> None:
        if self._correction_controls_frame is None:
            return
        self._correction_controls_frame.pack_forget()

    def _set_detail_submode(self, mode: str) -> None:
        self._detail_submode = mode

        if mode == "correction":
            self._show_view("correction")
            return
        self._hide_correction_controls()

        if mode == "extra":
            self._reading_mode_title_var.set("Extraseiten")
            self._reading_toolbar.pack_forget()
            self._mode_row.pack_forget()
            self._regions_editor.pack(fill=ui.BOTH, pady=(10, 0))
            if self._extra_overview_frame is not None:
                self._extra_overview_frame.pack_forget()
                self._extra_overview_frame.pack(fill=ui.X, pady=(0, 6), before=self._regions_tree.master)
            self._task_input_container.pack_forget()
            self._extra_area_container.pack(fill=ui.X, pady=(4, 0))
            self._extra_toolbar.pack(fill=ui.X, pady=(6, 0))
            return

        self._reading_mode_title_var.set("Einlesen")
        self._extra_toolbar.pack_forget()
        self._reading_toolbar.pack(fill=ui.X)
        self._superpage_toggle.pack_forget()
        self._superpage_toggle.pack(side=ui.RIGHT)
        self._mode_row.pack(fill=ui.X, pady=(8, 0))
        self._regions_editor.pack(fill=ui.BOTH, pady=(10, 0))
        if self._extra_overview_frame is not None:
            self._extra_overview_frame.pack_forget()
        self._extra_area_container.pack_forget()
        self._task_input_container.pack(fill=ui.X)

    def _refresh_task_input_mode(self) -> None:
        mode = self._assignment_mode_var.get()
        if mode == "form":
            self._quick_tasks_entry.pack_forget()
            self._form_tasks_text.pack_forget()
            self._form_tasks_text.pack(fill=ui.X, pady=(4, 0))
            self._task_input_example_var.set("Beispiel (Formular):\n5B:2\n5C:1")
        else:
            self._form_tasks_text.pack_forget()
            self._quick_tasks_entry.pack_forget()
            self._quick_tasks_entry.pack(fill=ui.X)
            self._task_input_example_var.set("Beispiel (Schnell): 5B:2;5C:1")

        self._task_input_example_label.pack_forget()
        self._task_input_example_label.pack(fill=ui.X, pady=(4, 0))

    def _read_task_specs_from_editor(self) -> list[tuple[str, float]] | None:
        if self._assignment_mode_var.get() == "form":
            raw = self._form_tasks_text.get("1.0", ui.END).strip()
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

    @staticmethod
    def _format_area_label(area_codes: list[str]) -> str:
        labels = [code.strip().upper() for code in area_codes if code.strip()]
        return ", ".join(labels) if labels else "-"

    @staticmethod
    def _format_task_specs_text(task_specs: list[tuple[str, float]]) -> str:
        if not task_specs:
            return "-"
        return ", ".join(f"{code}({max_points:g})" for code, max_points in task_specs)

    def _build_standard_area_task_map(self) -> dict[str, list[tuple[str, float]]]:
        mapping: dict[str, list[tuple[str, float]]] = {}
        if self._current_exam is None:
            return mapping

        for region in self._current_exam.regions:
            task_specs = [(task.code, task.max_points) for task in region.tasks]
            for code in region.assigned_area_codes:
                normalized = code.strip().upper()
                if not normalized or normalized in mapping:
                    continue
                mapping[normalized] = task_specs
        return mapping

    def _format_tasks_for_areas(self, area_codes: list[str]) -> str:
        normalized_area_codes = [code.strip().upper() for code in area_codes if code.strip()]
        if not normalized_area_codes:
            return "-"

        area_tasks = self._build_standard_area_task_map()
        parts: list[str] = []
        for area_code in normalized_area_codes:
            task_text = self._format_task_specs_text(area_tasks.get(area_code, []))
            parts.append(f"{area_code}: {task_text}")
        return " | ".join(parts)

    def _refresh_extra_overview(self) -> None:
        if not self._extra_mode_active:
            self._extra_overview_var.set("")
            return

        area_tasks = self._build_standard_area_task_map()
        if not area_tasks:
            self._extra_overview_var.set("Noch keine Standardbereiche vorhanden.")
            return

        lines = [
            f"{area_code}: {self._format_task_specs_text(task_specs)}"
            for area_code, task_specs in sorted(area_tasks.items())
        ]
        self._extra_overview_var.set("\n".join(lines))

    def _refresh_region_tree(self) -> None:
        self._region_tree_rows.clear()
        for item in self._regions_tree.get_children():
            self._regions_tree.delete(item)

        if self._current_exam is None:
            self._extra_overview_var.set("")
            return

        self._refresh_extra_overview()

        if self._extra_mode_active and self._extra_sequence:
            student_index, page_number = self._extra_sequence[self._extra_cursor]
            student_pdf = self._current_exam.students[student_index].pdf_filename
            for assignment in self._current_exam.extra_page_assignments:
                if assignment.student_pdf != student_pdf or assignment.page_number != page_number:
                    continue
                area = self._format_area_label(assignment.assigned_area_codes)
                row_id = self._regions_tree.insert(
                    "",
                    ui.END,
                    values=(area, self._format_tasks_for_areas(assignment.assigned_area_codes), assignment.page_number),
                )
                self._region_tree_rows[row_id] = ("extra", assignment.assignment_id)
        else:
            for region in self._current_exam.regions:
                area = self._format_area_label(region.assigned_area_codes)
                tasks_text = self._format_task_specs_text([(task.code, task.max_points) for task in region.tasks])
                row_id = self._regions_tree.insert(
                    "",
                    ui.END,
                    values=(area, tasks_text, region.page_number),
                )
                self._region_tree_rows[row_id] = ("region", region.region_id)

        for draft in self._draft_regions.values():
            if self._extra_mode_active and self._extra_sequence:
                student_index, page_number = self._extra_sequence[self._extra_cursor]
                student_pdf = self._current_exam.students[student_index].pdf_filename
                if draft.student_pdf != student_pdf or draft.page_number != page_number:
                    continue
            elif draft.student_pdf:
                continue
            area = self._format_area_label(draft.area_codes)
            tasks_text = (
                self._format_tasks_for_areas(draft.area_codes)
                if self._extra_mode_active
                else self._format_task_specs_text(draft.task_specs)
            )
            row_id = self._regions_tree.insert(
                "",
                ui.END,
                values=(f"{area}*", tasks_text, draft.page_number),
            )
            self._region_tree_rows[row_id] = ("draft", draft.draft_id)

    def _select_region_by_id(self, region_id: str) -> None:
        for row_id, candidate in self._region_tree_rows.items():
            if candidate[1] == region_id:
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
            self._selected_region_kind = None
            self._active_region_var.set("-")
            return

        row_value = self._region_tree_rows.get(selection[0])
        if row_value is None:
            return
        kind, region_id = row_value
        self._selected_region_kind = kind

        if kind == "draft":
            draft = self._draft_regions.get(region_id)
            if draft is None:
                return
            self._selected_region_id = draft.draft_id
            area = draft.area_codes[0] if draft.area_codes else "-"
            self._active_region_var.set(f"{area} (Draft)")
            if self._extra_mode_active:
                self._extra_area_codes_var.set(",".join(code.strip().upper() for code in draft.area_codes if code.strip()))
                self._rerender_active_page()
                return
            quick_text = ";".join(f"{code}:{points:g}" for code, points in draft.task_specs)
            form_text = "\n".join(f"{code}:{points:g}" for code, points in draft.task_specs)
            self._quick_tasks_var.set(quick_text)
            self._form_tasks_text.delete("1.0", ui.END)
            self._form_tasks_text.insert("1.0", form_text)
            self._rerender_active_page()
            return

        if kind == "extra":
            assignment = next(
                (item for item in self._current_exam.extra_page_assignments if item.assignment_id == region_id),
                None,
            )
            if assignment is None:
                return
            self._selected_region_id = assignment.assignment_id
            area = assignment.assigned_area_codes[0] if assignment.assigned_area_codes else "-"
            self._active_region_var.set(area)
            self._extra_area_codes_var.set(",".join(code.strip().upper() for code in assignment.assigned_area_codes if code.strip()))
            self._rerender_active_page()
            return

        region = next((item for item in self._current_exam.regions if item.region_id == region_id), None)
        if region is None:
            return

        self._selected_region_id = region_id
        area = region.assigned_area_codes[0] if region.assigned_area_codes else "-"
        self._active_region_var.set(area)
        if self._extra_mode_active:
            self._extra_area_codes_var.set(",".join(code.strip().upper() for code in region.assigned_area_codes if code.strip()))
            self._rerender_active_page()
            return

        quick_text = ";".join(f"{task.code}:{task.max_points:g}" for task in region.tasks)
        form_text = "\n".join(f"{task.code}:{task.max_points:g}" for task in region.tasks)
        self._quick_tasks_var.set(quick_text)
        self._form_tasks_text.delete("1.0", ui.END)
        self._form_tasks_text.insert("1.0", form_text)
        self._rerender_active_page()

    def _save_selected_region(self) -> None:
        if self._current_exam is None or self._selected_region_id is None or self._controller is None:
            return

        if self._extra_mode_active:
            self._save_selected_extra_region()
            return

        task_specs = self._read_task_specs_from_editor()
        if task_specs is None:
            return

        region = next((item for item in self._current_exam.regions if item.region_id == self._selected_region_id), None)
        if region is not None:
            updated = self._controller.upsert_region_immediate(
                exam=self._current_exam,
                student_pdf="",
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
            self._rerender_active_page()
            return

        draft = self._draft_regions.get(self._selected_region_id)
        if draft is None:
            return

        if not task_specs:
            messagebox.showerror("Ungültige Eingabe", "Bitte mindestens eine Aufgabe mit Code und Punkten angeben.")
            return

        before_ids = {region.region_id for region in self._current_exam.regions}

        updated = self._controller.upsert_region_immediate(
            exam=self._current_exam,
            student_pdf="",
            page_number=draft.page_number,
            box=draft.box,
            task_specs=task_specs,
            area_codes=draft.area_codes,
        )
        if updated is None:
            return
        persisted_id = next(
            (
                region.region_id
                for region in reversed(updated.regions)
                if region.region_id not in before_ids
            ),
            None,
        )

        del self._draft_regions[draft.draft_id]
        self._current_exam = updated
        self._refresh_region_tree()
        if persisted_id:
            self._select_region_by_id(persisted_id)
        self._apply_detail_labels(updated)
        self._rerender_active_page()

    def _save_selected_extra_region(self) -> None:
        if self._current_exam is None or self._selected_region_id is None or self._controller is None:
            return

        area_codes = [code.strip().upper() for code in self._extra_area_codes_var.get().split(",") if code.strip()]
        if not area_codes:
            messagebox.showerror("Ungültige Eingabe", "Bitte mindestens einen bestehenden Bereich angeben, z. B. A.")
            return

        draft = self._draft_regions.get(self._selected_region_id)
        if draft is not None:
            before_ids = {assignment.assignment_id for assignment in self._current_exam.extra_page_assignments}
            updated = self._controller.assign_extra_page_immediate(
                exam=self._current_exam,
                student_pdf=draft.student_pdf,
                page_number=draft.page_number,
                box=draft.box,
                area_codes=area_codes,
            )
            if updated is None:
                return
            persisted_id = next(
                (
                    assignment.assignment_id
                    for assignment in reversed(updated.extra_page_assignments)
                    if assignment.assignment_id not in before_ids
                ),
                None,
            )
            del self._draft_regions[draft.draft_id]
            self._current_exam = updated
            self._refresh_region_tree()
            if persisted_id:
                self._select_region_by_id(persisted_id)
            self._apply_detail_labels(updated)
            self._rerender_active_page()
            return

        assignment = next(
            (item for item in self._current_exam.extra_page_assignments if item.assignment_id == self._selected_region_id),
            None,
        )
        if assignment is None:
            return
        updated = self._controller.assign_extra_page_immediate(
            exam=self._current_exam,
            student_pdf=assignment.student_pdf,
            page_number=assignment.page_number,
            box=(assignment.box.x0, assignment.box.y0, assignment.box.x1, assignment.box.y1),
            area_codes=area_codes,
        )
        if updated is None:
            return
        self._current_exam = updated
        self._refresh_region_tree()
        self._select_region_by_id(assignment.assignment_id)
        self._apply_detail_labels(updated)
        self._rerender_active_page()

    def _delete_selected_region(self) -> None:
        if self._current_exam is None or self._selected_region_id is None:
            return

        if self._selected_region_id in self._draft_regions:
            del self._draft_regions[self._selected_region_id]
            self._selected_region_id = None
            self._selected_region_kind = None
            self._active_region_var.set("-")
            self._quick_tasks_var.set("")
            self._form_tasks_text.delete("1.0", ui.END)
            self._refresh_region_tree()
            self._rerender_active_page()
            return

        if self._controller is None:
            return

        if self._selected_region_kind == "extra":
            updated = self._controller.delete_extra_page_assignment_immediate(
                exam=self._current_exam,
                assignment_id=self._selected_region_id,
            )
        else:
            updated = self._controller.delete_region_immediate(exam=self._current_exam, region_id=self._selected_region_id)
        self._current_exam = updated

        self._selected_region_id = None
        self._selected_region_kind = None
        self._active_region_var.set("-")
        self._quick_tasks_var.set("")
        self._form_tasks_text.delete("1.0", ui.END)
        self._refresh_region_tree()
        self._apply_detail_labels(self._current_exam)
        self._rerender_active_page()

    def _on_delete_region_key(self, _event: ui.Event[ui.Misc]) -> None:
        if self._active_view == "correction" and self._correction_mode_active:
            self._delete_selected_correction_annotation()
            return
        self._delete_selected_region()



