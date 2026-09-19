from __future__ import annotations

from typing import Sequence

from app.adapters.gui.dialog_services import messagebox
from app.core.domain.models import StudentExam

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui


class MainWindowReadingMixin:
    def _start_reading_mode(self) -> None:
        """Enter Einlesemodus, resetting any active extra/naming/correction mode."""
        if not self._current_exam or not self._current_exam.students:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Klausur öffnen.")
            return
        self._stop_correction_mode(silent=True)
        self._extra_mode_active = False
        self._naming_mode_active = False
        self._naming_capture_active = False
        self._reading_active = True
        self._reading_student_cursor = 0
        self._reading_page = 1
        self._selected_region_id = None
        self._selected_region_kind = None
        self._set_detail_submode("reading")
        self._show_view("reading")
        self._refresh_region_tree()
        self._render_current_reading_page()
        self._status_var.set("Einlesemodus aktiv")

    def _change_reading_student(self, delta: int) -> None:
        if not self._reading_active or not self._current_exam or not self._current_exam.students:
            return
        self._reading_student_cursor = (self._reading_student_cursor + delta) % len(self._current_exam.students)
        if not bool(self._superpage_var.get()):
            student = self._current_exam.students[self._reading_student_cursor]
            self._reading_page = min(self._reading_page, max(student.page_count, 1))
        self._render_current_reading_page()

    def _change_reading_page(self, delta: int) -> None:
        if not self._reading_active:
            return
        new_page = self._reading_page + delta
        if bool(self._superpage_var.get()):
            max_page = self._max_available_page()
        else:
            student = self._get_reading_student()
            if student is None:
                return
            max_page = max(student.page_count, 1)
        self._reading_page = max(1, min(max_page, new_page))
        self._render_current_reading_page()

    def _get_reading_student(self) -> StudentExam | None:
        if not self._current_exam or not self._current_exam.students:
            return None
        return self._current_exam.students[self._reading_student_cursor]

    def _render_current_reading_page(self) -> None:
        student = self._get_reading_student()
        if student is None or self._current_exam is None:
            return

        if bool(self._superpage_var.get()):
            used = self._render_superposed_page(students=self._current_exam.students, page_number=self._reading_page)
            max_page = self._max_available_page()
            if used > 0:
                self._reading_info_var.set(
                    f"Superseite | Seite {self._reading_page}/{max_page} | Quellen: {used}"
                )
            return

        self._render_pdf_page(student=student, page_number=self._reading_page)

        extra_marker = " (Extraseite)" if self._reading_page > self._current_exam.standard_page_count else ""
        self._reading_info_var.set(
            f"{student.display_name} | Seite {self._reading_page}/{student.page_count}{extra_marker}"
        )

    def _on_superpage_toggle(self) -> None:
        if not self._reading_active:
            self._superpage_var.set(False)
            return
        if bool(self._superpage_var.get()):
            self._reading_page = min(self._reading_page, self._max_available_page())
            self._status_var.set("Superseite aktiv")
        else:
            student = self._get_reading_student()
            if student is not None:
                self._reading_page = min(self._reading_page, max(student.page_count, 1))
            self._status_var.set("Superseite aus")
        self._render_current_reading_page()

    def _max_available_page(self) -> int:
        if self._current_exam is None or not self._current_exam.students:
            return 1
        return max(max(student.page_count, 1) for student in self._current_exam.students)

    def _render_superposed_page(self, *, students: Sequence[StudentExam], page_number: int) -> int:
        """Render the Superseite composite onto the reading canvas (Einlesemodus/Namenmodus)."""
        built = self._build_superposed_pixmap(students=students, page_number=page_number)
        if built is None:
            self._reading_canvas.delete("all")
            self._reading_info_var.set("Superseite: Keine renderbaren Seiten vorhanden")
            return 0
        pixmap, reference_rect, source_count = built

        pgm_header = f"P5 {pixmap.width} {pixmap.height} 255\n".encode("ascii")
        self._render_photo = ui.PhotoImage(data=pgm_header + pixmap.samples, format="ppm")

        self._x_factor = reference_rect.width / max(pixmap.width, 1)
        self._y_factor = reference_rect.height / max(pixmap.height, 1)
        self._reading_canvas.configure(width=pixmap.width, height=pixmap.height)
        self._reading_canvas.delete("all")
        self._canvas_image_id = self._reading_canvas.create_image(0, 0, anchor=ui.NW, image=self._render_photo)
        self._reading_canvas.configure(scrollregion=(0, 0, pixmap.width, pixmap.height))
        self._draw_existing_regions("", page_number)
        return source_count

    def _focus_reading_task_input(self) -> None:
        """Move focus into the Aufgaben/Punkte editor after a region is drawn."""
        if self._assignment_mode_var.get() == "form":
            self._form_tasks_text.focus_set()
        else:
            self._quick_tasks_entry.focus_set()
            self._quick_tasks_entry.selection_range(0, ui.END)

    def _next_area_label(self) -> str:
        """Return the first area-code label not already used by a region or draft.

        Collision-safe by construction: scans the labels actually in use
        (committed regions and open standard drafts) instead of deriving a
        label purely from a count, which broke whenever the count and the
        real labels in use fell out of sync (the root cause of duplicate
        `assigned_area_codes` collapsing regions in Korrekturmodus).
        """
        if self._current_exam is None:
            return "A"
        if self._extra_mode_active:
            existing = self._existing_standard_areas()
            return existing[0] if existing else "A"
        used = {
            region.assigned_area_codes[0].strip().upper()
            for region in self._current_exam.regions
            if region.assigned_area_codes and region.assigned_area_codes[0].strip()
        }
        used.update(
            draft.area_codes[0].strip().upper()
            for draft in self._draft_regions.values()
            if draft.student_pdf == "" and draft.area_codes and draft.area_codes[0].strip()
        )
        index = 0
        while self._index_to_area_label(index) in used:
            index += 1
        return self._index_to_area_label(index)

    def _finish_reading_mode(self) -> None:
        """Mark Einlesemodus complete for the current exam and leave the reading view."""
        if not self._current_exam or not self._controller:
            return
        updated = self._controller.finish_reading_mode(exam=self._current_exam)
        self._current_exam = updated
        self._apply_detail_labels(updated)
        self._reading_active = False
        self._naming_mode_active = False
        self._naming_capture_active = False
        self._reading_info_var.set("Einlesemodus: abgeschlossen")
        self._show_detail_mode()
