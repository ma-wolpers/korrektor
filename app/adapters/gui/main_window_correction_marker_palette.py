"""Correction marker palette: colour choice and one image button per catalog symbol.

The buttons show the symbols exactly as they will be drawn (``mark_renderer``), in
the currently chosen marker colour (re-rendered when the colour changes; a coloured
icon stays visible on light and dark themes). The tooltip names the symbol and its
keyboard shortcut. Moved out of ``main_window_correction_markers.py`` (file-size rule)
when the catalog (``app/core/domain/mark_symbols.py``) replaced the former
``CORRECTION_MARKER_TOOLS`` tuple.
"""

from __future__ import annotations

import base64
import io

from app.adapters.gui.main_window_constants import CORRECTION_MARKER_COLORS
from app.core.domain.mark_symbols import MARK_SYMBOLS, SYMBOL_BY_KEY
from app.infrastructure.rendering.mark_renderer import MarkStyle, render_mark_image

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import on_combobox_select, ui, widgets

PALETTE_COLUMNS = 6
ICON_BOX_PX = (30, 22)
ICON_FONT_PT = 14.0


def shortcut_display(shortcut: str) -> str:
    """Tooltip text of a catalog shortcut: ``"t"`` -> ``"T"``, ``"T"`` -> ``"Umschalt+T"``."""
    if shortcut.isalpha() and shortcut.isupper():
        return f"Umschalt+{shortcut}"
    return shortcut.upper()


def palette_icon_png(content: str, color_hex: str) -> bytes:
    """The symbol ``content`` rendered and shrunk to fit ``ICON_BOX_PX`` (PNG bytes)."""
    image = render_mark_image(MarkStyle("symbol", content, color_hex, ICON_FONT_PT), 2.0)
    image.thumbnail(ICON_BOX_PX)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class MainWindowCorrectionMarkerPaletteMixin:
    """Colour combobox, symbol buttons and the current-tool state."""

    def _build_correction_view_form_markers(self) -> None:
        """"Markierungen" block: colour choice and the symbol grid."""
        marker_controls = widgets.Frame(self._correction_form_panel.content, style="Surface.TFrame")
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
        on_combobox_select(color_combo, self._on_correction_marker_color_changed)

        grid = widgets.Frame(marker_controls, style="Surface.TFrame")
        grid.pack(anchor=ui.W, pady=(6, 0))
        self._marker_palette_buttons: dict[str, widgets.Button] = {}
        self._marker_palette_photos: list[ui.PhotoImage] = []
        for position, symbol in enumerate(MARK_SYMBOLS):
            button = widgets.Button(
                grid,
                style="SecondaryAction.TButton",
                command=lambda value=symbol.key: self._set_correction_marker_tool(value),
            )
            button.grid(row=position // PALETTE_COLUMNS, column=position % PALETTE_COLUMNS, padx=(0, 4), pady=(0, 4))
            self._attach_hover_help(button, label=f"Markierung: {symbol.label}", shortcut=shortcut_display(symbol.shortcut))
            self._marker_palette_buttons[symbol.key] = button
        self._refresh_marker_palette_icons()
        self._correction_marker_controls_frame = marker_controls

    def _refresh_marker_palette_icons(self) -> None:
        """(Re-)draw every palette icon in the current marker colour."""
        color_hex = self._current_marker_color_hex()
        self._marker_palette_photos.clear()
        for symbol in MARK_SYMBOLS:
            png = palette_icon_png(symbol.content, color_hex)
            photo = ui.PhotoImage(data=base64.b64encode(png).decode("ascii"), format="png")
            self._marker_palette_photos.append(photo)
            self._marker_palette_buttons[symbol.key].configure(image=photo)

    @staticmethod
    def _marker_tool_lookup(tool_key: str) -> tuple[str, str] | None:
        """``(content, label)`` of catalog symbol ``tool_key``, or ``None``."""
        symbol = SYMBOL_BY_KEY.get(tool_key)
        return (symbol.content, symbol.label) if symbol is not None else None

    def _set_correction_marker_tool(self, tool_key: str) -> None:
        """Make ``tool_key`` the symbol a canvas click places (unknown keys are ignored)."""
        symbol = SYMBOL_BY_KEY.get(tool_key)
        if symbol is None:
            return
        self._correction_marker_tool_key = tool_key
        self._correction_marker_info_var.set(f"Markierung: {symbol.label} ({shortcut_display(symbol.shortcut)})")
