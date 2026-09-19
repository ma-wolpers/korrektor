from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Iterable, Sequence
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
from app.adapters.gui.main_window_constants import (
    CORRECTION_ALT_MODIFIER_MASKS,
    CORRECTION_DEFAULT_COLOR_NAME,
    CORRECTION_DEFAULT_FONT_SIZE_PT,
    CORRECTION_EXPORT_SYMBOL_HEIGHT_EM,
    CORRECTION_EXPORT_SYMBOL_ROT90_X_SHIFT_EM,
    CORRECTION_EXPORT_SYMBOL_ROT180_Y_CORRECTION_EM,
    CORRECTION_EXPORT_SYMBOL_Y_SHIFT_EM,
    CORRECTION_EXPORT_TEXT_HEIGHT_EM,
    CORRECTION_EXPORT_TEXT_ROT90_Y_CORRECTION_EM,
    CORRECTION_EXPORT_TEXT_ROT180_Y_CORRECTION_EM,
    CORRECTION_EXPORT_TEXT_ROT_X_SHIFT_FACTOR,
    CORRECTION_EXPORT_TEXT_WIDTH_PADDING_EM,
    CORRECTION_EXPORT_TEXT_Y_SHIFT_EM,
    CORRECTION_MARKER_COLORS,
    CORRECTION_MARKER_TOOLS,
    CORRECTION_ZOOM_MAX_PERCENT,
    CORRECTION_ZOOM_MIN_PERCENT,
    SUPERSYMBOL_OPERATOR_LABELS,
)
from app.adapters.gui.main_window_correction_completion import MainWindowCorrectionCompletionMixin
from app.adapters.gui.main_window_dispatch import MainWindowDispatchMixin
from app.adapters.gui.main_window_overview import MainWindowOverviewMixin
from app.adapters.gui.main_window_view_state import MainWindowViewStateMixin
from app.adapters.gui.main_window_extra_pages import MainWindowExtraPagesMixin
from app.adapters.gui.main_window_naming import MainWindowNamingMixin
from app.adapters.gui.main_window_correction_core import MainWindowCorrectionCoreMixin
from app.adapters.gui.main_window_correction_markers import MainWindowCorrectionMarkersMixin
from app.adapters.gui.main_window_correction_markers_clipboard import MainWindowCorrectionMarkersClipboardMixin
from app.adapters.gui.main_window_correction_markers_export import MainWindowCorrectionMarkersExportMixin
from app.adapters.gui.main_window_menu import MainWindowMenuMixin
from app.adapters.gui.main_window_shortcuts import MainWindowShortcutsMixin
from app.adapters.gui.main_window_shortcuts_debug import MainWindowShortcutsDebugMixin
from app.adapters.gui.main_window_theme import MainWindowThemeMixin
from app.adapters.gui.main_window_correction_form import MainWindowCorrectionFormMixin
from app.adapters.gui.main_window_correction_zoom import MainWindowCorrectionZoomMixin
from app.adapters.gui.main_window_reading import MainWindowReadingMixin
from app.adapters.gui.main_window_reading_canvas import MainWindowReadingCanvasMixin
from app.adapters.gui.main_window_region_editor import MainWindowRegionEditorMixin
from app.adapters.gui.main_window_region_specs import MainWindowRegionSpecsMixin
from app.adapters.gui.main_window_supersymbol import MainWindowSupersymbolMixin
from app.adapters.gui.main_window_types import CorrectionTemplate, DraftRegion
from app.adapters.gui.view_models import ExamOverviewRow
from app.core.domain.annotation_sync import build_annotation_clones
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


