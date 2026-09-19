from __future__ import annotations

from bw_gui.theming import apply_window_theme
from bw_gui.theming import configure_ttk_theme
from bw_gui.theming import theme_canvas
from bw_gui.theming._theme_manager import get_theme

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import widgets


class MainWindowThemeMixin:
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
