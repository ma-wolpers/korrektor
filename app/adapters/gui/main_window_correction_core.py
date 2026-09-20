from __future__ import annotations

from pathlib import Path

import fitz

from app.adapters.gui.dialog_services import messagebox
from app.adapters.gui.main_window_types import CorrectionTemplate
from app.core.domain.models import ExamProject, StudentExam, TaskDefinition

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui, widgets


class MainWindowCorrectionCoreMixin:
    def _build_correction_view_canvas_header(self) -> None:
        widgets.Label(self._correction_view, text="Korrektur", style="Title.TLabel").pack(anchor=ui.W)
        self._correction_info_var = ui.StringVar(value="Korrektur: nicht aktiv")
        widgets.Label(self._correction_view, textvariable=self._correction_info_var, style="Muted.TLabel").pack(anchor=ui.W, pady=(4, 8))

        correction_actions = widgets.Frame(self._correction_view, style="Surface.TFrame")
        correction_actions.pack(fill=ui.X, pady=(0, 8))

        correction_back_button = widgets.Button(
            correction_actions,
            text="Zurueck zur Klausur",
            style="SecondaryAction.TButton",
            command=self._stop_correction_mode,
        )
        correction_back_button.pack(side=ui.LEFT)
        self._attach_hover_help(correction_back_button, label="Korrekturansicht verlassen", shortcut="Esc")

        widgets.Label(correction_actions, text="Bereich", style="Muted.TLabel").pack(side=ui.LEFT, padx=(14, 4))
        self._correction_area_combo_view = widgets.Combobox(
            correction_actions,
            textvariable=self._correction_area_var,
            state="readonly",
            width=10,
            values=("A",),
        )
        self._correction_area_combo_view.pack(side=ui.LEFT)
        self._correction_area_combo_view.bind("<<ComboboxSelected>>", self._on_correction_area_changed)

        widgets.Label(correction_actions, text="Aufgabe", style="Muted.TLabel").pack(side=ui.LEFT, padx=(12, 4))
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
        self._attach_hover_help(zoom_in_correction_button, label="Korrektur-Zoom vergroessern", shortcut="Strg++")

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
        correction_buttons = widgets.Frame(self._correction_form_panel, style="Surface.TFrame")
        correction_buttons.pack(fill=ui.X, pady=(10, 0))

        save_comments_button = widgets.Button(
            correction_buttons,
            text="Alle PDFs ueberschreiben",
            style="SecondaryAction.TButton",
            command=self._save_correction_annotations_to_pdfs,
        )
        save_comments_button.pack(side=ui.LEFT)
        self._attach_hover_help(save_comments_button, label="Alle Original-PDFs dieser Klausur mit ihren Markierungen ueberschreiben")

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
        self._attach_hover_help(next_correction_student_button, label="Naechste Person in Korrektur", shortcut="Rechts")

    def _start_correction_mode(self) -> None:
        """Enter Korrekturmodus, building the region_id-keyed templates/label map."""
        if not self._current_exam:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Klausur öffnen.")
            return
        templates = self._build_correction_templates(self._current_exam)
        if not templates:
            messagebox.showinfo("Keine Bereiche", "Bitte zuerst Standardbereiche im Einlesemodus markieren und speichern.")
            return
        label_to_region_id = self._build_label_to_region_id_map(templates)

        area = self._correction_area_var.get().strip().upper()
        if area not in label_to_region_id:
            area = sorted(label_to_region_id.keys())[0]
            self._correction_area_var.set(area)

        indices = list(range(len(self._current_exam.students)))
        if not indices:
            messagebox.showinfo("Keine Fälle", "Diese Klausur enthält keine Schüler:innen.")
            return

        self._reading_active = False
        self._extra_mode_active = False
        self._extra_sequence = []
        self._naming_mode_active = False
        self._naming_capture_active = False
        self._close_extra_popup()
        self._correction_mode_active = True
        self._correction_zoom_percent = 100
        self._refresh_correction_zoom_label()
        self._correction_selected_annotation_id = None
        self._correction_drag_annotation_id = None
        self._correction_drag_offset_pdf = None
        self._correction_templates = templates
        self._correction_label_to_region_id = label_to_region_id
        self._correction_student_indices = indices
        self._correction_cursor = 0
        self._student_cursor = indices[0]
        self._set_correction_marker_tool(self._correction_marker_tool_key)
        self._show_view("correction")
        self._refresh_active_student_label()
        self._refresh_correction_task_choices(load_saved_points=True)
        self._refresh_correction_completion_controls()
        self._focus_first_input_field()
        self._status_var.set(f"Korrekturmodus aktiv für Bereich {area}")

    def _stop_correction_mode(self, *, silent: bool = False) -> None:
        """Leave Korrekturmodus, clearing the region templates and label map."""
        self._commit_points_if_possible()
        self._correction_mode_active = False
        self._correction_templates = {}
        self._correction_label_to_region_id = {}
        self._correction_task_items = []
        self._correction_student_indices = []
        self._correction_cursor = 0
        self._correction_clip_box = None
        self._correction_scale = 1.0
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
            self._status_var.set("Korrekturmodus beendet")

    @staticmethod
    def _build_correction_templates(exam: ExamProject) -> dict[str, CorrectionTemplate]:
        """Build one `CorrectionTemplate` per region, keyed by `region_id`.

        Assumes `exam` already passed `validate_regions` (unique, non-empty
        `region_id`s and `assigned_area_codes[0]` labels) — this no longer
        needs to defend against duplicate labels by dropping regions, since
        that is now rejected earlier, at load time.
        """
        templates: dict[str, CorrectionTemplate] = {}
        ordered_regions = sorted(
            (region for region in exam.regions if region.assigned_area_codes),
            key=lambda item: (item.assigned_area_codes[0], item.page_number, item.region_id),
        )
        for region in ordered_regions:
            area_code = region.assigned_area_codes[0].strip().upper()
            if not area_code or region.region_id in templates:
                continue
            templates[region.region_id] = CorrectionTemplate(
                region_id=region.region_id,
                area_code=area_code,
                page_number=region.page_number,
                box=(region.box.x0, region.box.y0, region.box.x1, region.box.y1),
                tasks=[TaskDefinition(code=task.code, name=task.name, max_points=task.max_points) for task in region.tasks],
            )
        return templates

    @staticmethod
    def _build_label_to_region_id_map(templates: dict[str, CorrectionTemplate]) -> dict[str, str]:
        """Map each region's visible `area_code` label to its `region_id` key.

        The Bereich-Auswahl UI (`_correction_area_var`) still operates on
        labels; this is the single place that resolves a label back to the
        `region_id` used to look regions up in `templates`. The result is
        cached on `self._correction_label_to_region_id`.
        """
        return {template.area_code: region_id for region_id, template in templates.items()}

    def _refresh_correction_task_choices(self, *, load_saved_points: bool) -> None:
        """Refresh the task combobox/Supersymbol scope for the selected Bereich.

        Cancels any active Supersymbol filter first, since it was computed
        for the previous Bereich's tasks and would otherwise go stale.
        """
        template = self._current_correction_template()
        self._cancel_supersymbol_filter()
        self._refresh_supersymbol_scope_choices(template)
        if template is None:
            self._correction_task_items = []
            self._correction_selected_annotation_id = None
            self._correction_task_combo["values"] = ()
            self._correction_task_var.set("")
            self._correction_max_points_var.set("Max: -")
            self._correction_points_var.set("")
            self._correction_comment_var.set("")
            self._render_correction_preview()
            return

        self._correction_task_items = [(task.code, float(task.max_points)) for task in template.tasks]
        labels = tuple(f"{code} ({max_points:g})" for code, max_points in self._correction_task_items)
        self._correction_task_combo["values"] = labels
        if labels:
            current = self._correction_task_var.get()
            if current not in labels:
                self._correction_task_var.set(labels[0])
        else:
            self._correction_task_var.set("")
        self._refresh_correction_task_meta(load_saved_points=load_saved_points)
        self._render_correction_preview()
        self._refresh_correction_completion_controls()

    def _refresh_correction_task_meta(self, *, load_saved_points: bool) -> None:
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
        existing_points = self._controller.load_saved_points(
            exam=self._current_exam,
            student_id=student.student_id,
            task_code=task_code,
        )
        existing_comment = self._controller.load_saved_comment(
            exam=self._current_exam,
            student_id=student.student_id,
            task_code=task_code,
        )
        self._correction_points_var.set(existing_points if existing_points is not None else "")
        self._correction_comment_var.set(existing_comment if existing_comment is not None else "")
        self._refresh_correction_completion_controls()

    def _cycle_combobox_value(self, combo: widgets.Combobox, value_var: ui.StringVar, delta: int) -> bool:
        values = tuple(str(item) for item in combo.cget("values"))
        if not values:
            return False
        current = value_var.get()
        if current in values:
            current_index = values.index(current)
        else:
            current_index = 0
        value_var.set(values[(current_index + delta) % len(values)])
        return True

    def _cycle_correction_task(self, delta: int) -> None:
        if not self._correction_mode_active:
            return
        self._save_current_correction_score()
        self._save_current_correction_comment()
        if not self._cycle_combobox_value(self._correction_task_combo, self._correction_task_var, delta):
            return
        self._correction_selected_annotation_id = None
        self._refresh_correction_task_meta(load_saved_points=True)
        self._focus_first_input_field()

    def _cycle_correction_area(self, delta: int) -> None:
        if not self._correction_mode_active:
            return
        self._save_current_correction_score()
        self._save_current_correction_comment()
        if not self._cycle_combobox_value(self._correction_area_combo_view, self._correction_area_var, delta):
            return
        self._correction_selected_annotation_id = None
        self._refresh_correction_task_choices(load_saved_points=True)
        self._focus_first_input_field()

    def _current_correction_student(self) -> StudentExam | None:
        if not self._current_exam or not self._correction_student_indices:
            return None
        index = self._correction_student_indices[self._correction_cursor]
        return self._current_exam.students[index]

    def _selected_correction_task(self) -> tuple[str | None, float]:
        selected = self._correction_task_var.get().strip()
        for code, max_points in self._correction_task_items:
            if selected.startswith(f"{code} ") or selected == code:
                return code, max_points
        return None, 0.0

    def _current_correction_template(self) -> CorrectionTemplate | None:
        """Resolve the currently selected Bereich label to its CorrectionTemplate.

        `_correction_templates` is keyed by `region_id`; `_correction_area_var`
        holds the visible `area_code` label, so the lookup goes through
        `_correction_label_to_region_id` first.
        """
        area_code = self._correction_area_var.get().strip().upper()
        region_id = self._correction_label_to_region_id.get(area_code)
        if region_id is None:
            return None
        return self._correction_templates.get(region_id)

    def _render_correction_preview(self) -> None:
        """Render the current student's region clip and refresh the status line."""
        if self._current_exam is None:
            return
        student = self._current_correction_student()
        template = self._current_correction_template()
        if student is None or template is None:
            self._correction_canvas.delete("all")
            self._correction_clip_box = None
            self._correction_info_var.set("Korrektur: keine Daten")
            return

        pdf_path = Path(self._current_exam.folder_path) / student.pdf_filename
        if not pdf_path.exists():
            self._correction_canvas.delete("all")
            self._correction_clip_box = None
            self._correction_info_var.set(f"Datei fehlt: {student.pdf_filename}")
            return

        document = self._doc_cache.get(student.pdf_filename)
        if document is None:
            document = fitz.open(pdf_path)
            self._doc_cache[student.pdf_filename] = document

        try:
            page = document.load_page(template.page_number - 1)
            page_rect = page.rect
            clip = fitz.Rect(*template.box)
            clip = clip.intersect(page_rect)
            if clip.is_empty:
                clip = page_rect
            target_width = 560.0
            scale = (target_width / max(clip.width, 1.0)) * (self._correction_zoom_percent / 100.0)
            try:
                pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=clip, alpha=False, annots=False)
            except TypeError:
                pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=clip, alpha=False)
            self._correction_clip_box = (float(clip.x0), float(clip.y0), float(clip.x1), float(clip.y1))
            self._correction_scale = scale
            self._correction_photo = ui.PhotoImage(data=pix.tobytes("ppm"), format="ppm")
            self._correction_canvas.delete("all")
            self._correction_canvas.create_image(0, 0, anchor=ui.NW, image=self._correction_photo)
            self._correction_canvas.configure(scrollregion=(0, 0, pix.width, pix.height))
            self._render_correction_annotations()
            self._correction_info_var.set(
                f"Bereich {template.area_code} | {student.display_name} ({self._correction_cursor + 1}/{len(self._correction_student_indices)}) | Seite {template.page_number}"
            )
        except Exception as exc:
            self._correction_canvas.delete("all")
            self._correction_clip_box = None
            self._correction_info_var.set(f"Fehler beim Korrektur-Rendering: {exc}")

    def _change_correction_student(self, delta: int) -> None:
        """Move to the next/previous correction student, cancelling any Supersymbol filter."""
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
