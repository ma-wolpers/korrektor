"""Task input with shorthand: "4a-d:1,4,2,3;5a:2;6b-c:1,4" (pure, no GUI).

Grammar (binding, see ARCHITEKTUR "Aufgaben-Eingabe"):

- Entries are separated by ``;`` or line breaks; an entry is ``Codes[:Punkte]``.
- ``Codes`` is one code or a run at the *end* of the code: a single letter
  run (``4a-d``), a digit run (``2.1-4`` -> 2.1 … 2.4, ``1-3``) or the long
  form (``4a-4d``). Codes are canonical upper case (``4a`` -> ``4A``);
  reversed or mixed runs are rejected.
- Points for **one** code: ``,`` is the decimal comma (``5a:1,5`` = 1.5).
- Points for **n > 1** codes: exactly n values separated by ``,`` or one
  value for all; decimals inside such a list use ``.`` (``4a-b:1.5,2``).
- No ``:`` means "no points" (``None``) - only allowed where the caller
  accepts references to existing tasks. ``4a:`` (empty value) is an error.
- A code may occur only once per input.

`format_task_specs` is the inverse: it compresses consecutive codes back
into runs, so ``parse(format(parse(x))) == parse(x)`` for every valid ``x``.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

_CODE_TAIL = re.compile(r"^(.*?)([A-Za-z]+|\d+)$")


@dataclass(frozen=True)
class TaskSpec:
    """One parsed task: canonical ``code`` and ``points`` (``None`` = reference to an existing task)."""

    code: str
    points: float | None


@dataclass(frozen=True)
class TaskSpecParseResult:
    """Parsed entries in input order, or a German ``error`` message (then ``items`` is empty)."""

    items: tuple[TaskSpec, ...]
    error: str | None = None


class _SpecError(ValueError):
    pass


def parse_task_specs(text: str, *, require_points: bool = True) -> TaskSpecParseResult:
    """Parse the task input (quick or form mode); see the module docstring for the grammar."""
    items: list[TaskSpec] = []
    seen: set[str] = set()
    try:
        for entry in (part.strip() for part in re.split(r"[;\n]", text)):
            if not entry:
                continue
            for spec in _parse_entry(entry, require_points):
                if spec.code in seen:
                    raise _SpecError(f"„{spec.code}“ kommt mehrfach vor.")
                seen.add(spec.code)
                items.append(spec)
    except _SpecError as exc:
        return TaskSpecParseResult(items=(), error=str(exc))
    return TaskSpecParseResult(items=tuple(items))


def _parse_entry(entry: str, require_points: bool) -> list[TaskSpec]:
    """One ``Codes[:Punkte]`` entry -> its task specs."""
    if entry.count(":") > 1:
        raise _SpecError(f"„{entry}“: zu viele Doppelpunkte (Form: 4a:2 oder 4a-c:1,2,1).")
    codes_text, _, points_text = entry.partition(":")
    codes = _expand_codes(codes_text.strip(), entry)
    if ":" not in entry:
        if require_points:
            raise _SpecError(f"„{entry}“: Punkte fehlen (z. B. {codes[0]}:2).")
        return [TaskSpec(code, None) for code in codes]
    points = _parse_points(points_text.strip(), len(codes), entry)
    return [TaskSpec(code, value) for code, value in zip(codes, points)]


def _expand_codes(text: str, entry: str) -> list[str]:
    """``4a-d`` -> ``[4A, 4B, 4C, 4D]``; a single code -> ``[CODE]``."""
    if not text:
        raise _SpecError(f"„{entry}“: Aufgaben-Code fehlt.")
    if text.count("-") > 1:
        raise _SpecError(f"„{entry}“: nur ein Bindestrich pro Bereich erlaubt (z. B. 4a-d).")
    if "-" not in text:
        return [text.upper()]
    left, right = (part.strip() for part in text.split("-"))
    match = _CODE_TAIL.match(left)
    if not right or match is None:
        raise _SpecError(f"„{entry}“: unvollständiger Bereich (z. B. 4a-d oder 2.1-4).")
    prefix, start = match.group(1), match.group(2)
    end_match = _CODE_TAIL.match(right)
    end = right
    if end_match is not None and end_match.group(1):
        if end_match.group(1).upper() != prefix.upper():
            raise _SpecError(f"„{entry}“: Anfang und Ende gehören nicht zur selben Aufgabe.")
        end = end_match.group(2)
    if start.isdigit() and end.isdigit():
        first, last = int(start), int(end)
        width = len(start) if start.startswith("0") else 0
        values = [str(number).zfill(width) for number in range(first, last + 1)]
    elif start.isalpha() and end.isalpha() and len(start) == 1 and len(end) == 1:
        first, last = ord(start.upper()), ord(end.upper())
        values = [chr(number) for number in range(first, last + 1)]
    else:
        raise _SpecError(f"„{entry}“: Bereich nur über einen Buchstaben (4a-d) oder Zahlen (2.1-4).")
    if not values:
        raise _SpecError(f"„{entry}“: Bereich läuft rückwärts.")
    return [f"{prefix}{value}".upper() for value in values]


def _parse_points(text: str, count: int, entry: str) -> list[float]:
    """Points for ``count`` codes: decimal comma for one code, list or shared value for several."""
    if not text:
        raise _SpecError(f"„{entry}“: Punktwert fehlt nach dem Doppelpunkt.")
    if count == 1:
        if text.count(",") > 1:
            raise _SpecError(f"„{entry}“: eine Aufgabe, aber mehrere Punktwerte.")
        return [_number(text.replace(",", "."), entry)]
    parts = [part.strip() for part in text.split(",")]
    if len(parts) == 1:
        return [_number(parts[0], entry)] * count
    if any(not part for part in parts):
        raise _SpecError(f"„{entry}“: ein Punktwert fehlt.")
    if len(parts) != count:
        raise _SpecError(f"„{entry}“: {count} Aufgaben, aber {len(parts)} Punktwerte.")
    return [_number(part, entry) for part in parts]


def _number(text: str, entry: str) -> float:
    """Parse one points value (``.`` as decimal point); must be a finite number >= 0."""
    try:
        value = float(text)
    except ValueError:
        raise _SpecError(f"„{entry}“: „{text}“ ist keine Zahl.") from None
    if not math.isfinite(value) or value < 0:
        raise _SpecError(f"„{entry}“: Punkte müssen eine Zahl ≥ 0 sein.")
    return value


def format_task_specs(items, *, separator: str = "; ") -> str:
    """Inverse of `parse_task_specs`: consecutive codes with the same prefix become runs.

    ``items`` may be `TaskSpec`s or ``(code, points)`` tuples. Runs are only
    formed among entries that all have points or all have none; equal values
    collapse to one shared value (``4A-D:2``).
    """
    specs = [item if isinstance(item, TaskSpec) else TaskSpec(item[0], item[1]) for item in items]
    groups: list[list[TaskSpec]] = []
    for spec in specs:
        if groups and _continues_run(groups[-1][-1], spec):
            groups[-1].append(spec)
        else:
            groups.append([spec])
    return separator.join(_format_group(group) for group in groups)


def _continues_run(previous: TaskSpec, current: TaskSpec) -> bool:
    """True if ``current`` directly follows ``previous`` in a run (same prefix, next letter/number, both with or both without points)."""
    if (previous.points is None) != (current.points is None):
        return False
    before, after = _CODE_TAIL.match(previous.code), _CODE_TAIL.match(current.code)
    if before is None or after is None or before.group(1) != after.group(1):
        return False
    a, b = before.group(2), after.group(2)
    if a.isalpha() and b.isalpha() and len(a) == len(b) == 1:
        return ord(b) == ord(a) + 1
    if a.isdigit() and b.isdigit():
        same_width = len(a) == len(b) or not (a.startswith("0") or b.startswith("0"))
        return same_width and int(b) == int(a) + 1
    return False


def _format_group(group: list[TaskSpec]) -> str:
    """Format one run: a single code, ``4A-D`` without points, or with one shared or n individual values."""
    if len(group) == 1:
        spec = group[0]
        return spec.code if spec.points is None else f"{spec.code}:{_format_number(spec.points, decimal=',')}"
    match = _CODE_TAIL.match(group[-1].code)
    codes = f"{group[0].code}-{match.group(2)}"
    if group[0].points is None:
        return codes
    values = [spec.points for spec in group]
    if all(value == values[0] for value in values):
        return f"{codes}:{_format_number(values[0], decimal='.')}"
    return f"{codes}:" + ",".join(_format_number(value, decimal=".") for value in values)


def _format_number(value: float, *, decimal: str) -> str:
    """``1.5`` with the given decimal separator (``,`` for a single code, ``.`` inside lists)."""
    return f"{value:g}".replace(".", decimal)


def task_sort_key(code: str) -> tuple:
    """Natural order of task codes: ``2 < 4A < 4B < 10A``; ``2.1 < 2.10``."""
    return tuple((0, int(part), "") if part.isdigit() else (1, 0, part) for part in re.findall(r"\d+|\D+", code.upper()))


def main_task_of(code: str) -> str:
    """Main task of a (sub)task: the code without its trailing letter run (``4A`` -> ``4``, ``2.1B`` -> ``2.1``)."""
    stripped = re.sub(r"[A-Za-z]+$", "", code.strip().upper())
    return stripped or code.strip().upper()
