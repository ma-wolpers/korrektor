from __future__ import annotations

from app.adapters.gui.dialog_services import messagebox
from app.core.domain.models import ExamProject, StudentExam
from app.core.domain.task_spec import main_task_of

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui, widgets


class MainWindowCorrectionCoreMixin:
    """Correction view: header/actions, task-centric navigation (↑/↓ subtask, Strg+↑/↓ main task, ←/→ person).

    Rendering of the stacked regions lives in `MainWindowCorrectionSegmentsMixin`
    (`main_window_correction_segments.py`).
    """

    def _build_correction_view_canvas_header(self) -> None:
        """Title, status line and the action row (back, task combo, max points, zoom) of the correction view."""
        widgets.Label(self._correction_view, text="Korrektur", style="Title.TLabel").pack(anchor=ui.W)
        self._correction_info_var = ui.StringVar(value="Korrektur: nicht aktiv")
        widgets.Label(self._correction_view, textvariable=self._correction_info_var, style="Muted.TLabel").pack(anchor=ui.W, pady=(4, 8))

        correction_actions = widgets.Frame(self._correction_view, style="Surface.TFrame")
        correction_actions.pack(fill=ui.X, pady=(0, 8))

        correction_back_button = widgets.Button(
            correction_actions,
            text="Zurück zur Klausur",
            style="SecondaryAction.TButton",
            command=self._stop_correction_mode,
        )
        correction_back_button.pack(side=ui.LEFT)
        self._attach_hover_help(correction_back_button, label="Korrekturansicht verlassen", shortcut="Esc")

        widgets.Label(correction_actions, text="Aufgabe", style="Muted.TLabel").pack(side=ui.LEFT, padx=(14, 4))
        self._correction_task_var = ui.StringVar(value="")
        self._correction_task_combo = widgets.Combobox(
            correction_actions,
            textvariable=self._correction_task_var,
            state="readonly",
            width=20,
            values=(),
        )
        self._correction_task_combo.pack(side=ui.LEFT)
        self._correction_task_combo.bind("<<ComboboxSelected>>", self._on_correction_task_changed)

        self._correction_max_points_var = ui.StringVar(value="Max: -")
        widgets.Label(correction_actions, textvariable=self._correction_max_points_var, style="Status.TLabel").pack(side=ui.LEFT, padx=(12, 0))

        correction_zoom_actions = widgets.Frame(correction_actions, style="Surface.TFrame")
        correction_zoom_actions.pack(side=ui.RIGHT)
        widgets.Label(correction_zoom_actions, textvariable=self._correction_zoom_info_var, style="Muted.TLabel").pack(side=ui.RIGHT, padx=(8, 0))
        reset_correction_zoom_button = widgets.Button(
            correction_zoom_actions,
            text="100%",
            style="SecondaryAction.TButton",
            command=self._reset_correction_zoom,
        )
        reset_correction_zoom_button.pack(side=ui.RIGHT)
        self._attach_hover_help(reset_correction_zoom_button, label="Korrektur-Zoom auf 100% setzen", shortcut="Strg+0")

        zoom_in_correction_button = widgets.Button(
            correction_zoom_actions,
            text="+",
            style="SecondaryAction.TButton",
            command=lambda: self._change_correction_zoom(10),
            width=3,
        )
        zoom_in_correction_button.pack(side=ui.RIGHT, padx=(8, 0))
        self._attach_hover_help(zoom_in_correction_button, label="Korrektur-Zoom vergrößern", shortcut="Strg++")

        zoom_out_correction_button = widgets.Button(
            correction_zoom_actions,
            text="-",
            style="SecondaryAction.TButton",
            command=lambda: self._change_correction_zoom(-10),
            width=3,
        )
        zoom_out_correction_button.pack(side=ui.RIGHT, padx=(8, 0))
        self._attach_hover_help(zoom_out_correction_button, label="Korrektur-Zoom verkleinern", shortcut="Strg+-")

    def _build_correction_view_form_save_nav(self) -> None:
        correction_buttons = widgets.Frame(self._correction_form_panel.content, style="Surface.TFrame")
        correction_buttons.pack(fill=ui.X, pady=(10, 0))

        save_comments_button = widgets.Button(
            correction_buttons,
            text="Alle PDFs überschreiben",
            style="SecondaryAction.TButton",
            command=self._save_correction_annotations_to_pdfs,
        )
        save_comments_button.pack(side=ui.LEFT)
        self._attach_hover_help(save_comments_button, label="Alle Original-PDFs dieser Klausur mit ihren Markierungen überschreiben")

        prev_correction_student_button = widgets.Button(
            correction_buttons,
            text="◀ Person",
            style="SecondaryAction.TButton",
            command=lambda: self._change_correction_student(-1),
        )
        prev_correction_student_button.pack(side=ui.RIGHT)
        self._attach_hover_help(prev_correction_student_button, label="Vorherige Person in Korrektur", shortcut="Links")

        next_correction_student_button = widgets.Button(
            correction_buttons,
            text="Person ▶",
            style="SecondaryAction.TButton",
            command=lambda: self._change_correction_student(1),
        )
        next_correction_student_button.pack(side=ui.RIGHT, padx=(0, 8))
        self._attach_hover_help(next_correction_student_button, label="Nächste Person in Korrektur", shortcut="Rechts")

    def _start_correction_mode(self) -> None:
        """Enter the task-centric correction: one (sub)task at a time, all its regions stacked."""
        if not self._current_exam:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Klausur öffnen.")
            return
        if not self._current_exam.tasks:
            messagebox.showinfo("Keine Aufgaben", "Bitte zuerst im Zuschnitt Bereiche mit Aufgaben festlegen.")
            return
        indices = list(range(len(self._current_exam.students)))
        if not indices:
            messagebox.showinfo("Keine Fälle", "Diese Klausur enthält keine Schüler:innen.")
            return
        self._refresh_correction_start_choices(self._current_exam)
        start_code = self._correction_start_task_var.get().strip().upper()

        self._reading_active = False
        self._extra_mode_active = False
        self._extra_sequence = []
        self._close_extra_popup()
        self._correction_mode_active = True
        self._correction_zoom_percent = 100
        self._refresh_correction_zoom_label()
        self._correction_selected_annotation_id = None
        self._correction_drag_annotation_id = None
        self._correction_drag_offset_pdf = None
        self._correction_templates = self._build_correction_templates(self._current_exam)
        self._correction_student_indices = indices
        self._correction_cursor = 0
        self._student_cursor = indices[0]
        self._correction_task_items = [(task.code, float(task.max_points)) for task in self._current_exam.tasks]
        labels = tuple(f"{code} ({max_points:g} P.)" for code, max_points in self._correction_task_items)
        self._correction_task_combo["values"] = labels
        self._correction_task_var.set(next((label for label in labels if label.startswith(f"{start_code} ")), labels[0]))
        self._set_correction_marker_tool(self._correction_marker_tool_key)
        self._show_view("correction")
        self._refresh_active_student_label()
        self._on_correction_task_switched()
        self._focus_first_input_field()
        self._status_var.set(f"Korrektur aktiv ab Aufgabe {self._selected_correction_task()[0]}")

    def _stop_correction_mode(self, *, silent: bool = False) -> None:
        """Leave the correction view, clearing templates, segments and any Supersymbol/Superposition state."""
        self._commit_points_if_possible()
        self._correction_mode_active = False
        self._correction_templates = {}
        self._correction_task_items = []
        self._correction_student_indices = []
        self._correction_cursor = 0
        self._correction_segments = []
        self._correction_photos = []
        self._correction_selected_annotation_id = None
        self._correction_drag_annotation_id = None
        self._correction_drag_offset_pdf = None
        self._correction_annotation_items.clear()
        if self._supersymbol_filter_active or self._superposition_mode is not None:
            self._supersymbol_filter_active = False
            self._supersymbol_matched_student_ids = []
            self._superposition_mode = None
            self._superposition_task_codes = []
            self._supersymbol_preview_button.configure(state="normal")
            self._supersymbol_cancel_button.pack_forget()
            self._supersymbol_info_var.set("")
        self._correction_finished_var.set(False)
        self._correction_finished_all_var.set(False)
        self._refresh_correction_completion_controls()
        self._close_extra_popup()
        self._refresh_active_student_label()
        self._show_detail_mode()
        if not silent:
            self._status_var.set("Korrektur beendet")

    def _refresh_correction_start_choices(self, exam: ExamProject) -> None:
        """Task combo of the detail view's "Schnellkorrektur": the start task (all tasks, natural order)."""
        codes = [task.code for task in exam.tasks] or ["-"]
        self._correction_start_task_combo["values"] = tuple(codes)
        if self._correction_start_task_var.get() not in codes:
            self._correction_start_task_var.set(codes[0])

    def _on_correction_task_switched(self) -> None:
        """A new current task: drop stale Supersymbol state, reload points/comment, re-render all its regions."""
        self._correction_selected_annotation_id = None
        self._cancel_supersymbol_filter()
        self._refresh_supersymbol_scope_choices(self._current_correction_template())
        self._refresh_correction_task_meta(load_saved_points=True)
        self._render_correction_preview()
        self._refresh_correction_completion_controls()

    def _refresh_correction_task_meta(self, *, load_saved_points: bool) -> None:
        """Show max points of the current task and (optionally) the person's saved points and comment."""
        task_code, max_points = self._selected_correction_task()
        if task_code is None:
            self._correction_max_points_var.set("Max: -")
            if load_saved_points:
                self._correction_points_var.set("")
                self._correction_comment_var.set("")
            self._refresh_correction_completion_controls()
            return

        self._correction_max_points_var.set(f"Max: {max_points:g}")
        if not load_saved_points or self._controller is None or self._current_exam is None:
            return
        student = self._current_correction_student()
        if student is None:
            return
        existing_points = self._controller.load_saved_points(exam=self._current_exam, student_id=student.student_id, task_code=task_code)
        existing_comment = self._controller.load_saved_comment(exam=self._current_exam, student_id=student.student_id, task_code=task_code)
        self._correction_points_var.set(existing_points if existing_points is not None else "")
        self._correction_comment_var.set(existing_comment if existing_comment is not None else "")
        self._refresh_correction_completion_controls()

    def _cycle_combobox_value(self, combo: widgets.Combobox, value_var: ui.StringVar, delta: int) -> bool:
        """Select the next/previous value of ``combo`` (wrapping); ``False`` if it has no values."""
        values = tuple(str(item) for item in combo.cget("values"))
        if not values:
            return False
        current = value_var.get()
        current_index = values.index(current) if current in values else 0
        value_var.set(values[(current_index + delta) % len(values)])
        return True

    def _cycle_correction_task(self, delta: int) -> None:
        """↑/↓: previous/next (sub)task (4A -> 4B -> ... -> 5A), wrapping around."""
        if not self._correction_mode_active:
            return
        self._save_current_correction_score()
        self._save_current_correction_comment()
        if self._cycle_combobox_value(self._correction_task_combo, self._correction_task_var, delta):
            self._on_correction_task_switched()
            self._focus_first_input_field()

    def _cycle_correction_main_task(self, delta: int) -> None:
        """Strg+↑/↓: first subtask of the next/previous main task (4B -> 5A; ↑ from 5B -> 4A), wrapping around."""
        if not self._correction_mode_active or not self._correction_task_items:
            return
        code, _max_points = self._selected_correction_task()
        codes = [item[0] for item in self._correction_task_items]
        mains = list(dict.fromkeys(main_task_of(item) for item in codes))
        current = mains.index(main_task_of(code)) if code is not None else 0
        target = mains[(current + delta) % len(mains)]
        first = next(item for item in codes if main_task_of(item) == target)
        self._save_current_correction_score()
        self._save_current_correction_comment()
        labels = tuple(str(item) for item in self._correction_task_combo.cget("values"))
        self._correction_task_var.set(labels[codes.index(first)])
        self._on_correction_task_switched()
        self._focus_first_input_field()

    def _current_correction_student(self) -> StudentExam | None:
        """The person currently shown in the correction view, or ``None``."""
        if not self._current_exam or not self._correction_student_indices:
            return None
        index = self._correction_student_indices[self._correction_cursor]
        return self._current_exam.students[index]

    def _selected_correction_task(self) -> tuple[str | None, float]:
        """``(code, max_points)`` of the task chosen in the combo, or ``(None, 0.0)``."""
        selected = self._correction_task_var.get().strip()
        for code, max_points in self._correction_task_items:
            if selected.startswith(f"{code} ") or selected == code:
                return code, max_points
        return None, 0.0

    def _change_correction_student(self, delta: int) -> None:
        """←/→: next/previous person (same task), cancelling any Supersymbol filter."""
        if not self._correction_mode_active or not self._correction_student_indices:
            return
        self._cancel_supersymbol_filter()
        self._save_current_correction_score()
        self._save_current_correction_comment()
        self._correction_cursor = (self._correction_cursor + delta) % len(self._correction_student_indices)
        self._student_cursor = self._correction_student_indices[self._correction_cursor]
        self._correction_selected_annotation_id = None
        self._refresh_active_student_label()
        self._refresh_correction_task_meta(load_saved_points=True)
        self._render_correction_preview()
        self._refresh_correction_completion_controls()
        self._focus_first_input_field()
