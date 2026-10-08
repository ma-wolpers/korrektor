"""List-ordering helpers for the PDF import's order dialog (presentation logic, Tk-free, unit-tested)."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import TypeVar

T = TypeVar("T")

_DIGITS = re.compile(r"(\d+)")


def natural_sort_key(path: Path) -> tuple:
    """Sort key: natural order of the case-folded filename, then exact filename, then full path.

    ``scan_2.pdf`` sorts before ``scan_10.pdf``. ``re.split`` with a
    capturing group alternates text and digit parts, so positions always
    compare str with str and int with int. The two tie-breakers make the
    order deterministic even when natural keys are equal (``Scan_01`` vs.
    ``scan_1``, or identical names in different folders - which a single
    file dialog cannot produce, see the order dialog).
    """
    parts = _DIGITS.split(path.name.casefold())
    natural = tuple(int(part) if index % 2 else part for index, part in enumerate(parts))
    return (natural, path.name, str(path))


def natural_sort_paths(paths: Iterable[Path]) -> list[Path]:
    """Return ``paths`` sorted by `natural_sort_key` (initial merge order)."""
    return sorted(paths, key=natural_sort_key)


def move_item(items: Sequence[T], index: int, delta: int) -> tuple[list[T], int]:
    """Return a *new* list with ``items[index]`` moved by ``delta`` and the item's new index.

    Never mutates ``items``. A move that would leave the list (or an invalid
    ``index``) returns an unchanged copy and the same index.

    Example: ``move_item(["a", "b", "c"], 2, -1)`` -> ``(["a", "c", "b"], 1)``.
    """
    moved = list(items)
    target = index + delta
    if not (0 <= index < len(moved)) or not (0 <= target < len(moved)):
        return moved, index
    item = moved.pop(index)
    moved.insert(target, item)
    return moved, target
