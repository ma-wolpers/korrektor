"""State and rules of the Scan-Werkstatt (Tk-free, unit-tested).

Page identity: every page is identified by its *original* 1-based page
number within the student's PDF. ``order`` lists those numbers in the new
order; rotation and deletion live in ``edits`` keyed by the original number,
so moving a page never loses its rotation or deletion mark. Positions
(``position``) are 1-based places within ``order``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace

from app.core.domain.models import StudentExam
from app.core.domain.page_geometry import normalize_rotation
from app.infrastructure.pdf.page_editing import PageEdit


@dataclass
class PdfEditState:
    """Pending edits of one student's PDF."""

    page_count: int
    order: list[int]
    edits: dict[int, PageEdit] = field(default_factory=dict)

    @classmethod
    def fresh(cls, page_count: int) -> "PdfEditState":
        """Unchanged state: pages 1..page_count in their original order."""
        return cls(page_count=page_count, order=list(range(1, page_count + 1)))

    def edit_for(self, original_page: int) -> PageEdit:
        return self.edits.get(original_page, PageEdit())

    def is_changed(self) -> bool:
        """True if the order differs or any page is rotated/deleted."""
        return self.order != list(range(1, self.page_count + 1)) or any(edit != PageEdit() for edit in self.edits.values())

    def kept_order(self) -> list[int]:
        """Original page numbers that remain, in the new order."""
        return [page for page in self.order if not self.edit_for(page).deleted]

    def page_mapping(self) -> dict[int, int | None]:
        """``{original page: new 1-based page number}``; deleted pages map to ``None``."""
        new_position = {page: index + 1 for index, page in enumerate(self.kept_order())}
        return {page: new_position.get(page) for page in range(1, self.page_count + 1)}


class ScanWorkshopSession:
    """Pending Scan-Werkstatt edits for all students of an exam.

    Students with an appended Auswertungsseite (`stats_report_appended`)
    are locked - by product decision the Werkstatt never moves that marker
    page; it has to be removed first (Auswertung → von der PDF entfernen).
    The crosshair is a fraction of the shown page (start: center) and stays
    where it was set across pages and students until the next click.
    """

    def __init__(self, students: Sequence[StudentExam]) -> None:
        self.pdfs = [student.pdf_filename for student in students]
        self.display_names = {student.pdf_filename: student.display_name for student in students}
        self.locked = {student.pdf_filename for student in students if student.stats_report_appended}
        self.states = {student.pdf_filename: PdfEditState.fresh(student.page_count) for student in students}
        self.student_index = 0
        self.position = 1
        self.crosshair = (0.5, 0.5)

    @property
    def current_pdf(self) -> str:
        return self.pdfs[self.student_index]

    @property
    def current_state(self) -> PdfEditState:
        return self.states[self.current_pdf]

    @property
    def current_original_page(self) -> int:
        """Original page number shown at the current position."""
        return self.current_state.order[self.position - 1]

    @property
    def current_edit(self) -> PageEdit:
        return self.current_state.edit_for(self.current_original_page)

    def is_current_locked(self) -> bool:
        return self.current_pdf in self.locked

    def go_student(self, delta: int) -> bool:
        """Previous/next student (no wrap-around); the position is kept where possible."""
        index = self.student_index + delta
        if not 0 <= index < len(self.pdfs):
            return False
        self.student_index = index
        self.position = min(self.position, len(self.current_state.order))
        return True

    def go_page(self, delta: int) -> bool:
        """Previous/next position within the current PDF (no wrap-around)."""
        position = self.position + delta
        if not 1 <= position <= len(self.current_state.order):
            return False
        self.position = position
        return True

    def move_page(self, delta: int) -> bool:
        """Strg+↑/↓: move the current page by ``delta`` places (take out, insert); the view follows the page."""
        state = self.current_state
        target = self.position + delta
        if self.is_current_locked() or not 1 <= target <= len(state.order):
            return False
        page = state.order.pop(self.position - 1)
        state.order.insert(target - 1, page)
        self.position = target
        return True

    def toggle_delete(self) -> bool:
        """Entf: mark/unmark the current page as deleted (it stays visible, greyed out, until applied)."""
        return self._update_edit(lambda edit: replace(edit, deleted=not edit.deleted))

    def rotate_by(self, degrees: float) -> bool:
        """Strg+←/→ (fine step) or the ±buttons: add a clockwise rotation."""
        return self._update_edit(lambda edit: replace(edit, rotation_deg=normalize_rotation(edit.rotation_deg + degrees)))

    def rotate_quarter(self, direction: int) -> bool:
        """Strg+Shift+←/→: rotate by 90° (``direction`` +1 clockwise, -1 counter-clockwise)."""
        return self.rotate_by(90.0 * direction)

    def set_rotation(self, degrees: float) -> bool:
        """Degree field: set the absolute clockwise rotation of the current page."""
        return self._update_edit(lambda edit: replace(edit, rotation_deg=normalize_rotation(degrees)))

    def set_crosshair(self, fraction_x: float, fraction_y: float) -> None:
        """Place the crosshair (fractions of the page, clamped to 0..1)."""
        self.crosshair = (min(max(fraction_x, 0.0), 1.0), min(max(fraction_y, 0.0), 1.0))

    def changed_pdfs(self) -> list[str]:
        """Students with pending edits, in exam order."""
        return [pdf for pdf in self.pdfs if self.states[pdf].is_changed()]

    def discard(self) -> None:
        """Drop every pending edit (crosshair and position stay)."""
        for pdf, state in self.states.items():
            self.states[pdf] = PdfEditState.fresh(state.page_count)
        self.position = min(self.position, len(self.current_state.order))

    def _update_edit(self, change) -> bool:
        if self.is_current_locked():
            return False
        state = self.current_state
        page = self.current_original_page
        new_edit = change(state.edit_for(page))
        if new_edit == PageEdit():
            state.edits.pop(page, None)
        else:
            state.edits[page] = new_edit
        return True
