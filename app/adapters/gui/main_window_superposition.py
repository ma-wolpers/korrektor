"""Punkte-/Prozent-/Noten-Superposition im Korrekturmodus (Mixin).

Bedienelemente (inkl. Auswahl "Wert von"), Start der Superposition, Vorschau mit
Seitenblaettern und Einfuegen an der angeklickten Position. Aus
main_window_supersymbol.py ausgelagert (Dateigroessen-Regel)."""

from __future__ import annotations


import fitz

from app.adapters.gui.dialog_services import messagebox
from app.adapters.gui.main_window_constants import SUPERPOSITION_WHOLE_EXAM_LABEL

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui, widgets
from bw_gui.widgets import Checkbox

_MODE_LABELS = {"scored": "Punkte", "percent": "Prozent", "grade": "Note"}


class MainWindowSuperpositionMixin:
    """Punkte-/Prozent-/Noten-Superposition im Korrekturmodus (Mixin)."""

    def _build_superposition_controls(self, parent) -> None:
        """Superposition section below the Supersymbol filter: "Wert von", the three insert buttons, options, page nav."""
        superposition_row = widgets.Frame(parent, style="Surface.TFrame")
        superposition_row.pack(fill=ui.X, pady=(6, 0))
        widgets.Label(superposition_row, text="Superposition (alle Personen, erster Superseiten-Bereich der Aufgabe)", style="Muted.TLabel").pack(
            anchor=ui.W
        )
        value_row = widgets.Frame(superposition_row, style="Surface.TFrame")
        value_row.pack(fill=ui.X, pady=(4, 0))
        widgets.Label(value_row, text="Wert von", style="Muted.TLabel").pack(side=ui.LEFT)
        self._superposition_value_var = ui.StringVar(value="")
        self._superposition_value_combo = widgets.Combobox(
            value_row, textvariable=self._superposition_value_var, state="readonly", width=26, values=()
        )
        self._superposition_value_combo.pack(side=ui.LEFT, padx=(8, 0))
        self._attach_hover_help(
            self._superposition_value_combo,
            label="Wofür Punkte bzw. Prozent eingefügt werden: aktuelle Teilaufgabe, ganze Aufgabe (alle Teilaufgaben) oder gesamte Klausur",
        )

        superposition_buttons = widgets.Frame(superposition_row, style="Surface.TFrame")
        superposition_buttons.pack(fill=ui.X, pady=(4, 0))
        buttons = (
            ("Punkte einfügen", "scored", "Fügt an einer gemeinsamen Position die jeweils erreichte Punktzahl jeder Person ein"),
            ("Prozent einfügen", "percent", "Fügt an einer gemeinsamen Position den jeweils erreichten Prozentsatz jeder Person ein"),
            ("Note einfügen", "grade", "Fügt an einer gemeinsamen Position die jeweilige Note jeder Person ein (Notenschlüssel nötig)"),
        )
        for index, (text, mode, help_text) in enumerate(buttons):
            button = widgets.Button(
                superposition_buttons,
                text=text,
                style="SecondaryAction.TButton",
                command=self._start_grade_superposition if mode == "grade" else (lambda mode=mode: self._start_superposition_preview(mode=mode)),
            )
            button.pack(side=ui.LEFT, padx=(0 if index == 0 else 8, 0))
            self._attach_hover_help(button, label=help_text + " - beim Überschreiben der PDFs immer mit dem aktuellen Stand")

        show_max_points_check = Checkbox(
            superposition_row,
            text="Gesamtpunktzahl anzeigen",
            variable=self._superposition_show_max_points_var,
        )
        show_max_points_check.pack(anchor=ui.W, pady=(4, 0))
        self._attach_hover_help(
            show_max_points_check,
            label="Punkte-Superposition zeigt z. B. '7/10' statt nur '7'",
        )

        superposition_page_nav = widgets.Frame(superposition_row, style="Surface.TFrame")
        self._superposition_page_nav_frame = superposition_page_nav
        for index, (text, delta) in enumerate((("◀ Seite", -1), ("Seite ▶", 1))):
            button = widgets.Button(
                superposition_page_nav,
                text=text,
                style="SecondaryAction.TButton",
                command=lambda delta=delta: self._change_superposition_page(delta),
            )
            button.pack(side=ui.LEFT, padx=(0 if index == 0 else 8, 0))
            self._attach_hover_help(
                button,
                label=f"Noten-Superposition: eine Seite {'zurück' if delta < 0 else 'vor'} (unabhängig von der Aufgabe)",
            )
        superposition_page_nav.pack(anchor=ui.W, pady=(4, 0))
        superposition_page_nav.pack_forget()

    def _superposition_value_options(self) -> dict[str, list[str]]:
        """``{Anzeigetext: task_codes}`` for "Wert von": the current subtask, its whole task(s), the whole exam (``[]``)."""
        code, _max_points = self._selected_correction_task()
        options = self._task_scope_options([code]) if code is not None else {}
        options[SUPERPOSITION_WHOLE_EXAM_LABEL] = []
        return options

    def _refresh_superposition_value_choices(self) -> None:
        """Offer the "Wert von" choices for the current task; keep a still offered selection, else the subtask."""
        values = tuple(self._superposition_value_options())
        self._superposition_value_combo["values"] = values
        if self._superposition_value_var.get() not in values:
            self._superposition_value_var.set(values[0])

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

        - "scored"/"percent" take their tasks from the own "Wert von"
          selection (`_superposition_value_options`: current subtask, whole
          task, whole exam = ``[]``), independent of the Supersymbol filter's
          "Aufgabe(n)". The preview is cropped to the current Bereich's box
          (`clip`) and stays on the Bereich's page.
        - "grade" is always exam-wide (`apply_grade_superposition_immediate`),
          shows the whole page, and `self._superposition_page_number` lets the
          teacher navigate to any page via `_change_superposition_page`.

        The inserted texts remember their source (`LiveValue`), so the
        preview and "Alle PDFs überschreiben" always show current values.
        """
        if self._current_exam is None or self._controller is None:
            return
        template = self._current_correction_template()
        if template is None:
            messagebox.showinfo("Hinweis", "Diese Aufgabe liegt nur in Einzelseiten-Bereichen – Superposition braucht einen Superseiten-Bereich.")
            return
        target_students = [self._current_exam.students[index] for index in self._correction_student_indices]
        if not target_students:
            return

        clip: fitz.Rect | None = None
        if mode != "grade":
            options = self._superposition_value_options()
            if self._superposition_value_var.get() not in options:
                messagebox.showinfo("Hinweis", "Bitte unter „Wert von“ wählen, wofür eingefügt wird.")
                return
            task_codes = options[self._superposition_value_var.get()]
            clip = fitz.Rect(*template.box)
            page_number = template.page_number
        else:
            task_codes = []
            self._superposition_page_number = template.page_number
            page_number = self._superposition_page_number

        self._superposition_mode = mode
        self._superposition_task_codes = task_codes
        self._supersymbol_preview_button.configure(state="disabled")
        self._supersymbol_cancel_button.pack(side=ui.LEFT, padx=(8, 0))
        if mode == "grade":
            self._superposition_page_nav_frame.pack(anchor=ui.W, pady=(4, 0))
        self._render_supersymbol_filtered_page(students=target_students, page_number=page_number, clip=clip)
        label = _MODE_LABELS[mode]
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
        apply_method = {
            "scored": self._controller.apply_scored_superposition_immediate,
            "percent": self._controller.apply_percent_superposition_immediate,
            "grade": self._controller.apply_grade_superposition_immediate,
        }[self._superposition_mode]
        extra_kwargs = (
            {"show_max_points": self._superposition_show_max_points_var.get()}
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
