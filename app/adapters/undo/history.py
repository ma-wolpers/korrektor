from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(slots=True)
class HistoryAction:
    """One undo/redo-capable entry on the session-local history stack.

    `context` tells the caller *how the UI should be refreshed* after this
    action is undone/redone - it is not a general classification of history
    action kinds, only a two-way switch:
    - "content": the currently open exam's identity is unchanged, only its
      content mutated (annotations, scores, regions, ...). The caller should
      reload the exam data in place and keep the active mode/view/selection
      intact (see `UiIntentControllerHistoryMixin._refresh_after_history_action`).
    - "lifecycle": the exam's identity itself changed (created/deleted) or
      the index directory changed - the previous full-navigation-reset
      refresh (back to the overview/detail hub) is still correct here.
    Defaults to "content" because that is the common case: every mutation on
    an already-open exam.
    """

    description: str
    undo: Callable[[], None]
    redo: Callable[[], None]
    context: str = "content"


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

    def undo(self) -> HistoryAction | None:
        """Pop and run the top undo action, returning it (or None if the stack is empty).

        Returns the whole `HistoryAction` (not just its description) so
        callers can branch on `.context` to decide how to refresh the UI
        afterwards, without a second lookup.
        """
        if not self._undo_stack:
            return None
        action = self._undo_stack.pop()
        action.undo()
        self._redo_stack.append(action)
        return action

    def redo(self) -> HistoryAction | None:
        """Pop and run the top redo action, returning it (or None if the stack is empty)."""
        if not self._redo_stack:
            return None
        action = self._redo_stack.pop()
        action.redo()
        self._undo_stack.append(action)
        return action
