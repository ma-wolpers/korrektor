from __future__ import annotations

from pathlib import Path

import fitz

from app.adapters.bootstrap.wiring import GuiDependencies
from app.app_info import APP_INFO
from app.adapters.gui.main_window_types import CorrectionTemplate, DraftRegion
from app.adapters.gui.ui_intents import UiIntent
from app.adapters.gui.view_models import ExamOverviewRow
from app.core.domain.models import ExamProject
from bw_gui.contracts.hsm import build_ui_hsm_contract
from bw_gui.contracts.keybinding import KeybindingRegistry
from bw_gui.contracts.popup import POPUP_KIND_MODAL, POPUP_KIND_NON_MODAL, PopupPolicy, PopupPolicyRegistry

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import BwBaseWindow, ui, widgets
from bw_gui.menu import section_spec
from bw_gui.theming import normalize_theme_key


class MainWindowBase(BwBaseWindow):
    """`__init__`/`build_menu`/`build_content` + the `BwBaseWindow` override
    pair (`open_settings`/`apply_theme`) - the one class with an `__init__`
    in the whole hierarchy (see docs/ARCHITEKTUR.md: mixins never define
    their own `__init__`, since `BwBaseWindow.__init__` invokes
    `build_menu()`/`build_content()` synchronously and all state must exist
    before that call).
    """

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
        self._grading_scale_popup: ui.Toplevel | None = None
        self._grading_scale_tree: widgets.Treeview | None = None
        self._grading_scale_selected_id: str | None = None
        self._grading_scale_assignment_var: ui.StringVar | None = None
        self._grading_scale_assign_id_by_label: dict[str, str] = {}
        self._task_category_popup: ui.Toplevel | None = None
        self._task_category_tasks_frame: widgets.Frame | None = None
        self._task_category_categories_frame: widgets.Frame | None = None
        self._task_category_drag_drop = None
        self._student_result_popup: ui.Toplevel | None = None
        self._student_result_cursor = 0
        self._student_result_scores: dict[str, dict[str, float]] | None = None
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
        self._superposition_mode: str | None = None
        self._superposition_task_codes: list[str] = []
        settings = self.deps.runtime_settings
        self._default_annotation_color_hex = self._normalize_marker_color_hex(settings.default_annotation_color)
        self._default_annotation_font_size = self._normalize_marker_font_size(settings.default_annotation_pdf_font_size)
        self._correction_selected_annotation_id: str | None = None
        self._correction_drag_annotation_id: str | None = None
        self._correction_drag_offset_pdf: tuple[float, float] | None = None
        self._correction_drag_alt_override = False
        self._correction_drag_before_payload: dict[str, object] | None = None
        self._correction_drag_moved = False
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
