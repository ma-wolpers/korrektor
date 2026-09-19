from __future__ import annotations

from pathlib import Path

import fitz

from app.adapters.gui.dialog_services import messagebox
from app.core.domain.models import ExamProject, StudentExam

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui


class MainWindowNamingMixin:
    def _start_naming_mode(self) -> None:
        """Enter Namenmodus: region-definition sub-step (reuses the reading canvas)."""
        if not self._current_exam or not self._current_exam.students:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Klausur öffnen.")
            return
        self._stop_correction_mode(silent=True)
        self._extra_mode_active = False
        self._naming_mode_active = True
        self._naming_capture_active = False
        self._reading_active = True
        self._reading_student_cursor = 0
        self._reading_page = self._current_exam.name_region_page if self._current_exam.name_region else 1
        self._selected_region_id = None
        self._selected_region_kind = None
        self._superpage_var.set(True)
        self._set_detail_submode("naming")
        self._show_view("reading")
        self._refresh_naming_region_hint()
        self._render_current_reading_page()
        self._status_var.set("Namenmodus aktiv - Namensbereich ziehen oder anpassen")

    def _refresh_naming_region_hint(self) -> None:
        """Update the region-definition hint and gate the "Namen erfassen" button."""
        exam = self._current_exam
        if exam is not None and exam.name_region is not None:
            self._naming_region_hint_var.set(f"Namensbereich gesetzt (Seite {exam.name_region_page}).")
            self._naming_enter_capture_button.configure(state="normal")
        else:
            self._naming_region_hint_var.set("Noch kein Namensbereich gezogen - Bereich ueber den Namen ziehen.")
            self._naming_enter_capture_button.configure(state="disabled")

    def _check_name_region_geometry(self, exam: ExamProject, page_number: int) -> list[str]:
        """Report students whose page geometry at `page_number` differs from the first.

        `name_region` assumes every student's PDF has the same page size and
        rotation at `page_number`; this only detects and reports a mismatch
        (purely informational) - it does not normalize or exclude anything.
        """
        folder = Path(exam.folder_path)
        reference_rect: fitz.Rect | None = None
        reference_rotation: int | None = None
        mismatched: list[str] = []
        for student in exam.students:
            if page_number > student.page_count:
                continue
            pdf_path = folder / student.pdf_filename
            if not pdf_path.exists():
                continue
            document = self._doc_cache.get(student.pdf_filename)
            if document is None:
                try:
                    document = fitz.open(pdf_path)
                except Exception:
                    continue
                self._doc_cache[student.pdf_filename] = document
            try:
                page = document.load_page(page_number - 1)
            except Exception:
                continue
            rect = page.rect
            rotation = int(page.rotation)
            if reference_rect is None or reference_rotation is None:
                reference_rect = rect
                reference_rotation = rotation
                continue
            size_matches = abs(rect.width - reference_rect.width) <= 1.0 and abs(rect.height - reference_rect.height) <= 1.0
            if not size_matches or rotation != reference_rotation:
                mismatched.append(student.display_name or student.student_id)
        return mismatched

    def _commit_name_region_from_drag(self, *, box: tuple[float, float, float, float], page_number: int) -> None:
        """Persist a freshly dragged Namenmodus region and warn on geometry mismatches."""
        self._reading_canvas.delete(self._drag_rect_id)
        self._drag_rect_id = None
        self._drag_start = None
        if self._current_exam is None or self._controller is None:
            return
        updated = self._controller.set_name_region_immediate(
            exam=self._current_exam,
            box=box,
            page_number=page_number,
        )
        self._current_exam = updated
        self._refresh_naming_region_hint()
        self._rerender_active_page()
        mismatched = self._check_name_region_geometry(updated, page_number)
        if mismatched:
            messagebox.showwarning(
                "Abweichende Seitengroesse",
                "Der Namensbereich liegt bei folgenden Personen moeglicherweise an anderer "
                "Stelle (abweichende Seitengroesse/Rotation):\n" + ", ".join(mismatched),
            )

    def _enter_naming_capture(self) -> None:
        """Switch from region-definition to the per-student naming walk."""
        if self._current_exam is None or self._current_exam.name_region is None:
            messagebox.showinfo("Hinweis", "Bitte zuerst einen Namensbereich ziehen.")
            return
        self._naming_capture_active = True
        self._reading_active = False
        self._naming_cursor = 0
        self._set_detail_submode("naming")
        self._render_naming_capture_page()
        self._refresh_naming_progress()
        self._focus_naming_entry()
        self._status_var.set("Namenserfassung aktiv")

    def _exit_naming_capture(self) -> None:
        """Return from the naming walk to region-definition (e.g. to re-align)."""
        self._commit_naming_field_if_possible()
        self._naming_capture_active = False
        self._reading_active = True
        self._set_detail_submode("naming")
        self._refresh_naming_region_hint()
        self._render_current_reading_page()
        self._status_var.set("Namenmodus aktiv - Namensbereich ziehen oder anpassen")

    def _change_naming_student(self, delta: int) -> None:
        """Commit the current name, move to the next/previous student, refocus the entry."""
        if not self._naming_capture_active or not self._current_exam or not self._current_exam.students:
            return
        self._commit_naming_field_if_possible()
        self._naming_cursor = (self._naming_cursor + delta) % len(self._current_exam.students)
        self._render_naming_capture_page()
        self._refresh_naming_progress()
        self._focus_naming_entry()

    def _current_naming_student(self) -> StudentExam | None:
        """Return the student currently shown in the naming-capture walk."""
        if not self._current_exam or not self._current_exam.students:
            return None
        return self._current_exam.students[self._naming_cursor]

    def _focus_naming_entry(self) -> None:
        """Move focus into the name entry with its content fully selected."""
        self._naming_entry.focus_set()
        self._naming_entry.selection_range(0, ui.END)

    def _render_naming_capture_page(self) -> None:
        """Render the current student's PDF cropped to the shared name_region."""
        exam = self._current_exam
        student = self._current_naming_student()
        if exam is None or student is None or exam.name_region is None:
            return
        self._naming_name_var.set(self._pending_student_names.get(student.student_id, ""))

        pdf_path = Path(exam.folder_path) / student.pdf_filename
        if not pdf_path.exists():
            self._reading_canvas.delete("all")
            self._reading_info_var.set(f"Datei fehlt: {student.pdf_filename}")
            return

        document = self._doc_cache.get(student.pdf_filename)
        if document is None:
            try:
                document = fitz.open(pdf_path)
            except Exception as exc:
                self._reading_canvas.delete("all")
                self._reading_info_var.set(f"Fehler beim PDF-Rendering: {exc}")
                return
            self._doc_cache[student.pdf_filename] = document

        page_index = exam.name_region_page - 1
        if page_index < 0 or page_index >= document.page_count:
            self._reading_canvas.delete("all")
            self._reading_info_var.set(f"Namensseite {exam.name_region_page} existiert nicht in {student.pdf_filename}")
            return

        try:
            page = document.load_page(page_index)
            clip = fitz.Rect(exam.name_region.x0, exam.name_region.y0, exam.name_region.x1, exam.name_region.y1)
            clip = clip.intersect(page.rect)
            if clip.is_empty:
                clip = page.rect
            target_width = 480.0
            scale = target_width / max(clip.width, 1.0)
            try:
                pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=clip, alpha=False)
            except TypeError:
                pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=clip)
        except Exception as exc:
            self._reading_canvas.delete("all")
            self._reading_info_var.set(f"Fehler beim PDF-Rendering: {exc}")
            return

        self._render_photo = ui.PhotoImage(data=pix.tobytes("ppm"), format="ppm")
        self._reading_canvas.configure(width=pix.width, height=pix.height)
        self._reading_canvas.delete("all")
        self._canvas_image_id = self._reading_canvas.create_image(0, 0, anchor=ui.NW, image=self._render_photo)
        self._reading_canvas.configure(scrollregion=(0, 0, pix.width, pix.height))
        self._reading_info_var.set(
            f"{student.display_name} ({self._naming_cursor + 1}/{len(exam.students)})"
        )

    def _refresh_naming_progress(self) -> None:
        """Update the "N/M Namen erfasst" label and gate the rename-all button."""
        exam = self._current_exam
        if exam is None:
            self._naming_progress_var.set("")
            self._naming_rename_all_button.configure(state="disabled")
            return
        done = sum(1 for student in exam.students if self._pending_student_names.get(student.student_id, "").strip())
        total = len(exam.students)
        self._naming_progress_var.set(f"{done}/{total} Namen erfasst")
        self._naming_rename_all_button.configure(state="normal" if done == total and total > 0 else "disabled")

    def _commit_naming_field_if_possible(self) -> None:
        """Store the currently typed name in-memory (no persistence/history entry yet)."""
        student = self._current_naming_student()
        if student is None:
            return
        name = self._naming_name_var.get().strip()
        if name:
            self._pending_student_names[student.student_id] = name
        else:
            self._pending_student_names.pop(student.student_id, None)
        self._refresh_naming_progress()

    def _on_naming_fields_focus_out(self, _event: ui.Event[ui.Misc]) -> None:
        """Commit the pending name when the entry loses focus."""
        self._commit_naming_field_if_possible()

    def _on_naming_fields_commit(self, _event: ui.Event[ui.Misc]) -> None:
        """Commit the pending name on <Return> and leave the field."""
        self._commit_naming_field_if_possible()
        self.root.focus_set()

    def _on_naming_fields_escape(self, _event: ui.Event[ui.Misc]) -> None:
        """Leave the name entry on <Escape> without a direct commit.

        No commit call here: leaving the field triggers <FocusOut>, which is
        the single commit path (see _commit_naming_field_if_possible).
        """
        self.root.focus_set()

    def _rename_all_students(self) -> None:
        """Trigger the batch rename once every student has a pending name."""
        if self._current_exam is None or self._controller is None:
            return
        self._commit_naming_field_if_possible()
        missing = [
            student.display_name or student.student_id
            for student in self._current_exam.students
            if not self._pending_student_names.get(student.student_id, "").strip()
        ]
        if missing:
            messagebox.showinfo("Hinweis", "Noch kein Name erfasst fuer: " + ", ".join(missing))
            return
        updated = self._controller.rename_students_immediate(
            exam=self._current_exam,
            name_by_student_id=dict(self._pending_student_names),
        )
        if updated is None:
            return
        self._current_exam = updated
        self._pending_student_names.clear()
        self._apply_detail_labels(updated)
        self._render_naming_capture_page()
        self._refresh_naming_progress()
