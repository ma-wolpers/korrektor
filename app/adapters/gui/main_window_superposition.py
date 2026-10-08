"""Punkte-/Noten-Superposition im Korrekturmodus (Mixin).

Start der Punkte- bzw. Noten-Superposition, Vorschau mit Seitenblaettern und Einfuegen an
der angeklickten Position. Aus main_window_supersymbol.py ausgelagert (Dateigroessen-Regel);
Methodenruempfe unveraendert."""

from __future__ import annotations


import fitz

from app.adapters.gui.dialog_services import messagebox

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui


class MainWindowSuperpositionMixin:
    """Punkte-/Noten-Superposition im Korrekturmodus (Mixin)."""

    def _start_scored_superposition(self) -> None:
        self._start_superposition_preview(mode="scored")

    def _start_grade_superposition(self) -> None:
        if self._current_exam is not None and self._current_exam.grading_scale_snapshot is None:
            messagebox.showinfo("Hinweis", "Bitte dieser Klausur zuerst einen Notenschlüssel zuordnen.")
            return
        self._start_superposition_preview(mode="grade")

    def _start_superposition_preview(self, *, mode: str) -> None:
        """Show the Superseite for every current-Bereich Korrektur-Schueler:in, ready for a placing click.

        Target set is always "all correction students of the active
        Bereich" (`self._correction_student_indices`, same set
        "Durchdruecken" uses) - unlike Supersymbol, a Superposition has no
        filter condition to narrow it down.

        The two modes intentionally source their task/page/clip data
        differently, per the Korrektor-Wunschliste:
        - "scored" always uses the single task currently selected in the
          Punkte-Formular (`_selected_correction_task()`), independent of
          the Supersymbol-Filter's own "Aufgabe(n)"-Auswahl (that field is
          for the filter's target population, not for what a Superposition
          inserts - the previous shared use of it was an accidental
          coupling). The preview is cropped to the current Bereich's box
          (`clip`), and stays tied to the Bereich's page.
        - "grade" is unchanged: `task_codes` no longer influences the
          Notenwert at all (`apply_grade_superposition_immediate` computes
          it exam-weit), the preview shows the whole page, and
          `self._superposition_page_number` lets the teacher navigate to
          any page of the exam via `_change_superposition_page`,
          independent of the Bereich.
        """
        if self._current_exam is None or self._controller is None:
            return
        template = self._current_correction_template()
        if template is None:
            messagebox.showinfo("Hinweis", "Bitte zuerst einen Bereich wählen.")
            return
        target_students = [self._current_exam.students[index] for index in self._correction_student_indices]
        if not target_students:
            return

        clip: fitz.Rect | None = None
        if mode == "scored":
            task_code, max_points = self._selected_correction_task()
            if task_code is None:
                messagebox.showinfo("Hinweis", "Bitte zuerst eine Aufgabe im Punkte-Formular auswählen.")
                return
            task_codes = [task_code]
            self._superposition_max_points = max_points
            clip = fitz.Rect(*template.box)
            page_number = template.page_number
        else:
            task_codes = self._resolve_supersymbol_task_codes(template)
            if not task_codes:
                messagebox.showinfo("Hinweis", "Bitte eine Aufgabe oder 'Summe aller Aufgaben' wählen.")
                return
            self._superposition_page_number = template.page_number
            page_number = self._superposition_page_number

        self._superposition_mode = mode
        self._superposition_task_codes = task_codes
        self._supersymbol_preview_button.configure(state="disabled")
        self._supersymbol_cancel_button.pack(side=ui.LEFT, padx=(8, 0))
        if mode == "grade":
            self._superposition_page_nav_frame.pack(anchor=ui.W, pady=(4, 0))
        self._render_supersymbol_filtered_page(students=target_students, page_number=page_number, clip=clip)
        label = "Punkte" if mode == "scored" else "Note"
        self._supersymbol_info_var.set(
            f"{label}-Superposition-Vorschau ({len(target_students)} Personen) - Klick platziert die Werte."
        )

    def _change_superposition_page(self, delta: int) -> None:
        """Move the Noten-Superposition preview by one page, independent of the current Bereich.

        Navigation is bounded by the largest `page_count` among target
        students (Praezedenz: `main_window_reading.py`s
        `max(student.page_count, 1)`), but that only governs what can be
        *looked at* - `apply_grade_superposition_immediate` separately
        validates, before placing anything, that every target student
        actually has the currently shown page (see its docstring); a page
        only some of them have can be viewed but never written to.
        """
        if self._superposition_mode != "grade" or self._current_exam is None:
            return
        target_students = [self._current_exam.students[index] for index in self._correction_student_indices]
        if not target_students:
            return
        max_page = max((student.page_count for student in target_students), default=1)
        max_page = max(max_page, 1)
        current = self._superposition_page_number or 1
        self._superposition_page_number = max(1, min(max_page, current + delta))
        self._render_supersymbol_filtered_page(students=target_students, page_number=self._superposition_page_number)

    def _apply_superposition_at_canvas_position(self, canvas_x: float, canvas_y: float) -> None:
        """Resolve every target student's Punkte-/Noten-Wert and place it, via the matching controller method."""
        if self._current_exam is None or self._controller is None or self._superposition_mode is None:
            return
        template = self._current_correction_template()
        if template is None:
            return
        pdf_pos = self._canvas_to_pdf_coords(canvas_x, canvas_y)
        if pdf_pos is None:
            return

        # "grade" mode's preview can be navigated to any page independent of
        # the Bereich (see _change_superposition_page) - the annotation must
        # land on whatever page is currently shown, not the Bereich's own
        # page. "scored" stays tied to the Bereich's page as before.
        page_number = (
            self._superposition_page_number
            if self._superposition_mode == "grade" and self._superposition_page_number is not None
            else template.page_number
        )
        student_ids = [self._current_exam.students[index].student_id for index in self._correction_student_indices]
        apply_method = (
            self._controller.apply_scored_superposition_immediate
            if self._superposition_mode == "scored"
            else self._controller.apply_grade_superposition_immediate
        )
        extra_kwargs = (
            {"max_points": self._superposition_max_points, "show_max_points": self._superposition_show_max_points_var.get()}
            if self._superposition_mode == "scored"
            else {}
        )
        updated = apply_method(
            exam=self._current_exam,
            region_id=template.region_id,
            page_number=page_number,
            task_codes=self._superposition_task_codes,
            student_ids=student_ids,
            annotation_type="text",
            color_hex=self._current_marker_color_hex(),
            font_size=self._default_annotation_font_size,
            x=pdf_pos[0],
            y=pdf_pos[1],
            **extra_kwargs,
        )
        if updated is None:
            return
        self._current_exam = updated
        self._cancel_supersymbol_filter()
