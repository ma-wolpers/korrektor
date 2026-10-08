from __future__ import annotations

import fitz

from app.adapters.gui.dialog_services import messagebox
from app.core.domain.models import StudentExam

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui

_MARGIN = 16


class MainWindowNamingCaptureMixin:
    """Rendering and interaction of both stages of the naming window (see `MainWindowNamingMixin`).

    Coordinates: the name field (``exam.name_region``) is stored in PDF
    points of the visible page with origin top-left - the same convention as
    the former Zuschnitt-based Namenmodus. The canvas shows the page with its
    top-left corner at canvas (0, 0) and ``view.scale`` pixels per point.
    """

    # --- stage 1: Namensfeld festlegen -------------------------------------------------

    def _naming_max_page(self) -> int:
        return max((student.page_count for student in self._current_exam.students), default=1)

    def _change_naming_page(self, delta: int) -> None:
        view = self._naming_window_view
        if view is None or view.stage != "region":
            return
        new_page = view.page + delta
        if 1 <= new_page <= self._naming_max_page():
            view.page = new_page
            self._render_naming_region_stage()

    def _canvas_target_size(self, view) -> tuple[float, float]:
        width = int(view.canvas.winfo_width())
        height = int(view.canvas.winfo_height())
        if width < 50 or height < 50:
            return 700.0, 760.0
        return float(width - _MARGIN), float(height - _MARGIN)

    def _render_naming_region_stage(self) -> None:
        """Superseite of the current page, fitted into the canvas, with the name field drawn on top."""
        view = self._naming_window_view
        exam = self._current_exam
        max_width, max_height = self._canvas_target_size(view)
        result = self._build_superposed_pixmap(students=exam.students, page_number=view.page, target_width=max_width)
        if result is not None and result[0].height > max_height:
            result = self._build_superposed_pixmap(
                students=exam.students, page_number=view.page, target_width=max_width * max_height / result[0].height
            )
        view.canvas.delete("all")
        if result is None:
            view.info_var.set(f"Seite {view.page} kann nicht dargestellt werden")
            return
        pix, rect = result[0], result[1]
        view.scale = pix.width / max(rect.width, 1.0)
        view.photo = ui.PhotoImage(data=pix.tobytes("ppm"), format="ppm")
        view.canvas.create_image(0, 0, anchor=ui.NW, image=view.photo)
        region = exam.name_region
        if region is not None and exam.name_region_page == view.page:
            view.canvas.create_rectangle(
                region.x0 * view.scale, region.y0 * view.scale, region.x1 * view.scale, region.y1 * view.scale,
                outline="#8b5cf6", width=3,
            )
        view.info_var.set(f"Namensfeld festlegen · Superseite {view.page}/{self._naming_max_page()} · Bereich über die Namen ziehen")
        view.hint_var.set(
            f"Namensfeld gesetzt (Seite {exam.name_region_page})." if region is not None else "Noch kein Namensfeld gezogen."
        )

    def _on_naming_canvas_press(self, event) -> None:
        view = self._naming_window_view
        if view is None or view.stage != "region":
            return
        view.drag_start = (float(event.x), float(event.y))
        view.drag_rect = view.canvas.create_rectangle(event.x, event.y, event.x, event.y, outline="#8b5cf6", width=2, dash=(4, 2))

    def _on_naming_canvas_drag(self, event) -> None:
        view = self._naming_window_view
        if view is None or view.drag_start is None or view.drag_rect is None:
            return
        x0, y0 = view.drag_start
        view.canvas.coords(view.drag_rect, x0, y0, event.x, event.y)

    def _on_naming_canvas_release(self, event) -> None:
        """Persist the dragged name field (PDF points) and warn about pages with other geometry."""
        view = self._naming_window_view
        if view is None or view.drag_start is None or self._controller is None:
            return
        x0, y0 = view.drag_start
        view.drag_start = None
        x1, y1 = float(event.x), float(event.y)
        if abs(x1 - x0) < 4 or abs(y1 - y0) < 4:
            self._render_naming_region_stage()
            return
        box = tuple(value / view.scale for value in (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)))
        updated = self._controller.set_name_region_immediate(exam=self._current_exam, box=box, page_number=view.page)
        self._current_exam = updated
        self._render_naming_region_stage()
        mismatched = self._check_name_region_geometry(updated, view.page)
        if mismatched:
            messagebox.showwarning(
                "Abweichende Seitengröße",
                "Das Namensfeld liegt bei folgenden Personen möglicherweise an anderer Stelle "
                "(abweichende Seitengröße/Rotation):\n" + ", ".join(mismatched),
                parent=view.popup,
            )

    # --- stage 2: Namen erfassen ---------------------------------------------------------

    def _current_naming_student(self) -> StudentExam | None:
        view = self._naming_window_view
        if view is None or self._current_exam is None or not self._current_exam.students:
            return None
        return self._current_exam.students[view.cursor]

    def _load_naming_field(self) -> None:
        view = self._naming_window_view
        student = self._current_naming_student()
        if view is not None and student is not None:
            view.name_var.set(self._pending_student_names.get(student.student_id, ""))

    def _focus_naming_entry(self) -> None:
        view = self._naming_window_view
        if view is None:
            return
        try:
            view.name_entry.focus_set()
            view.name_entry.selection_range(0, ui.END)
        except Exception:
            pass

    def _commit_naming_field_if_possible(self, view=None) -> None:
        """Store the typed name in memory (persisted only by "Alle umbenennen")."""
        view = view or self._naming_window_view
        if view is None or view.stage != "capture" or self._current_exam is None or not self._current_exam.students:
            return
        student = self._current_exam.students[view.cursor]
        name = view.name_var.get().strip()
        if name:
            self._pending_student_names[student.student_id] = name
        else:
            self._pending_student_names.pop(student.student_id, None)
        if self._naming_window_view is view:
            self._refresh_naming_progress()

    def _change_naming_student(self, delta: int) -> None:
        """←/→: take the typed name, move to the previous/next student (wraps around)."""
        view = self._naming_window_view
        if view is None or view.stage != "capture":
            return
        self._commit_naming_field_if_possible()
        view.cursor = (view.cursor + delta) % len(self._current_exam.students)
        self._load_naming_field()
        self._render_naming_capture_page()
        self._focus_naming_entry()

    def _commit_and_next_naming_student(self) -> None:
        """Enter: take the name and go to the next student."""
        self._change_naming_student(1)

    def _render_naming_capture_page(self) -> None:
        """The current student's page, cropped to the shared name field and fitted to the canvas."""
        view = self._naming_window_view
        exam = self._current_exam
        student = self._current_naming_student()
        if view is None or student is None or exam.name_region is None:
            return
        view.canvas.delete("all")
        try:
            page = self._naming_document(student.pdf_filename).load_page(exam.name_region_page - 1)
            region = exam.name_region
            clip = fitz.Rect(region.x0, region.y0, region.x1, region.y1).intersect(page.rect)
            if clip.is_empty:
                clip = page.rect
            max_width, max_height = self._canvas_target_size(view)
            scale = min(max_width / max(clip.width, 1.0), max_height / max(clip.height, 1.0))
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=clip, alpha=False)
        except Exception as exc:
            view.info_var.set(f"{student.display_name}: Namensfeld kann nicht dargestellt werden ({exc})")
            return
        view.photo = ui.PhotoImage(data=pix.tobytes("ppm"), format="ppm")
        view.canvas.create_image(0, 0, anchor=ui.NW, image=view.photo)
        view.info_var.set(f"Namen erfassen · {student.display_name} ({view.cursor + 1}/{len(exam.students)})")
        self._refresh_naming_progress()

    def _refresh_naming_progress(self) -> None:
        """"N/M Namen erfasst"; "Alle umbenennen" only once every student has a name."""
        view = self._naming_window_view
        if view is None or self._current_exam is None:
            return
        students = self._current_exam.students
        done = sum(1 for student in students if self._pending_student_names.get(student.student_id, "").strip())
        view.progress_var.set(f"{done}/{len(students)} Namen erfasst · ←/→ Person · Enter übernimmt und springt weiter")
        view.rename_button.configure(state="normal" if students and done == len(students) else "disabled")

    def _rename_all_students(self) -> None:
        """Rename every student (file + display name) via the existing rollback-safe batch rename."""
        view = self._naming_window_view
        if self._current_exam is None or self._controller is None or view is None:
            return
        self._commit_naming_field_if_possible()
        missing = [
            student.display_name or student.student_id
            for student in self._current_exam.students
            if not self._pending_student_names.get(student.student_id, "").strip()
        ]
        if missing:
            messagebox.showinfo("Hinweis", "Noch kein Name erfasst für: " + ", ".join(missing), parent=view.popup)
            return
        updated = self._controller.rename_students_immediate(exam=self._current_exam, name_by_student_id=dict(self._pending_student_names))
        if updated is None:
            return
        self._current_exam = updated
        self._pending_student_names.clear()
        self._apply_detail_labels(updated)
        self._load_naming_field()
        self._render_naming_capture_page()