class MainWindow(
    MainWindowSupersymbolMixin,
    MainWindowNamingMixin,
    MainWindowExtraPagesMixin,
    MainWindowCorrectionCompletionMixin,
    MainWindowRegionSpecsMixin,
    MainWindowRegionEditorMixin,
    MainWindowReadingCanvasMixin,
    MainWindowReadingMixin,
    MainWindowCorrectionZoomMixin,
    MainWindowCorrectionFormMixin,
    MainWindowCorrectionCoreMixin,
    MainWindowCorrectionMarkersExportMixin,
    MainWindowCorrectionMarkersClipboardMixin,
    MainWindowCorrectionMarkersMixin,
    MainWindowShortcutsDebugMixin,
    MainWindowShortcutsMixin,
    MainWindowMenuMixin,
    MainWindowThemeMixin,
    MainWindowDispatchMixin,
    MainWindowOverviewMixin,
    MainWindowViewStateMixin,
    BwBaseWindow,
):
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
        self._naming_mode_active = False
        self._naming_capture_active = False
        self._naming_cursor = 0
        self._pending_student_names: dict[str, str] = {}
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
        self._correction_label_to_region_id: dict[str, str] = {}
        self._correction_task_items: list[tuple[str, float]] = []
        self._correction_photo: ui.PhotoImage | None = None
        self._correction_zoom_percent = 100
        self._correction_comment_entry: widgets.Entry | None = None
        self._correction_marker_tool_key = "check"
        self._supersymbol_filter_active = False
        self._supersymbol_matched_student_ids: list[str] = []
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
        self._correction_finished_all_check: widgets.Checkbutton | None = None
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
        self._correction_finished_all_var = ui.BooleanVar(value=False)
        self._correction_finished_all_hint_var = ui.StringVar(value="")
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

    def _build_layout(self, frame=None) -> None:
        shell = widgets.Frame(frame if frame is not None else self, style="App.TFrame", padding=16)
        shell.pack(fill=ui.BOTH, expand=True)

        self._view_stack = widgets.Frame(shell, style="App.TFrame")
        self._view_stack.pack(fill=ui.BOTH, expand=True, pady=(0, 10))

        self._overview_view = widgets.Frame(self._view_stack, style="Surface.TFrame", padding=12)
        self._detail_view = widgets.Frame(self._view_stack, style="Surface.TFrame", padding=12)
        self._reading_view = widgets.Frame(self._view_stack, style="Surface.TFrame", padding=12)
        self._correction_view = widgets.Frame(self._view_stack, style="Surface.TFrame", padding=12)

        widgets.Label(self._overview_view, text="Übersicht", style="Title.TLabel").pack(anchor=ui.W)

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

        mode_naming_button = widgets.Button(
            detail_actions,
            text="Namen",
            style="SecondaryAction.TButton",
            command=self._start_naming_mode,
        )
        mode_naming_button.pack(side=ui.LEFT, padx=(8, 0))
        self._attach_hover_help(mode_naming_button, label="In den Namenmodus wechseln (PDFs umbenennen)", shortcut=None)

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

        self._finish_reading_button = widgets.Button(
            reading_nav,
            text="Einlesen abschliessen",
            style="PrimaryAction.TButton",
            command=self._finish_reading_mode,
        )
        self._finish_reading_button.pack(side=ui.RIGHT)
        self._attach_hover_help(self._finish_reading_button, label="Einlesemodus abschliessen", shortcut=None)

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

        self._naming_region_toolbar = widgets.Frame(self._reading_view, style="Surface.TFrame")
        self._naming_region_hint_var = ui.StringVar(value="")
        widgets.Label(
            self._naming_region_toolbar,
            textvariable=self._naming_region_hint_var,
            style="Muted.TLabel",
            justify=ui.LEFT,
        ).pack(side=ui.LEFT, fill=ui.X, expand=True)
        self._naming_enter_capture_button = widgets.Button(
            self._naming_region_toolbar,
            text="Namen erfassen ▶",
            style="PrimaryAction.TButton",
            command=self._enter_naming_capture,
        )
        self._naming_enter_capture_button.pack(side=ui.RIGHT)
        self._attach_hover_help(
            self._naming_enter_capture_button,
            label="Weiter zur Namenserfassung (Namensbereich muss zuvor gezogen sein)",
            shortcut=None,
        )

        self._naming_capture_panel = widgets.Frame(self._reading_view, style="Surface.TFrame")
        naming_capture_nav = widgets.Frame(self._naming_capture_panel, style="Surface.TFrame")
        naming_capture_nav.pack(fill=ui.X)
        back_to_naming_region_button = widgets.Button(
            naming_capture_nav,
            text="◀ Bereich anpassen",
            style="SecondaryAction.TButton",
            command=self._exit_naming_capture,
        )
        back_to_naming_region_button.pack(side=ui.LEFT)
        prev_naming_student_button = widgets.Button(
            naming_capture_nav,
            text="◀ Person",
            style="SecondaryAction.TButton",
            command=lambda: self._change_naming_student(-1),
        )
        prev_naming_student_button.pack(side=ui.LEFT, padx=(14, 0))
        self._attach_hover_help(prev_naming_student_button, label="Vorherige Person", shortcut="Links")
        next_naming_student_button = widgets.Button(
            naming_capture_nav,
            text="Person ▶",
            style="SecondaryAction.TButton",
            command=lambda: self._change_naming_student(1),
        )
        next_naming_student_button.pack(side=ui.LEFT, padx=(8, 0))
        self._attach_hover_help(next_naming_student_button, label="Naechste Person", shortcut="Rechts")

        self._naming_rename_all_button = widgets.Button(
            naming_capture_nav,
            text="Alle umbenennen",
            style="PrimaryAction.TButton",
            command=self._rename_all_students,
        )
        self._naming_rename_all_button.pack(side=ui.RIGHT)
        self._attach_hover_help(
            self._naming_rename_all_button,
            label="Erst aktiv, wenn fuer alle Schueler:innen ein Name erfasst wurde",
            shortcut=None,
        )

        naming_capture_form = widgets.Frame(self._naming_capture_panel, style="Surface.TFrame")
        naming_capture_form.pack(fill=ui.X, pady=(6, 0))
        widgets.Label(naming_capture_form, text="Name:", style="Muted.TLabel").pack(side=ui.LEFT)
        self._naming_name_var = ui.StringVar(value="")
        self._naming_entry = widgets.Entry(naming_capture_form, textvariable=self._naming_name_var)
        self._naming_entry.pack(side=ui.LEFT, fill=ui.X, expand=True, padx=(8, 0))
        self._naming_entry.bind("<FocusOut>", self._on_naming_fields_focus_out)
        self._naming_entry.bind("<Return>", self._on_naming_fields_commit)
        self._naming_entry.bind("<Escape>", self._on_naming_fields_escape)

        self._naming_progress_var = ui.StringVar(value="")
        widgets.Label(
            self._naming_capture_panel,
            textvariable=self._naming_progress_var,
            style="Muted.TLabel",
        ).pack(anchor=ui.W, pady=(4, 0))

        self._mode_row = widgets.Frame(self._reading_view, style="Surface.TFrame")
        self._mode_row.pack(fill=ui.X, pady=(8, 0))
        widgets.Label(self._mode_row, text="Zuordnung:", style="Muted.TLabel").pack(side=ui.LEFT)
        widgets.Radiobutton(self._mode_row, text="Schnell (Code:Punkte)", value="quick", variable=self._assignment_mode_var).pack(side=ui.LEFT, padx=(8, 0))
        widgets.Radiobutton(self._mode_row, text="Formular", value="form", variable=self._assignment_mode_var).pack(side=ui.LEFT, padx=(8, 0))
        self._assignment_mode_var.trace_add("write", lambda *_args: self._refresh_task_input_mode())

        self._reading_split = widgets.PanedWindow(self._reading_view, orient=ui.HORIZONTAL)
        self._reading_split.pack(fill=ui.BOTH, expand=True, pady=(10, 0))

        canvas_panel = widgets.Frame(self._reading_split, style="Surface.TFrame", padding=(0, 0, 8, 0))
        editor_panel = widgets.Frame(self._reading_split, style="Surface.TFrame", padding=(8, 0, 0, 0))
        self._reading_split.add(canvas_panel, weight=3)
        self._reading_split.add(editor_panel, weight=2)

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
        self._quick_tasks_entry.bind("<FocusOut>", self._on_reading_fields_focus_out)
        self._quick_tasks_entry.bind("<Return>", self._on_reading_fields_commit)
        self._quick_tasks_entry.bind("<Escape>", self._on_reading_fields_escape)

        self._form_tasks_text = ui.Text(self._task_input_container, height=4, wrap="word")
        # No <Return> binding here: Enter must insert a newline between tasks
        # in Formular-Modus. <FocusOut> is the commit path for this widget.
        self._form_tasks_text.bind("<FocusOut>", self._on_reading_fields_focus_out)
        self._form_tasks_text.bind("<Escape>", self._on_reading_fields_escape)

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
        # Only shown in Extraseiten-Modus: the standard Aufgaben/Punkte editor
        # commits automatically on FocusOut (see _commit_reading_fields_if_possible).
        self._save_region_button = widgets.Button(
            region_actions,
            text="Speichern",
            style="SecondaryAction.TButton",
            command=self._save_selected_extra_region,
        )
        self._save_region_button.pack(side=ui.LEFT)
        self._attach_hover_help(self._save_region_button, label="Extraseiten-Zuordnung speichern", shortcut=None)

        self._delete_region_button = widgets.Button(
            region_actions,
            text="Loeschen",
            style="SecondaryAction.TButton",
            command=self._delete_selected_region,
        )
        self._delete_region_button.pack(side=ui.LEFT, padx=(8, 0))
        self._attach_hover_help(self._delete_region_button, label="Aktiven Bereich loeschen", shortcut="Entf")

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

        self._correction_finished_all_check = widgets.Checkbutton(
            correction_form,
            text="Bereich: alle als fertig markieren",
            variable=self._correction_finished_all_var,
            command=self._on_correction_finished_all_toggled,
            state="disabled",
        )
        self._correction_finished_all_check.grid(row=5, column=0, columnspan=3, sticky=ui.W, pady=(8, 0))
        widgets.Label(
            correction_form,
            textvariable=self._correction_finished_all_hint_var,
            style="Muted.TLabel",
        ).grid(row=6, column=0, columnspan=3, sticky=ui.W, pady=(2, 0))

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

        supersymbol_controls = widgets.Frame(correction_form_panel, style="Surface.TFrame")
        supersymbol_controls.pack(fill=ui.X, pady=(10, 0))
        widgets.Label(supersymbol_controls, text="Supersymbol (Filter)", style="Muted.TLabel").pack(anchor=ui.W)

        supersymbol_row1 = widgets.Frame(supersymbol_controls, style="Surface.TFrame")
        supersymbol_row1.pack(fill=ui.X, pady=(4, 0))
        widgets.Label(supersymbol_row1, text="Aufgabe(n)", style="Muted.TLabel").pack(side=ui.LEFT)
        self._supersymbol_scope_var = ui.StringVar(value="")
        self._supersymbol_scope_combo = widgets.Combobox(
            supersymbol_row1,
            textvariable=self._supersymbol_scope_var,
            state="readonly",
            width=16,
            values=(),
        )
        self._supersymbol_scope_combo.pack(side=ui.LEFT, padx=(8, 0))

        supersymbol_row2 = widgets.Frame(supersymbol_controls, style="Surface.TFrame")
        supersymbol_row2.pack(fill=ui.X, pady=(4, 0))
        widgets.Label(supersymbol_row2, text="Punkte", style="Muted.TLabel").pack(side=ui.LEFT)
        self._supersymbol_operator_var = ui.StringVar(value=SUPERSYMBOL_OPERATOR_LABELS[0])
        supersymbol_operator_combo = widgets.Combobox(
            supersymbol_row2,
            textvariable=self._supersymbol_operator_var,
            state="readonly",
            width=4,
            values=SUPERSYMBOL_OPERATOR_LABELS,
        )
        supersymbol_operator_combo.pack(side=ui.LEFT, padx=(8, 0))
        self._supersymbol_value_var = ui.StringVar(value="")
        supersymbol_value_entry = widgets.Entry(supersymbol_row2, textvariable=self._supersymbol_value_var, width=8)
        supersymbol_value_entry.pack(side=ui.LEFT, padx=(6, 0))

        supersymbol_row3 = widgets.Frame(supersymbol_controls, style="Surface.TFrame")
        supersymbol_row3.pack(fill=ui.X, pady=(6, 0))
        self._supersymbol_preview_button = widgets.Button(
            supersymbol_row3,
            text="Vorschau anzeigen",
            style="SecondaryAction.TButton",
            command=self._start_supersymbol_filter,
        )
        self._supersymbol_preview_button.pack(side=ui.LEFT)
        self._attach_hover_help(
            self._supersymbol_preview_button,
            label="Zeigt alle Personen, die die Bedingung erfuellen, ueberlagert an - Klick platziert das aktuell gewaehlte Markierungssymbol bei allen gleichzeitig",
        )
        self._supersymbol_cancel_button = widgets.Button(
            supersymbol_row3,
            text="Abbrechen",
            style="SecondaryAction.TButton",
            command=self._cancel_supersymbol_filter,
        )
        self._supersymbol_cancel_button.pack(side=ui.LEFT, padx=(8, 0))
        self._supersymbol_cancel_button.pack_forget()

        self._supersymbol_info_var = ui.StringVar(value="")
        widgets.Label(
            supersymbol_controls,
            textvariable=self._supersymbol_info_var,
            style="Muted.TLabel",
        ).pack(anchor=ui.W, pady=(4, 0))

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

