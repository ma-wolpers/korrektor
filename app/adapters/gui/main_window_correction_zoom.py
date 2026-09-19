from __future__ import annotations

from app.adapters.gui.main_window_constants import CORRECTION_ZOOM_MAX_PERCENT, CORRECTION_ZOOM_MIN_PERCENT

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui


class MainWindowCorrectionZoomMixin:
    def _refresh_correction_zoom_label(self) -> None:
        self._correction_zoom_info_var.set(f"Zoom: {self._correction_zoom_percent}%")

    def _change_correction_zoom(self, delta: int) -> None:
        """Change the correction zoom level, cancelling any active Supersymbol filter."""
        target = max(CORRECTION_ZOOM_MIN_PERCENT, min(CORRECTION_ZOOM_MAX_PERCENT, self._correction_zoom_percent + delta))
        if target == self._correction_zoom_percent:
            return
        self._correction_zoom_percent = target
        self._refresh_correction_zoom_label()
        # Cancel first: _render_correction_preview() below would otherwise
        # silently overwrite the filtered composite's coordinate mapping
        # (_correction_clip_box/_correction_scale) while a click would still
        # be treated as a Supersymbol placement, misplacing it.
        self._cancel_supersymbol_filter()
        self._render_correction_preview()

    def _reset_correction_zoom(self) -> None:
        """Reset correction zoom to 100%, cancelling any active Supersymbol filter."""
        if self._correction_zoom_percent == 100:
            return
        self._correction_zoom_percent = 100
        self._refresh_correction_zoom_label()
        self._cancel_supersymbol_filter()
        self._render_correction_preview()

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
