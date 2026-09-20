"""Facade module preserving the public MainWindow import path and constants.

Split across `main_window_*.py` mixin files (see docs/ARCHITEKTUR.md and
the file-size-split plan) to stay under the project's ~300-line-of-code
convention. Internal mixin files import their own dependencies directly
from their source modules (e.g. `main_window_types.py`,
`main_window_constants.py`), never from this facade - this facade exists
for external callers/tests only (see e.g. tests/test_annotation_export_alignment.py,
tests/test_person_area_finished.py, tests/test_extra_sequence.py, which
import `MainWindow`/`CorrectionTemplate`/`DraftRegion`/`CORRECTION_MARKER_TOOLS`
directly from here).
"""

from __future__ import annotations

from app.adapters.gui.main_window_types import CorrectionTemplate, DraftRegion
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
    SUPERSYMBOL_OPERATOR_BY_LABEL,
    SUPERSYMBOL_OPERATOR_LABELS,
    SUPERSYMBOL_SUM_SCOPE_LABEL,
)

from app.adapters.gui.main_window_base import MainWindowBase
from app.adapters.gui.main_window_layout import MainWindowLayoutMixin
from app.adapters.gui.main_window_dispatch import MainWindowDispatchMixin
from app.adapters.gui.main_window_supersymbol import MainWindowSupersymbolMixin
from app.adapters.gui.main_window_correction_markers_export import MainWindowCorrectionMarkersExportMixin
from app.adapters.gui.main_window_correction_markers_clipboard import MainWindowCorrectionMarkersClipboardMixin
from app.adapters.gui.main_window_correction_markers_transform import MainWindowCorrectionMarkersTransformMixin
from app.adapters.gui.main_window_correction_markers import MainWindowCorrectionMarkersMixin
from app.adapters.gui.main_window_correction_sync import MainWindowCorrectionSyncMixin
from app.adapters.gui.main_window_correction_zoom import MainWindowCorrectionZoomMixin
from app.adapters.gui.main_window_correction_completion import MainWindowCorrectionCompletionMixin
from app.adapters.gui.main_window_correction_form import MainWindowCorrectionFormMixin
from app.adapters.gui.main_window_naming import MainWindowNamingMixin
from app.adapters.gui.main_window_extra_pages import MainWindowExtraPagesMixin
from app.adapters.gui.main_window_grading_scale import MainWindowGradingScaleMixin
from app.adapters.gui.main_window_task_categories import MainWindowTaskCategoriesMixin
from app.adapters.gui.main_window_student_result import MainWindowStudentResultMixin
from app.adapters.gui.main_window_reading_canvas import MainWindowReadingCanvasMixin
from app.adapters.gui.main_window_reading import MainWindowReadingMixin
from app.adapters.gui.main_window_correction_core import MainWindowCorrectionCoreMixin
from app.adapters.gui.main_window_region_editor import MainWindowRegionEditorMixin
from app.adapters.gui.main_window_region_specs import MainWindowRegionSpecsMixin
from app.adapters.gui.main_window_shortcuts_debug import MainWindowShortcutsDebugMixin
from app.adapters.gui.main_window_shortcuts import MainWindowShortcutsMixin
from app.adapters.gui.main_window_menu import MainWindowMenuMixin
from app.adapters.gui.main_window_overview import MainWindowOverviewMixin
from app.adapters.gui.main_window_view_state import MainWindowViewStateMixin
from app.adapters.gui.main_window_view_transitions import MainWindowViewTransitionsMixin
from app.adapters.gui.main_window_theme import MainWindowThemeMixin


class MainWindow(
    MainWindowLayoutMixin,
    MainWindowDispatchMixin,
    MainWindowSupersymbolMixin,
    MainWindowCorrectionMarkersExportMixin,
    MainWindowCorrectionMarkersClipboardMixin,
    MainWindowCorrectionMarkersTransformMixin,
    MainWindowCorrectionMarkersMixin,
    MainWindowCorrectionSyncMixin,
    MainWindowCorrectionZoomMixin,
    MainWindowCorrectionCompletionMixin,
    MainWindowCorrectionFormMixin,
    MainWindowNamingMixin,
    MainWindowExtraPagesMixin,
    MainWindowGradingScaleMixin,
    MainWindowTaskCategoriesMixin,
    MainWindowStudentResultMixin,
    MainWindowReadingCanvasMixin,
    MainWindowReadingMixin,
    MainWindowCorrectionCoreMixin,
    MainWindowRegionEditorMixin,
    MainWindowRegionSpecsMixin,
    MainWindowShortcutsDebugMixin,
    MainWindowShortcutsMixin,
    MainWindowMenuMixin,
    MainWindowOverviewMixin,
    MainWindowViewStateMixin,
    MainWindowViewTransitionsMixin,
    MainWindowThemeMixin,
    MainWindowBase,
):
    """Tkinter-Desktopanwendung fuer die Klausurkorrektur."""
