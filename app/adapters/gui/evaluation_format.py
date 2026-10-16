"""Display formatting of evaluation values - one place for "unscored" vs. "0".

Unscored (``None``) is always shown as an en dash, a real 0 as "0", so the two can never
be confused in any view of the "Auswertung" window. No computation happens here.
"""

from __future__ import annotations

UNSCORED = "–"


def number(value: float | None) -> str:
    """``None`` -> "–", otherwise the compact number (``2``, ``1.5``)."""
    return UNSCORED if value is None else f"{value:g}"


def points(achieved: float | None, max_points: float) -> str:
    """"1.5 / 2", or "– / 2" while unscored."""
    return f"{number(achieved)} / {max_points:g}"


def percent(value: float | None) -> str:
    """"75 %" (rounded), or "–"."""
    return UNSCORED if value is None else f"{value:.0f} %"


def count_of(count: int, total: int) -> str:
    """"3/5"."""
    return f"{count}/{total}"
