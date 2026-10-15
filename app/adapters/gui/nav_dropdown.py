"""Navigation dropdown: a read-only combobox addressed by stable keys, never by label text.

One building block for every "jump to …" dropdown (correction: task and submission;
Zuschnitt: submission and page). It exists because the former task combo kept its
state in the label text and was moved by setting the ``StringVar`` directly. That
had two consequences:

* bw-gui's selection hook (``on_combobox_select``) never learned about the
  programmatic change, so a later user pick of the value it still remembered was
  swallowed (pick 1A, press ↓ to 1B, pick 1A again -> nothing happened);
* the pick handler read the *new* value from the variable before saving, so the
  entries of the old task were written onto the new one.

``NavDropdown`` keeps a parallel list of keys (task code, ``student_id``, 1-based page
number, ``(student_id, page)`` …) and the callers keep their own cursor as the single
source of truth. All programmatic changes go through bw-gui's
``combobox_selection.set_index(..., notify=False)``: they update bw-gui's remembered
value and never call the pick handler. The handler runs for user picks only.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable, Sequence
from typing import Any

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import combobox_selection, on_combobox_select, ui, widgets

EMPTY_LABEL = "–"

NavItem = tuple[Hashable, str]


class NavDropdown:
    """A read-only combobox whose entries are ``(key, label)`` pairs.

    Usage::

        dropdown = NavDropdown(parent, width=18, on_pick=self._go_to_student_id)
        dropdown.widget.pack(side=ui.LEFT)
        chosen = dropdown.set_items([(s.student_id, s.display_name) for s in students], current_id)

    ``set_items`` and ``select`` never call ``on_pick``; ``on_pick(key)`` runs only when
    the user picks an entry that is not already the selected one.
    """

    def __init__(self, parent: Any, *, width: int, on_pick: Callable[[Hashable], object]) -> None:
        """Create the combobox (read-only, empty) and subscribe to user picks.

        Args:
            parent: Tk parent widget.
            width: Width in characters.
            on_pick: Called with the picked entry's key after a user pick.
        """
        self._var = ui.StringVar(value=EMPTY_LABEL)
        self.widget = widgets.Combobox(parent, textvariable=self._var, state="disabled", width=width, values=())
        self._keys: list[Hashable] = []
        self._labels: list[str] = []
        self._selected: Hashable | None = None
        self._on_pick = on_pick
        on_combobox_select(self.widget, self._on_select)

    @property
    def keys(self) -> tuple[Hashable, ...]:
        """The keys of the current entries, in display order."""
        return tuple(self._keys)

    @property
    def selected_key(self) -> Hashable | None:
        """The key of the selected entry, ``None`` while the list is empty."""
        return self._selected

    def set_items(self, items: Sequence[NavItem], selected_key: Hashable | None) -> Hashable | None:
        """Replace the entries (only if they changed) and select ``selected_key``.

        Rule for a key that is not (or no longer) in ``items``: the first entry is
        selected. The caller gets the key that is actually selected back and moves
        its own cursor accordingly. An empty list disables the combobox and shows
        ``EMPTY_LABEL``; a single entry stays selectable.

        Args:
            items: ``(key, label)`` pairs; keys must be unique.
            selected_key: Key to select.

        Returns:
            The selected key, or ``None`` for an empty list.
        """
        keys = [key for key, _label in items]
        labels = [label for _key, label in items]
        if len(set(keys)) != len(keys):
            raise ValueError("NavDropdown keys must be unique")
        if keys != self._keys or labels != self._labels:
            self._keys, self._labels = keys, labels
            self.widget.configure(values=tuple(labels), state="readonly" if keys else "disabled")
        if not keys:
            self._selected = None
            combobox_selection.set_value(self.widget, EMPTY_LABEL)
            return None
        return self.select(selected_key if selected_key in keys else keys[0])

    def select(self, key: Hashable) -> Hashable:
        """Show ``key`` as selected without calling ``on_pick`` (key must be an entry)."""
        index = self._keys.index(key)
        self._selected = key
        combobox_selection.set_index(self.widget, index)
        return key

    def _on_select(self, change: Any) -> None:
        """bw-gui pick report: forward a user pick of a different entry as its key.

        The caller's navigation ends by calling ``select``/``set_items``. If it
        declines the move (nothing selected afterwards), the previous entry is shown
        again so the combobox never displays a state the view does not have.
        """
        index = change.index
        if index is None or not 0 <= index < len(self._keys):
            return
        key = self._keys[index]
        previous = self._selected
        if key == previous:
            return
        self._on_pick(key)
        if self._selected == previous and previous in self._keys:
            self.select(previous)
