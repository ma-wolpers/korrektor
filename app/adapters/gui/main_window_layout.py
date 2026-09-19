from __future__ import annotations

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui, widgets


class MainWindowLayoutMixin:
    """Thin `_build_layout` orchestrator - all actual widget construction lives
    in the owning mixin of each view/panel (see docs/ARCHITEKTUR.md). Call
    order here is preserved exactly from the original monolithic
    `_build_layout` where it affects initial visual stacking (the
    Korrektur-view's form-panel children have no later re-pack step, unlike
    the Reading-view's toolbars, which `_set_detail_submode` re-arranges
    unconditionally at the end of this method regardless of construction
    order).
    """

    def _build_layout(self, frame=None) -> None:
        shell = widgets.Frame(frame if frame is not None else self, style="App.TFrame", padding=16)
        shell.pack(fill=ui.BOTH, expand=True)

        self._view_stack = widgets.Frame(shell, style="App.TFrame")
        self._view_stack.pack(fill=ui.BOTH, expand=True, pady=(0, 10))

        self._overview_view = widgets.Frame(self._view_stack, style="Surface.TFrame", padding=12)
        self._detail_view = widgets.Frame(self._view_stack, style="Surface.TFrame", padding=12)
        self._reading_view = widgets.Frame(self._view_stack, style="Surface.TFrame", padding=12)
        self._correction_view = widgets.Frame(self._view_stack, style="Surface.TFrame", padding=12)

        self._build_overview_view()
        self._build_detail_view()
        self._build_reading_view()
        self._build_correction_view()

        widgets.Separator(shell).pack(fill=ui.X, pady=(10, 8))
        widgets.Label(shell, textvariable=self._status_var, style="Status.TLabel").pack(anchor=ui.W)

        self._hide_correction_controls()
        self._set_detail_submode("reading")
        self._show_view("overview")

    def _build_reading_view(self) -> None:
        self._build_reading_view_nav_bar()
        self._build_reading_view_extra_toolbar()
        self._build_reading_view_naming_panel()
        self._build_reading_view_mode_row()
        self._build_reading_view_canvas()
        self._build_reading_view_region_editor()

    def _build_correction_view(self) -> None:
        self._build_correction_view_canvas_header()
        self._build_correction_view_canvas()
        self._build_correction_view_form_points_comment()
        self._build_correction_view_form_finished_checkboxes()
        self._build_correction_view_form_markers()
        self._build_correction_view_form_markers_transform()
        self._build_correction_view_form_supersymbol()
        self._build_correction_view_form_save_nav()
