from __future__ import annotations

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui


class MainWindowViewTransitionsMixin:
    """View-/Modus-Wechsel (Uebersicht <-> Detail <-> Einlesen/Extraseiten/Namen/Korrektur).

    Ausgelagert aus `main_window_view_state.py` (Meilenstein 2.4/2.5 der
    Korrektor-Wunschliste, das dort ergaenzte Notenschluessel-Zuordnungsfeld
    hat die Datei ueber die projektweite ~300-Zeilen-Konvention gebracht -
    siehe `docs/ARCHITEKTUR.md` "Datei-Organisation"). Reine
    Sichtbarkeits-/Zustandsumschaltung zwischen den Top-Level-Views und
    Detail-Submodi; `_build_detail_view` (die Widget-Konstruktion, die diese
    Methoden bedienen) bleibt in `main_window_view_state.py`.
    """

    def _show_detail_mode(self) -> None:
        if self._current_exam is None:
            return
        self._show_view("detail")
        self._in_detail_mode = True
        self._set_detail_submode("reading")

    def _show_view(self, view_name: str) -> None:
        frames = {
            "overview": self._overview_view,
            "detail": self._detail_view,
            "reading": self._reading_view,
            "correction": self._correction_view,
            "scan_workshop": self._scan_workshop_view,
        }
        target = frames.get(view_name)
        if target is None:
            return

        for frame in frames.values():
            frame.pack_forget()
        target.pack(fill=ui.BOTH, expand=True)
        self._active_view = view_name
        self._refresh_active_student_label()

    def _leave_reading_view(self) -> None:
        self._reading_active = False
        self._extra_mode_active = False
        self._superpage_var.set(False)
        self._extra_sequence = []
        self._reading_mode_title_var.set("Zuschnitt")
        self._clear_pending_redraw()
        self._close_extra_popup()
        self._reading_info_var.set("Zuschnitt: bereit")
        self._status_var.set("Zuschnitt verlassen")
        self._show_detail_mode()

    def _return_to_overview(self) -> None:
        """Close the current exam and all its active mode state, showing the overview."""
        self._current_exam = None
        self._detail_exam_file = None
        self._reading_active = False
        self._extra_mode_active = False
        self._pending_student_names.clear()
        self._end_naming_window()
        self._scan_session = None
        self._correction_mode_active = False
        self._superpage_var.set(False)
        self._selected_region_id = None
        self._selected_region_kind = None
        self._clear_pending_redraw()
        self._draft_regions.clear()
        self._detail_name.set("-")
        self._detail_pages.set("Standardseiten: -")
        self._detail_students.set("Schüler:innen: -")
        self._detail_regions.set("Fertig korrigiert -")
        self._detail_status.set("Status: -")
        self._active_student.set("Aktive Person: -")
        if self._grading_scale_assignment_var is not None:
            self._grading_scale_assignment_var.set("Notenschlüssel: keiner zugeordnet")
        self._correction_zoom_percent = 100
        self._refresh_correction_zoom_label()
        self._reading_mode_title_var.set("Zuschnitt")
        self._reading_info_var.set("Zuschnitt: nicht aktiv")
        if hasattr(self, "_correction_info_var"):
            self._correction_info_var.set("Korrektur: nicht aktiv")
        if hasattr(self, "_correction_points_var"):
            self._correction_points_var.set("")
        if hasattr(self, "_correction_comment_var"):
            self._correction_comment_var.set("")
        if hasattr(self, "_correction_finished_var"):
            self._correction_finished_var.set(False)
        if hasattr(self, "_correction_finished_all_var"):
            self._correction_finished_all_var.set(False)
        self._close_extra_popup()
        self._reading_canvas.delete("all")
        if hasattr(self, "_correction_canvas"):
            self._correction_canvas.delete("all")
        self._active_region_var.set("-")
        self._quick_tasks_var.set("")
        self._form_tasks_text.delete("1.0", ui.END)
        self._refresh_region_tree()
        self._show_view("overview")
        self._in_detail_mode = False
        self._status_var.set("Zur Übersicht zurückgekehrt")

    def _show_correction_controls(self) -> None:
        if self._correction_controls_frame is None:
            return
        self._correction_controls_frame.pack(fill=ui.BOTH, expand=True, pady=(10, 0))

    def _hide_correction_controls(self) -> None:
        if self._correction_controls_frame is None:
            return
        self._correction_controls_frame.pack_forget()

    def _set_detail_submode(self, mode: str) -> None:
        """Switch the Klausur-Detail view between correction / Zuschnitt Schritt 2 ("extra") / Schritt 1 ("reading").

        Both Zuschnitt steps use the same task editor; Schritt 2 additionally
        shows its toolbar, the task checklist and the "Speichern" button
        (ticking tasks needs an explicit commit; Enter/leaving the field
        commits in both steps, see `_commit_reading_fields_if_possible`).
        """
        self._detail_submode = mode

        if mode == "correction":
            self._show_view("correction")
            return
        self._hide_correction_controls()
        self._finish_reading_button.pack(side=ui.RIGHT)

        if mode == "extra":
            self._reading_mode_title_var.set("Zuschnitt · Schritt 2: Einzelseiten")
            self._zuschnitt_step_button.configure(text="◀ Schritt 1: Superseiten")
            self._zuschnitt_step_button.pack(side=ui.RIGHT, padx=(0, 8))
            self._reading_toolbar.pack_forget()
            self._mode_row.pack(fill=ui.X, pady=(8, 0), before=self._reading_split)
            self._regions_editor.pack(fill=ui.BOTH, pady=(10, 0))
            self._task_input_container.pack(fill=ui.X)
            self._task_checklist_frame.pack(fill=ui.X, pady=(6, 0), before=self._region_actions)
            self._extra_toolbar.pack(fill=ui.X, pady=(6, 0), before=self._reading_split)
            self._save_region_button.pack_forget()
            self._save_region_button.pack(side=ui.LEFT, before=self._delete_region_button)
            self._refresh_task_checklist()
            return

        self._reading_mode_title_var.set("Zuschnitt · Schritt 1: Superseiten")
        self._zuschnitt_step_button.configure(text="Schritt 2: Einzelseiten ▶")
        self._zuschnitt_step_button.pack(side=ui.RIGHT, padx=(0, 8))
        self._extra_toolbar.pack_forget()
        self._reading_toolbar.pack(fill=ui.X, before=self._reading_split)
        self._superpage_toggle.pack_forget()
        self._superpage_toggle.pack(side=ui.RIGHT)
        self._mode_row.pack(fill=ui.X, pady=(8, 0), before=self._reading_split)
        self._regions_editor.pack(fill=ui.BOTH, pady=(10, 0))
        self._task_checklist_frame.pack_forget()
        self._task_input_container.pack(fill=ui.X)
        self._save_region_button.pack_forget()
