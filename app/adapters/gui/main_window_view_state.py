from __future__ import annotations

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui


class MainWindowViewStateMixin:
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
        was_naming = self._naming_mode_active
        self._reading_active = False
        self._extra_mode_active = False
        self._naming_mode_active = False
        self._naming_capture_active = False
        self._superpage_var.set(False)
        self._extra_sequence = []
        self._reading_mode_title_var.set("Einlesen")
        self._clear_pending_redraw()
        self._close_extra_popup()
        self._reading_info_var.set("Einlesemodus: bereit")
        self._status_var.set("Namenmodus verlassen" if was_naming else "Einlesemodus verlassen")
        self._show_detail_mode()

    def _return_to_overview(self) -> None:
        """Close the current exam and all its active mode state, showing the overview."""
        self._current_exam = None
        self._detail_exam_file = None
        self._reading_active = False
        self._extra_mode_active = False
        self._naming_mode_active = False
        self._naming_capture_active = False
        self._pending_student_names.clear()
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
        self._correction_zoom_percent = 100
        self._refresh_correction_zoom_label()
        self._reading_mode_title_var.set("Einlesen")
        self._reading_info_var.set("Einlesemodus: nicht aktiv")
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
        if hasattr(self, "_extra_area_codes_var"):
            self._extra_area_codes_var.set("")
        self._refresh_region_tree()
        self._show_view("overview")
        self._in_detail_mode = False
        self._status_var.set("Zur Übersicht zurueckgekehrt")

    def _show_correction_controls(self) -> None:
        if self._correction_controls_frame is None:
            return
        self._correction_controls_frame.pack(fill=ui.BOTH, expand=True, pady=(10, 0))

    def _hide_correction_controls(self) -> None:
        if self._correction_controls_frame is None:
            return
        self._correction_controls_frame.pack_forget()

    def _set_detail_submode(self, mode: str) -> None:
        """Switch the Klausur-Detail view between correction/extra/reading/naming sub-modes.

        Also toggles `_save_region_button` visibility: it is only shown in
        "extra" mode, since the standard Aufgaben/Punkte editor now commits
        via <FocusOut> instead of a manual button (see
        `_commit_reading_fields_if_possible`).
        """
        self._detail_submode = mode

        if mode == "correction":
            self._show_view("correction")
            return
        self._hide_correction_controls()
        self._naming_region_toolbar.pack_forget()
        self._naming_capture_panel.pack_forget()
        self._finish_reading_button.pack(side=ui.RIGHT)

        if mode == "extra":
            self._reading_mode_title_var.set("Extraseiten")
            self._reading_toolbar.pack_forget()
            self._mode_row.pack_forget()
            self._regions_editor.pack(fill=ui.BOTH, pady=(10, 0))
            if self._extra_overview_frame is not None:
                self._extra_overview_frame.pack_forget()
                self._extra_overview_frame.pack(fill=ui.X, pady=(0, 6), before=self._regions_tree.master)
            self._task_input_container.pack_forget()
            self._extra_area_container.pack(fill=ui.X, pady=(4, 0))
            self._extra_toolbar.pack(fill=ui.X, pady=(6, 0), before=self._reading_split)
            self._save_region_button.pack_forget()
            self._save_region_button.pack(side=ui.LEFT, before=self._delete_region_button)
            return

        if mode == "naming":
            # Widgets toggled here live at the _reading_view level, as siblings
            # of self._reading_split (the canvas/editor PanedWindow, packed
            # once at construction and never forgotten). Re-packing a sibling
            # after pack_forget() without `before=` would append it AFTER an
            # already-packed self._reading_split, leaving it squeezed into no
            # visible space - every pack() call here must anchor `before=
            # self._reading_split` to land above the canvas as intended.
            self._reading_mode_title_var.set("Namen")
            self._extra_toolbar.pack_forget()
            self._mode_row.pack_forget()
            self._regions_editor.pack_forget()
            if self._extra_overview_frame is not None:
                self._extra_overview_frame.pack_forget()
            self._save_region_button.pack_forget()
            # "Einlesen abschliessen" finishes task-region marking - meaningless
            # in Namenmodus, unlike the reading_nav frame it lives in, which
            # also hosts "Zurueck zur Klausur" and stays visible in every submode.
            self._finish_reading_button.pack_forget()
            if self._naming_capture_active:
                self._reading_toolbar.pack_forget()
                self._naming_region_toolbar.pack_forget()
                self._naming_capture_panel.pack(fill=ui.BOTH, pady=(10, 0), before=self._reading_split)
            else:
                self._naming_capture_panel.pack_forget()
                self._reading_toolbar.pack(fill=ui.X, before=self._reading_split)
                self._superpage_toggle.pack_forget()
                self._superpage_toggle.pack(side=ui.RIGHT)
                self._naming_region_toolbar.pack(fill=ui.X, pady=(6, 0), before=self._reading_split)
            return

        self._reading_mode_title_var.set("Einlesen")
        self._extra_toolbar.pack_forget()
        self._reading_toolbar.pack(fill=ui.X, before=self._reading_split)
        self._superpage_toggle.pack_forget()
        self._superpage_toggle.pack(side=ui.RIGHT)
        self._mode_row.pack(fill=ui.X, pady=(8, 0), before=self._reading_split)
        self._regions_editor.pack(fill=ui.BOTH, pady=(10, 0))
        if self._extra_overview_frame is not None:
            self._extra_overview_frame.pack_forget()
        self._extra_area_container.pack_forget()
        self._task_input_container.pack(fill=ui.X)
        self._save_region_button.pack_forget()
