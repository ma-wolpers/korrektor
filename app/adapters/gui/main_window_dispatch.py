from __future__ import annotations

from app.core.domain.models import StudentExam
from bw_gui.contracts.hsm import ESCAPE_CLOSE_POPUP, ESCAPE_EXIT_INLINE_EDITOR, ESCAPE_POP_PARENT

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui, widgets


class MainWindowDispatchMixin:
    def _on_escape(self, _event: ui.Event[ui.Misc]) -> None:
        """Resolve one Escape press via the HSM contract: close popup, leave an inline
        editor/active mode (reading, extra, naming, correction), or pop back to the overview."""
        self._sync_popup_sessions_from_windows()
        widget = self.root.focus_get()
        action = self._hsm_contract.resolve_escape_action(
            has_popup=self._popup_registry.has_active_popup(),
            has_inline_editor=isinstance(widget, (ui.Entry, widgets.Entry))
            or self._correction_mode_active
            or self._reading_active
            or self._extra_mode_active
            or self._naming_mode_active,
            has_parent_state=self._current_exam is not None,
        )

        if action == ESCAPE_CLOSE_POPUP:
            active_popup = self._popup_registry.active_popup()
            if active_popup is not None:
                popup_id = active_popup.popup_id
                for child in self.root.winfo_children():
                    if not isinstance(child, ui.Toplevel):
                        continue
                    if str(child) != popup_id:
                        continue
                    try:
                        child.destroy()
                    except Exception:
                        pass
                    break
                self._popup_registry.close_popup(popup_id)
                self._tracked_popup_ids.discard(popup_id)
                return

        if action == ESCAPE_EXIT_INLINE_EDITOR:
            if isinstance(widget, (ui.Entry, widgets.Entry)):
                self.root.focus_set()
                return

            if self._correction_mode_active:
                self._stop_correction_mode()
                return

            if self._reading_active or self._extra_mode_active or self._naming_mode_active:
                self._leave_reading_view()
                return

        if action != ESCAPE_POP_PARENT or self._current_exam is None:
            self._status_var.set("Bereits in Gesamtübersicht")
            return

        self._current_exam = None
        self._detail_name.set("-")
        self._detail_pages.set("Standardseiten: -")
        self._detail_students.set("Schüler:innen: -")
        self._detail_regions.set("Fertig korrigiert -")
        self._detail_status.set("Status: -")
        self._active_student.set("Aktive Person: -")
        self._reading_active = False
        self._extra_mode_active = False
        self._extra_sequence = []
        self._naming_mode_active = False
        self._naming_capture_active = False
        self._pending_student_names.clear()
        self._correction_mode_active = False
        self._correction_student_indices = []
        self._reading_info_var.set("Einlesemodus: nicht aktiv")
        self._draft_regions.clear()
        self._reading_canvas.delete("all")
        self._hide_correction_controls()
        self._close_extra_popup()
        self._return_to_overview()

    def _on_points_focus_out(self, _event: ui.Event[ui.Misc]) -> None:
        self._commit_points_if_possible()

    def _on_points_commit(self, _event: ui.Event[ui.Misc]) -> None:
        self._commit_points_if_possible()
        self.root.focus_set()

    def _on_points_escape(self, _event: ui.Event[ui.Misc]) -> None:
        self._commit_points_if_possible()
        self.root.focus_set()

    def _on_reading_fields_focus_out(self, _event: ui.Event[ui.Misc]) -> None:
        """Commit the Aufgaben/Punkte editor when it loses focus."""
        self._commit_reading_fields_if_possible()

    def _on_reading_fields_commit(self, _event: ui.Event[ui.Misc]) -> None:
        """Commit the Aufgaben/Punkte editor on <Return> and leave the field."""
        self._commit_reading_fields_if_possible()
        self.root.focus_set()

    def _on_reading_fields_escape(self, _event: ui.Event[ui.Misc]) -> None:
        """Leave the Aufgaben/Punkte editor on <Escape> without a direct commit.

        No commit call here: leaving the field triggers <FocusOut>, which is
        the single commit path (see _commit_reading_fields_if_possible).
        """
        self.root.focus_set()

    def _on_left_key(self, _event: ui.Event[ui.Misc]) -> None:
        """Dispatch Left to the active mode's "previous" action (student/page)."""
        if self._is_editable_widget(self.root.focus_get()) and not (
            (self._active_view == "correction" and self._correction_mode_active)
            or (self._active_view == "reading" and self._detail_submode == "naming" and self._naming_capture_active)
        ):
            return
        if self._active_view == "correction" and self._correction_mode_active:
            self._change_correction_student(-1)
            return
        if self._active_view == "reading" and self._detail_submode == "naming" and self._naming_capture_active:
            self._change_naming_student(-1)
            return
        if self._active_view == "reading" and self._detail_submode == "extra" and self._extra_mode_active:
            self._change_extra_page(-1)
            return
        if self._active_view == "reading" and self._detail_submode in {"reading", "naming"} and self._reading_active:
            self._change_reading_page(-1)
            return
        self._move_student(-1)

    def _on_right_key(self, _event: ui.Event[ui.Misc]) -> None:
        """Dispatch Right to the active mode's "next" action (student/page)."""
        if self._is_editable_widget(self.root.focus_get()) and not (
            (self._active_view == "correction" and self._correction_mode_active)
            or (self._active_view == "reading" and self._detail_submode == "naming" and self._naming_capture_active)
        ):
            return
        if self._active_view == "correction" and self._correction_mode_active:
            self._change_correction_student(1)
            return
        if self._active_view == "reading" and self._detail_submode == "naming" and self._naming_capture_active:
            self._change_naming_student(1)
            return
        if self._active_view == "reading" and self._detail_submode == "extra" and self._extra_mode_active:
            self._change_extra_page(1)
            return
        if self._active_view == "reading" and self._detail_submode in {"reading", "naming"} and self._reading_active:
            self._change_reading_page(1)
            return
        self._move_student(1)

    def _on_up_key(self, _event: ui.Event[ui.Misc]) -> None:
        if self._is_editable_widget(self.root.focus_get()) and not (
            self._active_view == "correction" and self._correction_mode_active
        ):
            return
        if self._active_view == "correction" and self._correction_mode_active:
            self._cycle_correction_task(-1)

    def _on_down_key(self, _event: ui.Event[ui.Misc]) -> None:
        if self._is_editable_widget(self.root.focus_get()) and not (
            self._active_view == "correction" and self._correction_mode_active
        ):
            return
        if self._active_view == "correction" and self._correction_mode_active:
            self._cycle_correction_task(1)

    def _on_ctrl_up_key(self, _event: ui.Event[ui.Misc]) -> None:
        if self._is_editable_widget(self.root.focus_get()) and not (
            self._active_view == "correction" and self._correction_mode_active
        ):
            return
        if self._active_view == "correction" and self._correction_mode_active:
            self._cycle_correction_area(-1)

    def _on_ctrl_down_key(self, _event: ui.Event[ui.Misc]) -> None:
        if self._is_editable_widget(self.root.focus_get()) and not (
            self._active_view == "correction" and self._correction_mode_active
        ):
            return
        if self._active_view == "correction" and self._correction_mode_active:
            self._cycle_correction_area(1)

    def _on_ctrl_space_key(self, _event: ui.Event[ui.Misc]):
        if self._active_view != "correction" or not self._correction_mode_active:
            return None
        if self._correction_finished_check is None:
            return "break"
        if str(self._correction_finished_check.cget("state")) == "disabled":
            return "break"
        self._correction_finished_var.set(not bool(self._correction_finished_var.get()))
        self._on_correction_finished_toggled()
        return "break"

    def _on_ctrl_e_key(self, _event: ui.Event[ui.Misc]):
        self._menu_export_scores()
        return "break"

    def _on_ctrl_plus_key(self, _event: ui.Event[ui.Misc]):
        if self._active_view != "correction" or not self._correction_mode_active:
            return None
        self._change_correction_zoom(10)
        return "break"

    def _on_ctrl_minus_key(self, _event: ui.Event[ui.Misc]):
        if self._active_view != "correction" or not self._correction_mode_active:
            return None
        self._change_correction_zoom(-10)
        return "break"

    def _on_ctrl_zero_key(self, _event: ui.Event[ui.Misc]):
        if self._active_view != "correction" or not self._correction_mode_active:
            return None
        self._reset_correction_zoom()
        return "break"

    def _on_ctrl_c_key(self, _event: ui.Event[ui.Misc]):
        if self._active_view != "correction" or not self._correction_mode_active:
            return None
        self._copy_selected_correction_annotation()
        return "break"

    def _on_ctrl_x_key(self, _event: ui.Event[ui.Misc]):
        if self._active_view != "correction" or not self._correction_mode_active:
            return None
        self._cut_selected_correction_annotation()
        return "break"

    def _on_ctrl_v_key(self, _event: ui.Event[ui.Misc]):
        if self._active_view != "correction" or not self._correction_mode_active:
            return None
        self._paste_correction_annotation()
        return "break"

    def _commit_points_if_possible(self) -> None:
        if self._correction_mode_active:
            self._save_current_correction_score()
            self._save_current_correction_comment()
            return
        if not self._controller or not self._current_exam or not self._current_exam.students:
            return
        student = self._current_exam.students[self._student_cursor]
        self._controller.save_score_immediate(
            exam=self._current_exam,
            student_id=student.student_id,
            task_code=self._task_code_var.get(),
            points_text=self._points_var.get(),
            max_points_text=self._max_points_var.get(),
        )

    def _current_canvas_context(self) -> tuple[StudentExam, int] | None:
        if self._current_exam is None:
            return None
        if self._extra_mode_active and self._extra_sequence:
            student_index, page_number = self._extra_sequence[self._extra_cursor]
            return self._current_exam.students[student_index], page_number
        student = self._get_reading_student()
        if student is None:
            return None
        return student, self._reading_page

    def _rerender_active_page(self) -> None:
        if self._extra_mode_active:
            self._render_current_extra_page()
            return
        self._render_current_reading_page()
