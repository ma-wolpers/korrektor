"""Zuschnitt navigation dropdowns: "Abgabe" and "Seite" in Schritt 1 and Schritt 2.

Schritt 1 (Superseiten) keeps its state in ``_reading_student_cursor`` and
``_reading_page`` (1-based like everywhere outside PyMuPDF). Schritt 2 (Einzelseiten)
walks ``_extra_sequence`` (``[(student_index, page)]``, sorted by student, then page)
with ``_extra_cursor``. The dropdowns (``NavDropdown``) only show that state; their
keys are stable identities - ``student_id``, the 1-based page number, and in Schritt 2
``(student_id, page)`` - never list positions or label text. Each pick moves the
cursor through the same functions as the buttons and arrow keys, then hands the
keyboard focus back to the window (a focused combobox counts as an input field and
would swallow ←/→).
"""

from __future__ import annotations

import bisect
from collections.abc import Hashable

from app.adapters.gui.nav_dropdown import NavDropdown

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui, widgets


def cursor_after_resequence(sequence: list[tuple[int, int]], target: tuple[int, int] | None) -> int:
    """Cursor for ``target`` in a rebuilt Schritt-2 walk.

    Rule: the same ``(student_index, page)`` if it is still in the walk, otherwise the
    next entry after it (walk order), otherwise the first entry. ``sequence`` must be
    sorted (``_build_extra_sequence`` yields student by student, pages ascending) and
    non-empty.

    Example: walk ``[(0, 2), (1, 1), (1, 3)]``, old target ``(1, 2)`` -> cursor 2 (``(1, 3)``).
    """
    if target is None:
        return 0
    if target in sequence:
        return sequence.index(target)
    position = bisect.bisect_right(sequence, target)
    return position if position < len(sequence) else 0


class MainWindowZuschnittNavigationMixin:
    """Dropdowns for submission and page in both Zuschnitt steps."""

    def _build_reading_nav_dropdowns(self, parent: widgets.Frame) -> None:
        """Schritt 1: "Abgabe" and "Seite" dropdowns in the reading toolbar."""
        widgets.Label(parent, text="Abgabe", style="Muted.TLabel").pack(side=ui.LEFT, padx=(14, 4))
        self._reading_student_dropdown = NavDropdown(parent, width=20, on_pick=self._on_reading_student_picked)
        self._reading_student_dropdown.widget.pack(side=ui.LEFT)
        widgets.Label(parent, text="Seite", style="Muted.TLabel").pack(side=ui.LEFT, padx=(10, 4))
        self._reading_page_dropdown = NavDropdown(parent, width=9, on_pick=self._on_reading_page_picked)
        self._reading_page_dropdown.widget.pack(side=ui.LEFT)

    def _build_extra_nav_dropdowns(self, parent: widgets.Frame) -> None:
        """Schritt 2: "Abgabe" and "Seite" dropdowns in the Einzelseiten toolbar."""
        widgets.Label(parent, text="Abgabe", style="Muted.TLabel").pack(side=ui.LEFT, padx=(14, 4))
        self._extra_student_dropdown = NavDropdown(parent, width=20, on_pick=self._on_extra_student_picked)
        self._extra_student_dropdown.widget.pack(side=ui.LEFT)
        widgets.Label(parent, text="Seite", style="Muted.TLabel").pack(side=ui.LEFT, padx=(10, 4))
        self._extra_page_dropdown = NavDropdown(parent, width=9, on_pick=self._on_extra_page_picked)
        self._extra_page_dropdown.widget.pack(side=ui.LEFT)

    # -- Schritt 1 ------------------------------------------------------------------

    def _reading_max_page(self) -> int:
        """Last selectable page: all PDFs with the Superseite on, else the current person's PDF."""
        if bool(self._superpage_var.get()):
            return self._max_available_page()
        student = self._get_reading_student()
        return max(student.page_count, 1) if student is not None else 1

    def _sync_reading_nav_dropdowns(self) -> None:
        """Show the current person and page; the person list is locked while the Superseite is on."""
        exam = self._current_exam
        students = exam.students if exam is not None else []
        current = self._get_reading_student()
        self._reading_student_dropdown.set_items(
            [(student.student_id, student.display_name) for student in students],
            current.student_id if current is not None else None,
        )
        self._reading_student_dropdown.set_enabled(not bool(self._superpage_var.get()))
        pages = [(page, f"Seite {page}") for page in range(1, self._reading_max_page() + 1)] if students else []
        self._reading_page_dropdown.set_items(pages, self._reading_page)

    def _on_reading_student_picked(self, student_id: Hashable) -> None:
        """Schritt-1 person pick: same move as "Schüler:in ▶" (page clamped to the person's PDF)."""
        if self._current_exam is None:
            return
        for index, student in enumerate(self._current_exam.students):
            if student.student_id == student_id:
                self._change_reading_student(index - self._reading_student_cursor)
                break
        self.root.focus_set()

    def _on_reading_page_picked(self, page: Hashable) -> None:
        """Schritt-1 page pick (1-based page number)."""
        self._change_reading_page(int(page) - self._reading_page)
        self.root.focus_set()

    # -- Schritt 2 ------------------------------------------------------------------

    def _sync_extra_nav_dropdowns(self) -> None:
        """Show the current Schritt-2 person and page; entries come from the walk only."""
        exam = self._current_exam
        sequence = self._extra_sequence if exam is not None else []
        if not sequence:
            self._extra_student_dropdown.set_items([], None)
            self._extra_page_dropdown.set_items([], None)
            return
        self._extra_cursor = max(0, min(self._extra_cursor, len(sequence) - 1))
        student_index, page = sequence[self._extra_cursor]
        student_items = []
        for index in dict.fromkeys(item[0] for item in sequence):
            student = exam.students[index]
            student_items.append((student.student_id, student.display_name))
        current_id = exam.students[student_index].student_id
        self._extra_student_dropdown.set_items(student_items, current_id)
        page_items = [((current_id, p), f"Seite {p}") for s, p in sequence if s == student_index]
        self._extra_page_dropdown.set_items(page_items, (current_id, page))

    def _go_to_extra_cursor(self, cursor: int) -> None:
        """Show walk entry ``cursor`` (no-op if it is the current one)."""
        if not self._extra_mode_active or not self._extra_sequence or cursor == self._extra_cursor:
            return
        self._extra_cursor = cursor
        self._show_current_extra_page()

    def _on_extra_student_picked(self, student_id: Hashable) -> None:
        """Schritt-2 person pick: the person's first page in the walk."""
        if self._current_exam is not None:
            for cursor, (index, _page) in enumerate(self._extra_sequence):
                if self._current_exam.students[index].student_id == student_id:
                    self._go_to_extra_cursor(cursor)
                    break
        self.root.focus_set()

    def _on_extra_page_picked(self, key: Hashable) -> None:
        """Schritt-2 page pick, key ``(student_id, page)``."""
        student_id, page = key
        if self._current_exam is not None:
            for cursor, (index, entry_page) in enumerate(self._extra_sequence):
                if entry_page == page and self._current_exam.students[index].student_id == student_id:
                    self._go_to_extra_cursor(cursor)
                    break
        self.root.focus_set()
