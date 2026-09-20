from __future__ import annotations

from typing import Sequence

from app.adapters.gui.dialog_services import messagebox
from app.adapters.gui.main_window_constants import (
    SUPERSYMBOL_OPERATOR_BY_LABEL,
    SUPERSYMBOL_OPERATOR_LABELS,
    SUPERSYMBOL_SUM_SCOPE_LABEL,
)
from app.adapters.gui.main_window_types import CorrectionTemplate
from app.core.domain.models import StudentExam
from app.core.domain.score_filter import compute_student_value, filter_matching_student_ids

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui, widgets


class MainWindowSupersymbolMixin:
    def _build_correction_view_form_supersymbol(self) -> None:
        supersymbol_controls = widgets.Frame(self._correction_form_panel, style="Surface.TFrame")
        supersymbol_controls.pack(fill=ui.X, pady=(10, 0))
        widgets.Label(supersymbol_controls, text="Supersymbol (Filter)", style="Muted.TLabel").pack(anchor=ui.W)

        supersymbol_row1 = widgets.Frame(supersymbol_controls, style="Surface.TFrame")
        supersymbol_row1.pack(fill=ui.X, pady=(4, 0))
        widgets.Label(supersymbol_row1, text="Aufgabe(n)", style="Muted.TLabel").pack(side=ui.LEFT)
        self._supersymbol_scope_var = ui.StringVar(value="")
        self._supersymbol_scope_combo = widgets.Combobox(
            supersymbol_row1,
            textvariable=self._supersymbol_scope_var,
            state="readonly",
            width=16,
            values=(),
        )
        self._supersymbol_scope_combo.pack(side=ui.LEFT, padx=(8, 0))
        self._supersymbol_scope_combo.bind("<<ComboboxSelected>>", self._on_supersymbol_scope_changed)

        supersymbol_row2 = widgets.Frame(supersymbol_controls, style="Surface.TFrame")
        supersymbol_row2.pack(fill=ui.X, pady=(4, 0))
        widgets.Label(supersymbol_row2, text="Punkte", style="Muted.TLabel").pack(side=ui.LEFT)
        self._supersymbol_operator_var = ui.StringVar(value=SUPERSYMBOL_OPERATOR_LABELS[0])
        supersymbol_operator_combo = widgets.Combobox(
            supersymbol_row2,
            textvariable=self._supersymbol_operator_var,
            state="readonly",
            width=4,
            values=SUPERSYMBOL_OPERATOR_LABELS,
        )
        supersymbol_operator_combo.pack(side=ui.LEFT, padx=(8, 0))
        self._supersymbol_value_var = ui.StringVar(value="")
        supersymbol_value_entry = widgets.Entry(supersymbol_row2, textvariable=self._supersymbol_value_var, width=8)
        supersymbol_value_entry.pack(side=ui.LEFT, padx=(6, 0))

        supersymbol_row3 = widgets.Frame(supersymbol_controls, style="Surface.TFrame")
        supersymbol_row3.pack(fill=ui.X, pady=(6, 0))
        self._supersymbol_preview_button = widgets.Button(
            supersymbol_row3,
            text="Vorschau anzeigen",
            style="SecondaryAction.TButton",
            command=self._start_supersymbol_filter,
        )
        self._supersymbol_preview_button.pack(side=ui.LEFT)
        self._attach_hover_help(
            self._supersymbol_preview_button,
            label="Zeigt alle Personen, die die Bedingung erfuellen, ueberlagert an - Klick platziert das aktuell gewaehlte Markierungssymbol bei allen gleichzeitig",
        )
        self._supersymbol_cancel_button = widgets.Button(
            supersymbol_row3,
            text="Abbrechen",
            style="SecondaryAction.TButton",
            command=self._cancel_supersymbol_filter,
        )
        self._supersymbol_cancel_button.pack(side=ui.LEFT, padx=(8, 0))
        self._supersymbol_cancel_button.pack_forget()

        superposition_row = widgets.Frame(supersymbol_controls, style="Surface.TFrame")
        superposition_row.pack(fill=ui.X, pady=(6, 0))
        widgets.Label(superposition_row, text="Superposition (alle Personen des Bereichs)", style="Muted.TLabel").pack(
            anchor=ui.W
        )
        superposition_buttons = widgets.Frame(superposition_row, style="Surface.TFrame")
        superposition_buttons.pack(fill=ui.X, pady=(4, 0))
        self._superposition_points_button = widgets.Button(
            superposition_buttons,
            text="Punkte einfuegen",
            style="SecondaryAction.TButton",
            command=self._start_scored_superposition,
        )
        self._superposition_points_button.pack(side=ui.LEFT)
        self._attach_hover_help(
            self._superposition_points_button,
            label="Fuegt an einer gemeinsamen Position die jeweils erreichte Punktzahl jeder Person ein",
        )
        self._superposition_grade_button = widgets.Button(
            superposition_buttons,
            text="Note einfuegen",
            style="SecondaryAction.TButton",
            command=self._start_grade_superposition,
        )
        self._superposition_grade_button.pack(side=ui.LEFT, padx=(8, 0))
        self._attach_hover_help(
            self._superposition_grade_button,
            label="Fuegt an einer gemeinsamen Position die jeweilige Note jeder Person ein (Notenschluessel noetig)",
        )

        self._supersymbol_info_var = ui.StringVar(value="")
        widgets.Label(
            supersymbol_controls,
            textvariable=self._supersymbol_info_var,
            style="Muted.TLabel",
        ).pack(anchor=ui.W, pady=(4, 0))

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
        self._prefill_supersymbol_value_for_scope(template)

    def _on_supersymbol_scope_changed(self, _event: ui.Event[ui.Misc]) -> None:
        """Re-prefill the Punkte field whenever the "Aufgabe(n)"-Auswahl changes by hand."""
        self._prefill_supersymbol_value_for_scope(self._current_correction_template())

    def _prefill_supersymbol_value_for_scope(self, template: CorrectionTemplate | None) -> None:
        """Set the Supersymbol-Punktwert to the current scope's Maximalpunktwert-Summe.

        Runs both on Bereich-Wechsel (`_refresh_supersymbol_scope_choices`)
        and on manual Aufgabe(n)-Auswahl (`_on_supersymbol_scope_changed`),
        so the field always starts at a sensible default (the maximum
        achievable value for the current scope) instead of empty - the
        teacher can still overwrite it before starting the filter, this only
        saves typing the common case (Filter: "hat volle Punktzahl").
        """
        if template is None:
            return
        task_codes = self._resolve_supersymbol_task_codes(template)
        if not task_codes:
            return
        max_points_by_code = {task.code: task.max_points for task in template.tasks}
        total_max_points = sum(max_points_by_code.get(code, 0.0) for code in task_codes)
        self._supersymbol_value_var.set(f"{total_max_points:g}")

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
        """Leave any active bulk-preview (Supersymbol filter or a Punkte-/Noten-Superposition).

        Shared cancel path for all three "preview a Superseite, click to
        apply" flows - only one is ever active at a time (starting one
        preview always goes through here first, via `_render_correction_preview`
        never having a stale filter/superposition state left behind).
        """
        if not self._supersymbol_filter_active and self._superposition_mode is None:
            return
        self._supersymbol_filter_active = False
        self._supersymbol_matched_student_ids = []
        self._superposition_mode = None
        self._superposition_task_codes = []
        self._supersymbol_preview_button.configure(state="normal")
        self._supersymbol_cancel_button.pack_forget()
        self._supersymbol_info_var.set("")
        self._render_correction_preview()

    def _start_scored_superposition(self) -> None:
        self._start_superposition_preview(mode="scored")

    def _start_grade_superposition(self) -> None:
        if self._current_exam is not None and self._current_exam.grading_scale_snapshot is None:
            messagebox.showinfo("Hinweis", "Bitte dieser Klausur zuerst einen Notenschluessel zuordnen.")
            return
        self._start_superposition_preview(mode="grade")

    def _start_superposition_preview(self, *, mode: str) -> None:
        """Show the Superseite for every current-Bereich Korrektur-Schueler:in, ready for a placing click.

        Target set is always "all correction students of the active
        Bereich" (`self._correction_student_indices`, same set
        "Durchdruecken" uses) - unlike Supersymbol, a Superposition has no
        filter condition to narrow it down.
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
        target_students = [self._current_exam.students[index] for index in self._correction_student_indices]
        if not target_students:
            return

        self._superposition_mode = mode
        self._superposition_task_codes = task_codes
        self._supersymbol_preview_button.configure(state="disabled")
        self._supersymbol_cancel_button.pack(side=ui.LEFT, padx=(8, 0))
        self._render_supersymbol_filtered_page(students=target_students, page_number=template.page_number)
        label = "Punkte" if mode == "scored" else "Note"
        self._supersymbol_info_var.set(
            f"{label}-Superposition-Vorschau ({len(target_students)} Personen) - Klick platziert die Werte."
        )

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

        student_ids = [self._current_exam.students[index].student_id for index in self._correction_student_indices]
        apply_method = (
            self._controller.apply_scored_superposition_immediate
            if self._superposition_mode == "scored"
            else self._controller.apply_grade_superposition_immediate
        )
        updated = apply_method(
            exam=self._current_exam,
            region_id=template.region_id,
            page_number=template.page_number,
            task_codes=self._superposition_task_codes,
            student_ids=student_ids,
            annotation_type="text",
            color_hex=self._current_marker_color_hex(),
            font_size=self._default_annotation_font_size,
            x=pdf_pos[0],
            y=pdf_pos[1],
        )
        if updated is None:
            return
        self._current_exam = updated
        self._cancel_supersymbol_filter()

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
