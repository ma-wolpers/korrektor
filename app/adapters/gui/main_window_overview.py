from __future__ import annotations

from pathlib import Path
from typing import Iterable

from app.adapters.gui.view_models import ExamOverviewRow
from app.core.domain.models import ExamProject
from app.core.domain.progress import ProgressCalculator

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui


class MainWindowOverviewMixin:
    def _initial_load(self) -> None:
        if self._controller:
            self._controller.refresh_exam_overview()

    def render_overview_rows(self, rows: list[ExamOverviewRow]) -> None:
        self._rows_by_tree_id.clear()
        for item in self._tree.get_children():
            self._tree.delete(item)

        for row in rows:
            tree_id = self._tree.insert(
                "",
                ui.END,
                values=(
                    row.exam_name,
                    f"{row.reading_percent:.0f}",
                    f"{row.correction_percent:.0f}",
                    row.region_count,
                    row.corrected_region_count,
                    "Ja" if row.reading_complete else "Nein",
                    "Ja" if row.has_open_flags else "Nein",
                ),
            )
            self._rows_by_tree_id[tree_id] = row

        children = self._tree.get_children()
        if children:
            self._tree.selection_set(children[0])
            self._tree.focus(children[0])

        self._status_var.set(f"{len(rows)} Klausuren geladen")

    def get_selected_row(self) -> ExamOverviewRow | None:
        selection = self._tree.selection()
        if selection:
            return self._rows_by_tree_id.get(selection[0])
        children = self._tree.get_children()
        if not children:
            return None
        first = children[0]
        self._tree.selection_set(first)
        self._tree.focus(first)
        return self._rows_by_tree_id.get(first)

    def open_exam_detail(self, exam: ExamProject, exam_file: Path) -> None:
        """Show the Klausur-Detail view for `exam`, resetting all mode state."""
        self._detail_exam_file = exam_file
        self._current_exam = exam
        self._student_cursor = 0
        self._reading_active = False
        self._reading_student_cursor = 0
        self._reading_page = 1
        self._superpage_var.set(False)
        self._extra_mode_active = False
        self._extra_sequence = []
        self._extra_cursor = 0
        self._naming_mode_active = False
        self._naming_capture_active = False
        self._naming_cursor = 0
        self._pending_student_names.clear()
        self._correction_mode_active = False
        self._correction_student_indices = []
        self._correction_cursor = 0

        self._refresh_correction_area_choices(exam)
        self._apply_detail_labels(exam)
        self._status_var.set(f"Detailansicht: {exam.exam_name}")
        self._reading_info_var.set("Einlesemodus: bereit")
        self._reading_canvas.delete("all")
        self._draft_regions.clear()
        self._hide_correction_controls()
        self._close_extra_popup()
        self._selected_region_id = None
        self._selected_region_kind = None
        self._clear_pending_redraw()
        self._refresh_region_tree()
        self._show_detail_mode()

    def on_exam_deleted(self, exam_id: str) -> None:
        if self._current_exam is None:
            return
        if self._current_exam.exam_id != exam_id:
            return
        self._return_to_overview()

    def on_exam_index_dir_changed(self, index_root: Path) -> None:
        self._exam_index_dir_value = str(index_root)
        self._return_to_overview()

    def sync_current_exam_from_repository(self) -> None:
        if self._current_exam is None:
            return

        exam_file = self.deps.exam_repository.index_root / f"{self._current_exam.exam_id}.json"
        if not exam_file.exists():
            self._return_to_overview()
            return

        exam = self.deps.exam_repository.load_exam(exam_file)
        self.open_exam_detail(exam, exam_file)

    def _apply_detail_labels(self, exam: ExamProject) -> None:
        progress = ProgressCalculator().compute(exam)

        self._detail_name.set(f"Name: {exam.exam_name}")
        self._detail_pages.set(f"Standardseiten: {exam.standard_page_count}")
        self._detail_students.set(f"Schüler:innen: {len(exam.students)}")
        self._detail_regions.set(f"Fertig korrigiert {progress.fully_finished_area_count}/{progress.total_area_count}")
        flags = []
        if progress.has_unassigned_extra_pages:
            flags.append("Extraseiten offen")
        if progress.has_missing_page_markings:
            flags.append("Seitenmarkierung fehlt")
        self._detail_status.set("Status: " + (", ".join(flags) if flags else "Keine offenen Warnungen"))
        self._refresh_active_student_label()

    def set_status(self, text: str) -> None:
        self._status_var.set(text)

    def invalidate_doc_cache(self, pdf_filenames: Iterable[str]) -> None:
        """Close and evict cached PDF documents for the given filenames.

        Must run before any filesystem rename of these files (Windows locks
        open file handles) and again before replaying a rename on undo/redo,
        so a stale, still-open `fitz.Document` is never left pointing at a
        path that no longer exists.
        """
        for filename in pdf_filenames:
            document = self._doc_cache.pop(filename, None)
            if document is not None:
                try:
                    document.close()
                except Exception:
                    pass

    def _refresh_active_student_label(self) -> None:
        if self._active_view not in {"reading", "correction"}:
            self._active_student.set("Aktive Person: -")
            return

        if not self._current_exam or not self._current_exam.students:
            self._active_student.set("Aktive Person: -")
            return

        if self._correction_mode_active and self._correction_student_indices:
            idx = self._correction_student_indices[self._correction_cursor]
            student = self._current_exam.students[idx]
            self._active_student.set(
                f"Aktive Person: {student.display_name} ({self._correction_cursor + 1}/{len(self._correction_student_indices)}) | Bereich {self._correction_area_var.get()}"
            )
            return

        if not self._reading_active and not self._extra_mode_active:
            self._active_student.set("Aktive Person: -")
            return

        if self._extra_mode_active and self._extra_sequence:
            student_index, _page_number = self._extra_sequence[self._extra_cursor]
            student = self._current_exam.students[student_index]
            self._active_student.set(
                f"Aktive Person: {student.display_name} ({self._extra_cursor + 1}/{len(self._extra_sequence)})"
            )
            return

        student = self._current_exam.students[self._reading_student_cursor]
        self._active_student.set(
            f"Aktive Person: {student.display_name} ({self._reading_student_cursor + 1}/{len(self._current_exam.students)})"
        )

    def _move_student(self, delta: int) -> None:
        if not self._current_exam or not self._current_exam.students:
            return
        self._commit_points_if_possible()
        if self._correction_mode_active and self._correction_student_indices:
            self._change_correction_student(delta)
            return
        self._student_cursor = (self._student_cursor + delta) % len(self._current_exam.students)
        self._refresh_active_student_label()
        self._focus_first_input_field()
