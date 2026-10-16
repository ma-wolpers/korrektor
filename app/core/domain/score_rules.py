"""Rules for a single score entry, checked before anything is written.

``points_error`` is the one check every score save goes through
(``UiIntentControllerScoringMixin.save_score_immediate``): points must not be negative
and must not exceed the task's own maximum. Bonus tasks have their own maximum too
(``2c:2?`` allows at most 2 points); only their effect on the exam total differs.
"""

from __future__ import annotations

_TOLERANCE = 1e-9


def points_error(points: float, max_points: float, task_code: str) -> str | None:
    """Why ``points`` cannot be saved for ``task_code``, or ``None`` if they can.

    Examples:
        >>> points_error(4.0, 4.0, "2A") is None
        True
        >>> points_error(5.0, 4.0, "2A")
        '5 Punkte sind mehr als die 4 möglichen Punkte von Aufgabe 2A.'
    """
    if points < 0:
        return "Punkte dürfen nicht negativ sein."
    if points > max_points + _TOLERANCE:
        return f"{points:g} Punkte sind mehr als die {max_points:g} möglichen Punkte von Aufgabe {task_code}."
    return None
