from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(slots=True)
class HistoryAction:
    description: str
    undo: Callable[[], None]
    redo: Callable[[], None]


class UndoHistory:
    """Session-local undo/redo stack for content mutations."""

    def __init__(self, *, max_entries: int = 200) -> None:
        self._max_entries = max(1, int(max_entries))
        self._undo_stack: list[HistoryAction] = []
        self._redo_stack: list[HistoryAction] = []

    def push(self, action: HistoryAction) -> None:
        self._undo_stack.append(action)
        self._redo_stack.clear()
        if len(self._undo_stack) > self._max_entries:
            self._undo_stack = self._undo_stack[-self._max_entries :]

    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    def peek_undo(self) -> str | None:
        if not self._undo_stack:
            return None
        return self._undo_stack[-1].description

    def peek_redo(self) -> str | None:
        if not self._redo_stack:
            return None
        return self._redo_stack[-1].description

    def undo(self) -> str | None:
        if not self._undo_stack:
            return None
        action = self._undo_stack.pop()
        action.undo()
        self._redo_stack.append(action)
        return action.description

    def redo(self) -> str | None:
        if not self._redo_stack:
            return None
        action = self._redo_stack.pop()
        action.redo()
        self._undo_stack.append(action)
        return action.description
