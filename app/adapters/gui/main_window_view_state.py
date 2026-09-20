from __future__ import annotations

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui, widgets


class MainWindowViewStateMixin:
    """Aufbau der Klausur-Detailansicht und ihrer Eingabefelder.

    View-/Modus-**Wechsel**-Logik (Sichtbarkeit der Top-Level-Views,
    Detail-Submodi) liegt getrennt in `main_window_view_transitions.py` -
    siehe dessen Docstring fuer die Begruendung des Splits.
    """

    def _build_detail_view(self) -> None:
        widgets.Label(self._detail_view, text="Klausur-Details", style="Title.TLabel").pack(anchor=ui.W)

        detail_actions = widgets.Frame(self._detail_view, style="Surface.TFrame")
        detail_actions.pack(fill=ui.X, pady=(8, 10))

        back_button = widgets.Button(
            detail_actions,
            text="Zur Übersicht",
            style="SecondaryAction.TButton",
            command=self._return_to_overview,
        )
        back_button.pack(side=ui.LEFT)
        self._attach_hover_help(back_button, label="Zur Gesamtübersicht wechseln", shortcut="Esc")

        mode_reading_button = widgets.Button(
            detail_actions,
            text="Einlesen",
            style="SecondaryAction.TButton",
            command=self._start_reading_mode,
        )
        mode_reading_button.pack(side=ui.LEFT, padx=(8, 0))
        self._attach_hover_help(mode_reading_button, label="In den Einlesemodus wechseln", shortcut=None)

        mode_extra_button = widgets.Button(
            detail_actions,
            text="Extraseiten",
            style="SecondaryAction.TButton",
            command=self._start_extra_mode,
        )
        mode_extra_button.pack(side=ui.LEFT, padx=(8, 0))
        self._attach_hover_help(mode_extra_button, label="In den Extraseitenmodus wechseln", shortcut=None)

        mode_correction_button = widgets.Button(
            detail_actions,
            text="Korrektur",
            style="SecondaryAction.TButton",
            command=self._start_correction_mode,
        )
        mode_correction_button.pack(side=ui.LEFT, padx=(8, 0))
        self._attach_hover_help(mode_correction_button, label="In den Korrekturmodus wechseln", shortcut=None)

        mode_naming_button = widgets.Button(
            detail_actions,
            text="Namen",
            style="SecondaryAction.TButton",
            command=self._start_naming_mode,
        )
        mode_naming_button.pack(side=ui.LEFT, padx=(8, 0))
        self._attach_hover_help(mode_naming_button, label="In den Namenmodus wechseln (PDFs umbenennen)", shortcut=None)

        export_detail_button = widgets.Button(
            detail_actions,
            text="Export",
            style="SecondaryAction.TButton",
            command=self._menu_export_scores,
        )
        export_detail_button.pack(side=ui.RIGHT)
        self._attach_hover_help(export_detail_button, label="Punkte als CSV exportieren", shortcut="Strg+E")

        grading_scale_manage_button = widgets.Button(
            detail_actions,
            text="Notenschlüssel",
            style="SecondaryAction.TButton",
            command=self._open_grading_scale_management_popup,
        )
        grading_scale_manage_button.pack(side=ui.RIGHT, padx=(0, 8))
        self._attach_hover_help(grading_scale_manage_button, label="Notenschluessel anlegen/bearbeiten/archivieren")

        task_category_button = widgets.Button(
            detail_actions,
            text="Kategorien",
            style="SecondaryAction.TButton",
            command=self._open_task_category_popup,
        )
        task_category_button.pack(side=ui.RIGHT, padx=(0, 8))
        self._attach_hover_help(task_category_button, label="Aufgaben per Drag-and-Drop Kategorien zuordnen")

        self._detail_name = ui.StringVar(value="-")
        self._detail_pages = ui.StringVar(value="Standardseiten: -")
        self._detail_students = ui.StringVar(value="Schüler:innen: -")
        self._detail_regions = ui.StringVar(value="Fertig korrigiert -")
        self._detail_status = ui.StringVar(value="Status: -")
        self._active_student = ui.StringVar(value="Aktive Person: -")

        for variable in [
            self._detail_name,
            self._detail_pages,
            self._detail_students,
            self._detail_regions,
            self._detail_status,
            self._active_student,
        ]:
            widgets.Label(self._detail_view, textvariable=variable, style="Muted.TLabel").pack(anchor=ui.W, pady=4)

        grading_scale_row = widgets.Frame(self._detail_view, style="Surface.TFrame")
        grading_scale_row.pack(fill=ui.X, pady=(4, 0))
        self._grading_scale_assignment_var = ui.StringVar(value="Notenschluessel: keiner zugeordnet")
        widgets.Label(grading_scale_row, textvariable=self._grading_scale_assignment_var, style="Muted.TLabel").pack(
            side=ui.LEFT
        )
        self._grading_scale_assign_choice_var = ui.StringVar(value="")
        self._grading_scale_assign_combo = widgets.Combobox(
            grading_scale_row,
            textvariable=self._grading_scale_assign_choice_var,
            state="readonly",
            width=28,
            values=(),
        )
        self._grading_scale_assign_combo.pack(side=ui.LEFT, padx=(10, 0))
        assign_grading_scale_button = widgets.Button(
            grading_scale_row,
            text="Zuordnen",
            style="SecondaryAction.TButton",
            command=self._assign_selected_grading_scale_to_current_exam,
        )
        assign_grading_scale_button.pack(side=ui.LEFT, padx=(6, 0))
        self._attach_hover_help(
            assign_grading_scale_button, label="Gewaehlten Notenschluessel dieser Klausur zuordnen"
        )

        self._correction_controls_frame = widgets.Frame(self._detail_view, style="Surface.TFrame")
        self._correction_controls_frame.pack(fill=ui.X, pady=(10, 0))

        widgets.Separator(self._correction_controls_frame).pack(fill=ui.X, pady=(0, 10))
        widgets.Label(self._correction_controls_frame, text="Schnellkorrektur", style="Muted.TLabel").pack(anchor=ui.W)

        correction_header = widgets.Frame(self._correction_controls_frame, style="Surface.TFrame")
        correction_header.pack(fill=ui.X, pady=(6, 6))
        widgets.Label(correction_header, text="Bereich", style="Muted.TLabel").pack(side=ui.LEFT)
        self._correction_area_var = ui.StringVar(value="A")
        self._correction_area_combo = widgets.Combobox(
            correction_header,
            textvariable=self._correction_area_var,
            state="readonly",
            width=8,
            values=("A",),
        )
        self._correction_area_combo.pack(side=ui.LEFT, padx=(8, 8))
        start_correction_button = widgets.Button(
            correction_header,
            text="Korrekturmodus",
            style="SecondaryAction.TButton",
            command=self._start_correction_mode,
        )
        start_correction_button.pack(side=ui.LEFT)
        self._attach_hover_help(start_correction_button, label="Korrekturmodus starten", shortcut=None)

        stop_correction_button = widgets.Button(
            correction_header,
            text="Modus beenden",
            style="SecondaryAction.TButton",
            command=self._stop_correction_mode,
        )
        stop_correction_button.pack(side=ui.LEFT, padx=(8, 0))
        self._attach_hover_help(stop_correction_button, label="Aktiven Modus beenden", shortcut="Esc")

        show_extras_button = widgets.Button(
            correction_header,
            text="Extraseiten ansehen",
            style="SecondaryAction.TButton",
            command=self._toggle_extra_pages_popup_for_current,
        )
        show_extras_button.pack(side=ui.RIGHT)
        self._attach_hover_help(show_extras_button, label="Extraseiten-Popup der aktuellen Person oeffnen", shortcut=None)

        form = widgets.Frame(self._correction_controls_frame, style="Surface.TFrame")
        form.pack(fill=ui.X, pady=(8, 0))
        form.columnconfigure(1, weight=1)

        widgets.Label(form, text="Aufgabe", style="Muted.TLabel").grid(row=0, column=0, sticky=ui.W, padx=(0, 6), pady=4)
        widgets.Label(form, text="Max", style="Muted.TLabel").grid(row=1, column=0, sticky=ui.W, padx=(0, 6), pady=4)
        widgets.Label(form, text="Erreicht", style="Muted.TLabel").grid(row=2, column=0, sticky=ui.W, padx=(0, 6), pady=4)

        self._task_code_var = ui.StringVar(value="A1")
        self._max_points_var = ui.StringVar(value="0")
        self._points_var = ui.StringVar(value="")

        self._task_code_entry = widgets.Entry(form, textvariable=self._task_code_var)
        self._max_points_entry = widgets.Entry(form, textvariable=self._max_points_var)
        self._points_entry = widgets.Entry(form, textvariable=self._points_var)

        self._task_code_entry.grid(row=0, column=1, sticky=ui.EW, pady=4)
        self._max_points_entry.grid(row=1, column=1, sticky=ui.EW, pady=4)
        self._points_entry.grid(row=2, column=1, sticky=ui.EW, pady=4)

        self._task_code_entry.bind("<Escape>", self._on_points_escape)
        self._max_points_entry.bind("<Escape>", self._on_points_escape)
        self._points_entry.bind("<FocusOut>", self._on_points_focus_out)
        self._points_entry.bind("<Return>", self._on_points_commit)
        self._points_entry.bind("<Escape>", self._on_points_escape)

        nav = widgets.Frame(self._correction_controls_frame, style="Surface.TFrame")
        nav.pack(fill=ui.X, pady=(10, 0))
        prev_student_button = widgets.Button(
            nav,
            text="◀ Person",
            style="SecondaryAction.TButton",
            command=lambda: self._move_student(-1),
        )
        prev_student_button.pack(side=ui.LEFT)
        self._attach_hover_help(prev_student_button, label="Vorherige Person", shortcut="Links")

        next_student_button = widgets.Button(
            nav,
            text="Person ▶",
            style="SecondaryAction.TButton",
            command=lambda: self._move_student(1),
        )
        next_student_button.pack(side=ui.LEFT, padx=(8, 0))
        self._attach_hover_help(next_student_button, label="Naechste Person", shortcut="Rechts")

    def _focus_first_input_field(self) -> None:
        if self._correction_mode_active:
            if str(self._correction_points_entry.cget("state")) == "disabled":
                if self._correction_finished_check is not None:
                    self._correction_finished_check.focus_set()
                return
            self._correction_points_entry.focus_set()
            self._correction_points_entry.selection_range(0, ui.END)
            return
        self._task_code_entry.focus_set()
        self._task_code_entry.selection_range(0, ui.END)

    def start_reading_mode_for_current_exam(self) -> None:
        self._start_reading_mode()
