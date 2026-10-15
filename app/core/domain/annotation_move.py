"""Moving correction marks: always inside a region, re-homed into the region they are dragged into.

A mark (`PdfAnnotation`, symbol and text alike) belongs to exactly one
region via ``region_id``; its point (``x``/``y``) must lie inside that
region's box - the PDF export skips marks outside it, and the correction
view draws a mark through its own region's crop, so a point outside would
show up on a neighbouring crop or in empty canvas space. This module is the
single rule for a move gesture: clamp into the target box, and when the
target is another region, switch ``region_id``/``page_number`` (and, if
needed, ``task_code``) of every moved mark together.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.core.domain.models import PdfAnnotation


@dataclass(frozen=True, slots=True)
class MoveTarget:
    """The region a mark is being moved into.

    ``box`` is the PDF-point rectangle the point is clamped into (the
    rendered crop of the region); ``task_codes`` are the region's tasks,
    used to keep a mark's ``task_code`` consistent with its region.
    """

    region_id: str
    page_number: int
    box: tuple[float, float, float, float]
    task_codes: tuple[str, ...]


def clamp_into_box(x: float, y: float, box: tuple[float, float, float, float]) -> tuple[float, float]:
    """Return ``(x, y)`` moved to the nearest point inside ``box`` (unchanged if already inside)."""
    x0, y0, x1, y1 = box
    return min(max(x, x0), x1), min(max(y, y0), y1)


def move_annotations(
    anchor: PdfAnnotation,
    followers: Sequence[PdfAnnotation],
    target_x: float,
    target_y: float,
    target: MoveTarget,
    fallback_task_code: str,
) -> bool:
    """Move ``anchor`` to ``(target_x, target_y)`` inside ``target`` and ``followers`` by the same delta.

    ``anchor`` is the dragged mark; ``followers`` are the other members of
    its sync group that move together (empty for an unsynced mark or an
    Alt-drag). Every moved mark is clamped into ``target.box`` on its own,
    so a follower never ends up outside the region either. If
    ``target.region_id`` differs from a mark's region, the mark is re-homed:
    ``region_id`` and ``page_number`` follow the target, and a non-empty
    ``task_code`` that is not one of the target's tasks becomes
    ``fallback_task_code`` (the task the view currently shows - always one
    of the target's tasks, since the view only stacks regions of that
    task). An empty ``task_code`` (e.g. a Supersymbol "Σ") stays empty.

    Mutates the marks in place; persistence and undo are the caller's job.
    Returns ``True`` if any mark changed.
    """
    clamped_x, clamped_y = clamp_into_box(target_x, target_y, target.box)
    dx = clamped_x - anchor.x
    dy = clamped_y - anchor.y
    changed = False
    for mark in (anchor, *followers):
        new_x, new_y = clamp_into_box(mark.x + dx, mark.y + dy, target.box)
        if (new_x, new_y) != (mark.x, mark.y):
            mark.x, mark.y = new_x, new_y
            changed = True
        if mark.region_id != target.region_id:
            mark.region_id = target.region_id
            mark.page_number = target.page_number
            if mark.task_code and mark.task_code not in target.task_codes:
                mark.task_code = fallback_task_code
            changed = True
    return changed
