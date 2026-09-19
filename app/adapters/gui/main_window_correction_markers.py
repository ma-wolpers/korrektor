from __future__ import annotations

from app.adapters.gui.main_window_constants import (
    CORRECTION_ALT_MODIFIER_MASKS,
    CORRECTION_DEFAULT_COLOR_NAME,
    CORRECTION_DEFAULT_FONT_SIZE_PT,
    CORRECTION_MARKER_COLORS,
    CORRECTION_MARKER_TOOLS,
)

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui


class MainWindowCorrectionMarkersMixin:
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

    @classmethod
    def _marker_color_name_for_hex(cls, color_hex: str) -> str:
        normalized = cls._normalize_marker_color_hex(color_hex)
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

    @staticmethod
    def _normalize_rotation_deg(raw_deg: float) -> float:
        # PDF freetext rotation is reliable for 90-degree steps.
        snapped = int(round(float(raw_deg) / 90.0)) * 90
        return float(snapped % 360)

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

    def _on_correction_canvas_press(self, event: ui.Event[ui.Misc]):
        """Handle a click on the correction canvas: Supersymbol apply, or normal select/place."""
        if not self._correction_mode_active:
            return None
        self._correction_canvas.focus_set()
        canvas_x = float(self._correction_canvas.canvasx(event.x))
        canvas_y = float(self._correction_canvas.canvasy(event.y))

        if self._supersymbol_filter_active:
            self._apply_supersymbol_at_canvas_position(canvas_x, canvas_y)
            return "break"

        self._correction_drag_alt_override = False
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
