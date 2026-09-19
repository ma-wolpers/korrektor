from __future__ import annotations

from typing import Sequence

from app.adapters.gui.dialog_services import messagebox
from app.adapters.gui.main_window_constants import SUPERSYMBOL_OPERATOR_BY_LABEL, SUPERSYMBOL_SUM_SCOPE_LABEL
from app.adapters.gui.main_window_types import CorrectionTemplate
from app.core.domain.models import StudentExam
from app.core.domain.score_filter import compute_student_value, filter_matching_student_ids

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui


class MainWindowSupersymbolMixin:
    def _refresh_supersymbol_scope_choices(self, template: CorrectionTemplate | None) -> None:
        """Populate the Supersymbol "Aufgabe(n)" scope combobox for the current Bereich.

        Offers each individual task code, plus "Summe aller Aufgaben" only
        when the Bereich actually has more than one task (a sum over a
        single task would just duplicate that task's own value).
        """
        if template is None or not template.tasks:
            self._supersymbol_scope_combo["values"] = ()
            self._supersymbol_scope_var.set("")
            return
        values = tuple(task.code for task in template.tasks)
        if len(template.tasks) > 1:
            values = values + (SUPERSYMBOL_SUM_SCOPE_LABEL,)
        self._supersymbol_scope_combo["values"] = values
        if self._supersymbol_scope_var.get() not in values:
            self._supersymbol_scope_var.set(values[0])

    def _resolve_supersymbol_task_codes(self, template: CorrectionTemplate) -> list[str]:
        """Resolve the Supersymbol scope selection to a concrete task_code list.

        Fixed once, at filter-start time (Invariant: the bulk apply is a
        one-time action, not a live filter that would need to react to the
        Bereich's tasks changing later).
        """
        scope = self._supersymbol_scope_var.get()
        if not scope:
            return []
        if scope == SUPERSYMBOL_SUM_SCOPE_LABEL:
            return [task.code for task in template.tasks]
        return [scope]

    def _start_supersymbol_filter(self) -> None:
        """Validate the Supersymbol filter and show the matched-students Superseite.

        0 matches is a hard stop (Invariant: there is no darstellbare
        Superseite to place a symbol on), not just a UX nicety.
        """
        if self._current_exam is None or self._controller is None:
            return
        template = self._current_correction_template()
        if template is None:
            messagebox.showinfo("Hinweis", "Bitte zuerst einen Bereich waehlen.")
            return
        task_codes = self._resolve_supersymbol_task_codes(template)
        if not task_codes:
            messagebox.showinfo("Hinweis", "Bitte eine Aufgabe oder 'Summe aller Aufgaben' waehlen.")
            return
        operator = SUPERSYMBOL_OPERATOR_BY_LABEL.get(self._supersymbol_operator_var.get())
        if operator is None:
            return
        raw_value = self._supersymbol_value_var.get().strip().replace(",", ".")
        try:
            target_value = float(raw_value)
        except ValueError:
            messagebox.showerror("Ungueltiger Wert", "Bitte eine Zahl als Filterwert eingeben.")
            return

        scores = self._controller.load_scores_for_exam(exam=self._current_exam)
        values_by_student = {
            student.student_id: compute_student_value(scores.get(student.student_id, {}), task_codes)
            for student in self._current_exam.students
        }
        matched_ids = filter_matching_student_ids(values_by_student, operator, target_value)
        if not matched_ids:
            messagebox.showerror(
                "Kein Treffer",
                "Kein(e) Schueler:in erfuellt diese Bedingung - das Supersymbol kann so nicht platziert werden.",
            )
            return

        matched_ids_set = set(matched_ids)
        matched_students = [s for s in self._current_exam.students if s.student_id in matched_ids_set]
        self._supersymbol_filter_active = True
        self._supersymbol_matched_student_ids = matched_ids
        self._supersymbol_preview_button.configure(state="disabled")
        self._supersymbol_cancel_button.pack(side=ui.LEFT, padx=(8, 0))
        self._render_supersymbol_filtered_page(students=matched_students, page_number=template.page_number)
        lookup = self._marker_tool_lookup(self._correction_marker_tool_key)
        glyph_label = lookup[1] if lookup else "?"
        self._supersymbol_info_var.set(
            f"{len(matched_ids)} Treffer - Klick auf die Vorschau platziert '{glyph_label}' bei allen gleichzeitig."
        )

    def _cancel_supersymbol_filter(self) -> None:
        """Leave the Supersymbol filtered preview (with or without having applied it)."""
        if not self._supersymbol_filter_active:
            return
        self._supersymbol_filter_active = False
        self._supersymbol_matched_student_ids = []
        self._supersymbol_preview_button.configure(state="normal")
        self._supersymbol_cancel_button.pack_forget()
        self._supersymbol_info_var.set("")
        self._render_correction_preview()

    def _render_supersymbol_filtered_page(self, *, students: Sequence[StudentExam], page_number: int) -> int:
        """Render the Supersymbol filtered Superseite onto the correction canvas.

        Full page (uncropped), unlike the normal single-student Korrektur
        preview: it sets `_correction_clip_box` to the whole reference page
        (origin at 0,0) rather than `template.box`, so the existing
        `_canvas_to_pdf_coords` conversion already yields correct absolute
        PDF coordinates - a click lands at the identical position for every
        matched student without any new coordinate-conversion code.
        """
        built = self._build_superposed_pixmap(students=students, page_number=page_number)
        if built is None:
            self._correction_canvas.delete("all")
            self._correction_info_var.set("Supersymbol: keine renderbaren Seiten fuer die Treffer")
            return 0
        pixmap, reference_rect, source_count = built

        pgm_header = f"P5 {pixmap.width} {pixmap.height} 255\n".encode("ascii")
        self._correction_photo = ui.PhotoImage(data=pgm_header + pixmap.samples, format="ppm")
        scale = pixmap.width / max(reference_rect.width, 1.0)
        self._correction_clip_box = (0.0, 0.0, float(reference_rect.width), float(reference_rect.height))
        self._correction_scale = scale
        self._correction_canvas.delete("all")
        self._correction_canvas.create_image(0, 0, anchor=ui.NW, image=self._correction_photo)
        self._correction_canvas.configure(scrollregion=(0, 0, pixmap.width, pixmap.height))
        self._correction_info_var.set(f"Supersymbol-Vorschau | Seite {page_number} | Treffer: {source_count}")
        return source_count

    def _apply_supersymbol_at_canvas_position(self, canvas_x: float, canvas_y: float) -> None:
        """Place the current marker symbol for every matched student at the clicked position."""
        if self._current_exam is None or self._controller is None:
            return
        template = self._current_correction_template()
        if template is None:
            return
        pdf_pos = self._canvas_to_pdf_coords(canvas_x, canvas_y)
        if pdf_pos is None:
            return
        lookup = self._marker_tool_lookup(self._correction_marker_tool_key)
        if lookup is None:
            return
        glyph, _label = lookup
        updated = self._controller.apply_super_symbol_immediate(
            exam=self._current_exam,
            region_id=template.region_id,
            page_number=template.page_number,
            matched_student_ids=self._supersymbol_matched_student_ids,
            annotation_type="symbol",
            content=glyph,
            color_hex=self._current_marker_color_hex(),
            font_size=self._default_annotation_font_size,
            x=pdf_pos[0],
            y=pdf_pos[1],
        )
        if updated is None:
            return
        self._current_exam = updated
        self._cancel_supersymbol_filter()
