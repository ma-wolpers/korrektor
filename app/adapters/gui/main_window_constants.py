from __future__ import annotations

from app.core.domain.grading_scale import SCALE_TYPE_POINTS_0_15, SCALE_TYPE_SCHOOL_1_6
from app.core.domain.score_filter import FilterOperator

CORRECTION_ZOOM_MIN_PERCENT = 10
CORRECTION_ZOOM_MAX_PERCENT = 240

SUPERSYMBOL_OPERATOR_BY_LABEL: dict[str, FilterOperator] = {
    "<": "<",
    "≤": "<=",
    "=": "==",
    "≥": ">=",
    ">": ">",
}
SUPERSYMBOL_OPERATOR_LABELS: tuple[str, ...] = tuple(SUPERSYMBOL_OPERATOR_BY_LABEL.keys())
SUPERSYMBOL_SUM_SCOPE_LABEL = "Summe aller Aufgaben"
SUPERSYMBOL_MAIN_TASK_SCOPE_LABEL = "Aufgabe {main} gesamt ({members})"
SUPERPOSITION_WHOLE_EXAM_LABEL = "Gesamte Klausur"

CORRECTION_MARKER_COLORS: dict[str, str] = {
    "Rot": "#d62828",
    "Pink": "#ff4fa3",
    "Blau": "#1d4ed8",
    "Grün": "#2a9d8f",
    "Orange": "#f77f00",
    "Violett": "#7b2cbf",
    "Schwarz": "#111111",
}

CORRECTION_DEFAULT_COLOR_NAME = "Rot"
CORRECTION_DEFAULT_FONT_SIZE_PT = 14.0

GRADING_SCALE_TYPE_BY_LABEL: dict[str, str] = {
    "Punktnoten (0-15)": SCALE_TYPE_POINTS_0_15,
    "Schulnoten (sehr gut 1 - ungenügend 6)": SCALE_TYPE_SCHOOL_1_6,
}
GRADING_SCALE_TYPE_LABELS: tuple[str, ...] = tuple(GRADING_SCALE_TYPE_BY_LABEL.keys())
GRADING_SCALE_TYPE_LABEL_BY_VALUE: dict[str, str] = {value: label for label, value in GRADING_SCALE_TYPE_BY_LABEL.items()}

COMPETENCY_CHART_TYPE_LABELS: tuple[str, ...] = ("Spinnennetz", "Balken")
COMPETENCY_CHART_SCOPE_LABELS: tuple[str, ...] = ("Pro Aufgabe", "Pro Kategorie")
