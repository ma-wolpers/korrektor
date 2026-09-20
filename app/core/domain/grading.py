from __future__ import annotations

from dataclasses import dataclass

from app.core.domain.grading_scale import GradingScaleSnapshot

# Percentages are compared at 2-decimal precision - same rationale and
# value as score_filter.py's _POINTS_PRECISION: avoids float-noise making an
# exact-boundary percentage (e.g. 80.0%) miss its own threshold.
_PERCENT_PRECISION = 2


class GradingError(ValueError):
    """Raised when a grade cannot be determined - never silently defaulted."""


@dataclass(slots=True)
class GradeResult:
    grade_label: str
    percentage: float


def resolve_grade(achieved_points: float, max_points: float, snapshot: GradingScaleSnapshot) -> GradeResult:
    """Resolve one student's grade from achieved/max points against a frozen `GradingScaleSnapshot`.

    Percentage-based, not points-based (`percentage = achieved_points /
    max_points * 100`, rounded to 2 decimals), so tasks/Bereiche with
    different `max_points` stay comparable on the same scale. Thresholds
    are evaluated highest-first: the *highest* `min_percent` the student's
    percentage still reaches wins (an exact match, e.g. exactly 80.0% on an
    ">= 80" threshold, is a hit for that threshold, not the next-lower
    one) - this must stay consistent with `GradeThreshold.min_percent`'s
    "at least this percent" semantics.

    Raises `GradingError` (never returns a silent fallback grade) when
    `max_points <= 0` (grading is undefined without a real maximum) or when
    no threshold is satisfied (percentage below the lowest `min_percent` -
    a gap in the scale's own definition, not a fixable default). Callers
    that need to attribute the failure to a specific person/task/Bereich
    (e.g. the Noten-Superposition bulk action) add that context themselves;
    this function only knows the numbers it was given.
    """
    if max_points <= 0:
        raise GradingError(f"Ungueltige maximale Punktzahl fuer die Notenberechnung: {max_points}")

    percentage = round((achieved_points / max_points) * 100.0, _PERCENT_PRECISION)
    for threshold in sorted(snapshot.thresholds, key=lambda item: item.min_percent, reverse=True):
        if percentage >= threshold.min_percent:
            return GradeResult(grade_label=threshold.grade_label, percentage=percentage)

    raise GradingError(
        f"Keine Notenstufe des Notenschluessels '{snapshot.name}' erreicht ({percentage:g}% erreicht)."
    )
