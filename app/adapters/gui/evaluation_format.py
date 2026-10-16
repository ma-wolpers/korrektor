"""Display formatting of evaluation values - one place for "unscored" vs. "0" and for task labels.

Unscored (``None``) is always shown as an en dash, a real 0 as "0", so the two can never
be confused in any view of the "Auswertung" window. `task_label` is the one task label
of the GUI (Zuschnitt checklist, Korrektur dropdown, Auswertung), so a bonus task is
marked the same way everywhere. No computation happens here.
"""

from __future__ import annotations

UNSCORED = "–"


def number(value: float | None) -> str:
    """``None`` -> "–", otherwise the compact number (``2``, ``1.5``)."""
    return UNSCORED if value is None else f"{value:g}"


def points(achieved: float | None, max_points: float) -> str:
    """"1.5 / 2", or "– / 2" while unscored."""
    return f"{number(achieved)} / {max_points:g}"


def task_points(achieved: float | None, max_points: float, is_bonus: bool) -> str:
    """`points` of one task, marked "(Bonus)" for a bonus task: "1 / 2 (Bonus)"."""
    return points(achieved, max_points) + (" (Bonus)" if is_bonus else "")


def percent(value: float | None) -> str:
    """"75 %" (rounded), or "–"."""
    return UNSCORED if value is None else f"{value:.0f} %"


def task_label(code: str, max_points: float, is_bonus: bool, *, compact: bool = False) -> str:
    """"2C (2 P.)" / "2C (2 P., Bonus)"; ``compact`` for column headers: "2C (2)" / "2C (+2)"."""
    if compact:
        return f"{code} ({'+' if is_bonus else ''}{max_points:g})"
    return f"{code} ({max_points:g} P.{', Bonus' if is_bonus else ''})"


def count_of(count: int, total: int) -> str:
    """"3/5"."""
    return f"{count}/{total}"
