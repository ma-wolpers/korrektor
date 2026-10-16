"""Correction view navigation: current task and person, their dropdowns and the arrow-key moves.

The current task is ``self._correction_task_code`` (a task code, ``None`` before the
correction starts) and the current person is ``self._correction_cursor`` (position in
``self._correction_student_indices``). Both dropdowns only *show* this state
(``NavDropdown``); every move - dropdown pick, ↑/↓, Strg+↑/↓, ←/→, "◀ Person"/"Person ▶" -
runs through ``_go_to_correction_task`` or ``_go_to_correction_cursor``, which save the
points and comment of the *current* task/person first and only then switch. Moved out of
``main_window_correction_core.py`` (file-size rule) when the person dropdown was added.
"""

from __future__ import annotations

from collections.abc import Hashable

from app.adapters.gui.nav_dropdown import NavDropdown
from app.core.domain.models import StudentExam
from app.core.domain.task_spec import main_task_of

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui, widgets


class MainWindowCorrectionNavigationMixin:
    """Task/person state of the correction view and every way to change it."""

    def _build_correction_nav_dropdowns(self, parent: widgets.Frame) -> None:
        """Add "Aufgabe" and "Abgabe" dropdowns to the correction action row.

        Args:
            parent: The action row (packed left to right).
        """
        widgets.Label(parent, text="Aufgabe", style="Muted.TLabel").pack(side=ui.LEFT, padx=(14, 4))
        self._correction_task_dropdown = NavDropdown(parent, width=14, on_pick=self._on_correction_task_picked)
        self._correction_task_dropdown.widget.pack(side=ui.LEFT)
        widgets.Label(parent, text="Abgabe", style="Muted.TLabel").pack(side=ui.LEFT, padx=(14, 4))
        self._correction_student_dropdown = NavDropdown(parent, width=22, on_pick=self._on_correction_student_picked)
        self._correction_student_dropdown.widget.pack(side=ui.LEFT)

    def _refresh_correction_nav_dropdowns(self) -> None:
        """Show the current task and person in the dropdowns (entries rebuilt only when changed).

        Called after every move and after an in-place reload, so a person renamed
        meanwhile shows the new name. Never triggers a pick.
        """
        task_items = [(code, f"{code} ({max_points:g} P.)") for code, max_points in self._correction_task_items]
        self._correction_task_dropdown.set_items(task_items, self._correction_task_code)
        student_items: list[tuple[Hashable, str]] = []
        if self._current_exam is not None:
            for index in self._correction_student_indices:
                student = self._current_exam.students[index]
                student_items.append((student.student_id, student.display_name))
        current = self._current_correction_student()
        self._correction_student_dropdown.set_items(student_items, current.student_id if current else None)

    def _current_correction_student(self) -> StudentExam | None:
        """The person currently shown in the correction view, or ``None``."""
        if not self._current_exam or not self._correction_student_indices:
            return None
        index = self._correction_student_indices[self._correction_cursor]
        return self._current_exam.students[index]

    def _selected_correction_task(self) -> tuple[str | None, float]:
        """``(code, max_points)`` of the current task, or ``(None, 0.0)``."""
        for code, max_points in self._correction_task_items:
            if code == self._correction_task_code:
                return code, max_points
        return None, 0.0

    def _correction_task_is_bonus(self, code: str | None) -> bool:
        """True if ``code`` is a bonus task of the current exam (shorthand ``2c:2?``)."""
        exam = self._current_exam
        return exam is not None and any(task.code == code and task.is_bonus for task in exam.tasks)

    def _go_to_correction_task(self, code: str) -> None:
        """Switch to task ``code``: save the current task's entries, then show all regions of ``code``.

        A code that is not a task, or the current one, changes nothing.
        """
        if not self._correction_mode_active or code == self._correction_task_code:
            return
        if code not in [item[0] for item in self._correction_task_items]:
            return
        self._save_current_correction_score()
        self._save_current_correction_comment()
        self._correction_task_code = code
        self._on_correction_task_switched()
        self._refresh_correction_nav_dropdowns()
        self._focus_first_input_field()

    def _correction_view_at_bottom(self) -> bool:
        """True if the preview shows its lower end - also when everything fits and nothing scrolls.

        Tk reports ``yview() == (0.0, 1.0)`` for content that fits, so one test covers
        both "scrolled to the very bottom" and "no scrolling at all".
        """
        return float(self._correction_canvas.yview()[1]) >= 1.0 - 1e-3

    def _go_to_correction_cursor(self, cursor: int) -> None:
        """Switch to the person at ``cursor`` (same task), cancelling any Supersymbol filter.

        The entries of the current person are saved before the cursor moves.
        Scrolling: the preview keeps its scroll position (Tk keeps the pixel origin,
        clamped to the new content) - unless it was at the bottom before the switch
        (incl. "everything visible"), then the new person's preview is scrolled to
        its bottom as well, so working through the last region of a task stays at
        the same place from person to person.
        """
        if not self._correction_mode_active or not self._correction_student_indices:
            return
        stick_to_bottom = self._correction_view_at_bottom()
        self._cancel_supersymbol_filter()
        self._save_current_correction_score()
        self._save_current_correction_comment()
        self._correction_cursor = cursor % len(self._correction_student_indices)
        self._student_cursor = self._correction_student_indices[self._correction_cursor]
        self._correction_selected_annotation_id = None
        self._refresh_active_student_label()
        self._refresh_correction_task_meta(load_saved_points=True)
        self._render_correction_preview()
        if stick_to_bottom:
            self._correction_canvas.yview_moveto(1.0)
        self._refresh_correction_completion_controls()
        self._refresh_correction_nav_dropdowns()
        self._focus_first_input_field()

    def _on_correction_task_picked(self, code: Hashable) -> None:
        """Task dropdown pick (user only)."""
        self._go_to_correction_task(str(code))

    def _on_correction_student_picked(self, student_id: Hashable) -> None:
        """Person dropdown pick (user only): move the cursor to that person."""
        if self._current_exam is None:
            return
        for cursor, index in enumerate(self._correction_student_indices):
            if self._current_exam.students[index].student_id == student_id:
                self._go_to_correction_cursor(cursor)
                return

    def _cycle_correction_task(self, delta: int) -> None:
        """↑/↓: previous/next (sub)task (4A -> 4B -> ... -> 5A), wrapping around."""
        if not self._correction_mode_active or not self._correction_task_items:
            return
        codes = [item[0] for item in self._correction_task_items]
        current = codes.index(self._correction_task_code) if self._correction_task_code in codes else 0
        self._go_to_correction_task(codes[(current + delta) % len(codes)])

    def _cycle_correction_main_task(self, delta: int) -> None:
        """Strg+↑/↓: first subtask of the next/previous main task (4B -> 5A; ↑ from 5B -> 4A), wrapping around."""
        if not self._correction_mode_active or not self._correction_task_items:
            return
        code, _max_points = self._selected_correction_task()
        codes = [item[0] for item in self._correction_task_items]
        mains = list(dict.fromkeys(main_task_of(item) for item in codes))
        current = mains.index(main_task_of(code)) if code is not None else 0
        target = mains[(current + delta) % len(mains)]
        self._go_to_correction_task(next(item for item in codes if main_task_of(item) == target))

    def _change_correction_student(self, delta: int) -> None:
        """←/→ and "◀ Person"/"Person ▶": next/previous person (same task), wrapping around."""
        if not self._correction_mode_active or not self._correction_student_indices:
            return
        self._go_to_correction_cursor(self._correction_cursor + delta)
