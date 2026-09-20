from __future__ import annotations

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui, widgets


class MainWindowCorrectionFormMixin:
    def _build_correction_view_form_points_comment(self) -> None:
        correction_form = widgets.Frame(self._correction_form_panel.content, style="Surface.TFrame")
        correction_form.pack(fill=ui.X, pady=(8, 0))
        correction_form.columnconfigure(1, weight=1)
        correction_form.columnconfigure(2, weight=0)

        widgets.Label(correction_form, text="Erreichte Punkte", style="Muted.TLabel").grid(
            row=0,
            column=0,
            sticky=ui.W,
            padx=(0, 6),
            pady=4,
        )
        self._correction_points_var = ui.StringVar(value="")
        self._correction_points_entry = widgets.Entry(correction_form, textvariable=self._correction_points_var)
        self._correction_points_entry.grid(row=0, column=1, sticky=ui.EW, pady=4)
        self._correction_points_entry.bind("<FocusOut>", self._on_correction_points_focus_out)
        self._correction_points_entry.bind("<Return>", self._on_correction_points_commit)
        self._correction_points_entry.bind("<Escape>", self._on_correction_points_escape)

        widgets.Label(correction_form, text="Kommentar", style="Muted.TLabel").grid(
            row=1,
            column=0,
            sticky=ui.W,
            padx=(0, 6),
            pady=4,
        )
        self._correction_comment_entry = widgets.Entry(correction_form, textvariable=self._correction_comment_var)
        self._correction_comment_entry.grid(row=1, column=1, sticky=ui.EW, pady=4)
        self._correction_comment_entry.bind("<FocusOut>", self._on_correction_comment_focus_out)
        self._correction_comment_entry.bind("<Return>", self._on_correction_comment_commit)
        self._correction_comment_entry.bind("<Escape>", self._on_correction_comment_escape)

        insert_comment_button = widgets.Button(
            correction_form,
            text="Einfuegen",
            style="SecondaryAction.TButton",
            command=self._insert_current_comment_into_preview_center,
        )
        insert_comment_button.grid(row=1, column=2, padx=(8, 0), sticky=ui.E)
        self._attach_hover_help(insert_comment_button, label="Kommentar in der Vorschau-Mitte einfuegen")

        self._correction_form_frame = correction_form

    def _save_current_correction_score(self) -> bool:
        if not self._correction_mode_active or self._controller is None or self._current_exam is None:
            return False
        if self._is_current_person_area_finished():
            return False
        student = self._current_correction_student()
        if student is None:
            return False
        task_code, max_points = self._selected_correction_task()
        if task_code is None:
            return False
        saved = self._controller.save_score_immediate(
            exam=self._current_exam,
            student_id=student.student_id,
            task_code=task_code,
            points_text=self._correction_points_var.get(),
            max_points_text=f"{max_points:g}",
        )
        self._refresh_correction_completion_controls()
        return saved

    def _save_current_correction_comment(self) -> bool:
        if not self._correction_mode_active or self._controller is None or self._current_exam is None:
            return False
        student = self._current_correction_student()
        if student is None:
            return False
        task_code, _max_points = self._selected_correction_task()
        if task_code is None:
            return False
        updated = self._controller.set_task_comment_immediate(
            exam=self._current_exam,
            student_id=student.student_id,
            task_code=task_code,
            comment_text=self._correction_comment_var.get(),
        )
        if updated is None:
            return False
        self._current_exam = updated
        self._apply_detail_labels(updated)
        return True

    def _on_correction_area_changed(self, _event: ui.Event[ui.Misc]) -> None:
        if not self._correction_mode_active:
            return
        self._save_current_correction_score()
        self._save_current_correction_comment()
        self._correction_selected_annotation_id = None
        self._refresh_correction_task_choices(load_saved_points=True)
        self._refresh_correction_completion_controls()
        self._focus_first_input_field()

    def _on_correction_task_changed(self, _event: ui.Event[ui.Misc]) -> None:
        if not self._correction_mode_active:
            return
        self._save_current_correction_score()
        self._save_current_correction_comment()
        self._correction_selected_annotation_id = None
        self._refresh_correction_task_meta(load_saved_points=True)
        self._refresh_correction_completion_controls()
        self._focus_first_input_field()

    def _on_correction_points_focus_out(self, _event: ui.Event[ui.Misc]) -> None:
        self._save_current_correction_score()

    def _on_correction_points_commit(self, _event: ui.Event[ui.Misc]) -> None:
        self._save_current_correction_score()
        self.root.focus_set()

    def _on_correction_points_escape(self, _event: ui.Event[ui.Misc]) -> None:
        self._save_current_correction_score()
        self.root.focus_set()

    def _on_correction_comment_focus_out(self, _event: ui.Event[ui.Misc]) -> None:
        self._save_current_correction_comment()

    def _on_correction_comment_commit(self, _event: ui.Event[ui.Misc]) -> None:
        self._save_current_correction_comment()
        self.root.focus_set()

    def _on_correction_comment_escape(self, _event: ui.Event[ui.Misc]) -> None:
        self._save_current_correction_comment()
        self.root.focus_set()
