from __future__ import annotations

from app.core.domain.grading_scale import SCALE_TYPE_POINTS_1_15, SCALE_TYPE_SCHOOL_1_6
from app.core.domain.score_filter import FilterOperator

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

SUPERSYMBOL_OPERATOR_BY_LABEL: dict[str, FilterOperator] = {
    "<": "<",
    "≤": "<=",
    "=": "==",
    "≥": ">=",
    ">": ">",
}
SUPERSYMBOL_OPERATOR_LABELS: tuple[str, ...] = tuple(SUPERSYMBOL_OPERATOR_BY_LABEL.keys())
SUPERSYMBOL_SUM_SCOPE_LABEL = "Summe aller Aufgaben"

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

GRADING_SCALE_TYPE_BY_LABEL: dict[str, str] = {
    "Punktnoten (1-15)": SCALE_TYPE_POINTS_1_15,
    "Schulnoten (sehr gut 1 - ungenuegend 6)": SCALE_TYPE_SCHOOL_1_6,
}
GRADING_SCALE_TYPE_LABELS: tuple[str, ...] = tuple(GRADING_SCALE_TYPE_BY_LABEL.keys())
GRADING_SCALE_TYPE_LABEL_BY_VALUE: dict[str, str] = {value: label for label, value in GRADING_SCALE_TYPE_BY_LABEL.items()}

COMPETENCY_CHART_TYPE_LABELS: tuple[str, ...] = ("Spinnennetz", "Balken")
COMPETENCY_CHART_SCOPE_LABELS: tuple[str, ...] = ("Pro Aufgabe", "Pro Kategorie")
