from __future__ import annotations

from uuid import uuid4

from app.adapters.gui.dialog_services import messagebox
from app.adapters.gui.main_window_types import DraftRegion

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui, widgets


class MainWindowReadingCanvasMixin:
    def _build_reading_view_canvas(self) -> None:
        self._reading_split = widgets.PanedWindow(self._reading_view, orient=ui.HORIZONTAL)
        self._reading_split.pack(fill=ui.BOTH, expand=True, pady=(10, 0))

        canvas_panel = widgets.Frame(self._reading_split, style="Surface.TFrame", padding=(0, 0, 8, 0))
        self._reading_editor_panel = widgets.Frame(self._reading_split, style="Surface.TFrame", padding=(8, 0, 0, 0))
        self._reading_split.add(canvas_panel, weight=3)
        self._reading_split.add(self._reading_editor_panel, weight=2)

        canvas_container = widgets.Frame(canvas_panel, style="Surface.TFrame")
        canvas_container.pack(fill=ui.BOTH, expand=True)

        canvas_scroll_x = widgets.Scrollbar(canvas_container, orient=ui.HORIZONTAL)
        canvas_scroll_y = widgets.Scrollbar(canvas_container, orient=ui.VERTICAL)

        canvas_bg, canvas_border = self._canvas_theme_tokens()
        self._reading_canvas = ui.Canvas(
            canvas_container,
            width=520,
            height=360,
            bg=canvas_bg,
            highlightthickness=1,
            highlightbackground=canvas_border,
            xscrollcommand=canvas_scroll_x.set,
            yscrollcommand=canvas_scroll_y.set,
        )
        canvas_scroll_x.config(command=self._reading_canvas.xview)
        canvas_scroll_y.config(command=self._reading_canvas.yview)

        canvas_scroll_x.pack(side=ui.BOTTOM, fill=ui.X)
        canvas_scroll_y.pack(side=ui.RIGHT, fill=ui.Y)
        self._reading_canvas.pack(side=ui.LEFT, fill=ui.BOTH, expand=True)
        self._reading_canvas.bind("<ButtonPress-1>", self._on_canvas_press)
        self._reading_canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self._reading_canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self._reading_canvas.bind("<MouseWheel>", self._on_canvas_mousewheel)
        self._reading_canvas.bind("<Shift-MouseWheel>", self._on_canvas_shift_mousewheel)

    def _draw_existing_regions(self, student_pdf: str, page_number: int) -> None:
        """Draw the persisted region(s) for the current mode: name_region in Namenmodus,
        extra-page/task regions plus open drafts otherwise."""
        if not self._current_exam:
            return

        if self._naming_mode_active and not self._naming_capture_active:
            region = self._current_exam.name_region
            if region is not None and self._current_exam.name_region_page == page_number:
                x0 = region.x0 / self._x_factor
                y0 = region.y0 / self._y_factor
                x1 = region.x1 / self._x_factor
                y1 = region.y1 / self._y_factor
                self._reading_canvas.create_rectangle(
                    x0, y0, x1, y1, outline="#8b5cf6", width=3, tags=("region", "name_region"),
                )
            return

        if self._extra_mode_active:
            for assignment in self._current_exam.extra_page_assignments:
                if assignment.student_pdf != student_pdf or assignment.page_number != page_number:
                    continue
                x0 = assignment.box.x0 / self._x_factor
                y0 = assignment.box.y0 / self._y_factor
                x1 = assignment.box.x1 / self._x_factor
                y1 = assignment.box.y1 / self._y_factor
                is_selected = (
                    self._selected_region_kind == "extra"
                    and assignment.assignment_id == self._selected_region_id
                )
                rect_id = self._reading_canvas.create_rectangle(
                    x0,
                    y0,
                    x1,
                    y1,
                    outline="#d17a00" if is_selected else "#0b8f59",
                    width=3 if is_selected else 2,
                    tags=("region", f"extra:{assignment.assignment_id}"),
                )
                self._reading_canvas.tag_bind(rect_id, "<Button-1>", self._on_canvas_region_click)
        else:
            for region in self._current_exam.regions:
                if region.page_number != page_number:
                    continue
                x0 = region.box.x0 / self._x_factor
                y0 = region.box.y0 / self._y_factor
                x1 = region.box.x1 / self._x_factor
                y1 = region.box.y1 / self._y_factor
                is_selected = (
                    self._selected_region_kind == "region"
                    and region.region_id == self._selected_region_id
                )
                rect_id = self._reading_canvas.create_rectangle(
                    x0,
                    y0,
                    x1,
                    y1,
                    outline="#d17a00" if is_selected else "#0b8f59",
                    width=3 if is_selected else 2,
                    tags=("region", f"region:{region.region_id}"),
                )
                self._reading_canvas.tag_bind(rect_id, "<Button-1>", self._on_canvas_region_click)

        for draft in self._draft_regions.values():
            if self._extra_mode_active:
                if draft.student_pdf != student_pdf or draft.page_number != page_number:
                    continue
            else:
                if draft.student_pdf:
                    continue
                if draft.page_number != page_number:
                    continue
            x0 = draft.box[0] / self._x_factor
            y0 = draft.box[1] / self._y_factor
            x1 = draft.box[2] / self._x_factor
            y1 = draft.box[3] / self._y_factor
            is_selected = self._selected_region_kind == "draft" and draft.draft_id == self._selected_region_id
            rect_id = self._reading_canvas.create_rectangle(
                x0,
                y0,
                x1,
                y1,
                outline="#d17a00" if is_selected else "#1f6feb",
                dash=(4, 2),
                width=3 if is_selected else 2,
                tags=("region", f"draft:{draft.draft_id}"),
            )
            self._reading_canvas.tag_bind(rect_id, "<Button-1>", self._on_canvas_region_click)

    def _on_canvas_region_click(self, event: ui.Event[ui.Misc]) -> None:
        current = self._reading_canvas.find_withtag("current")
        if not current:
            return
        tags = self._reading_canvas.gettags(current[0])
        region_tag = next(
            (tag for tag in tags if tag.startswith("region:") or tag.startswith("extra:") or tag.startswith("draft:")),
            None,
        )
        if region_tag is None:
            return
        region_id = region_tag.split(":", 1)[1]
        self._select_region_by_id(region_id)
        self._rerender_active_page()

    def _on_canvas_press(self, event: ui.Event[ui.Misc]) -> None:
        if not self._reading_active and not self._extra_mode_active:
            return
        x = float(self._reading_canvas.canvasx(event.x))
        y = float(self._reading_canvas.canvasy(event.y))
        self._drag_start = (x, y)
        if self._drag_rect_id is not None:
            self._reading_canvas.delete(self._drag_rect_id)
        self._drag_rect_id = self._reading_canvas.create_rectangle(
            x,
            y,
            x,
            y,
            outline="#1f6feb",
            width=2,
        )

    def _on_canvas_drag(self, event: ui.Event[ui.Misc]) -> None:
        if self._drag_start is None or self._drag_rect_id is None:
            return
        x0, y0 = self._drag_start
        x1 = float(self._reading_canvas.canvasx(event.x))
        y1 = float(self._reading_canvas.canvasy(event.y))
        self._reading_canvas.coords(self._drag_rect_id, x0, y0, x1, y1)

    def _on_canvas_release(self, event: ui.Event[ui.Misc]) -> None:
        """Finish a canvas drag: commit a pending redraw, or create a new draft region.

        After creating a new standard (non-extra) draft, focus moves straight
        into the Aufgaben/Punkte editor (`_focus_reading_task_input`) so the
        drawn region's tasks/points can be typed without an extra click.
        """
        if (not self._reading_active and not self._extra_mode_active) or self._drag_start is None:
            return
        if self._drag_rect_id is None:
            self._drag_start = None
            return

        x0, y0 = self._drag_start
        x1 = float(self._reading_canvas.canvasx(event.x))
        y1 = float(self._reading_canvas.canvasy(event.y))
        if abs(x1 - x0) < 5 or abs(y1 - y0) < 5:
            self._reading_canvas.delete(self._drag_rect_id)
            self._drag_rect_id = None
            self._drag_start = None
            return

        context = self._current_canvas_context()
        if context is None:
            self._reading_canvas.delete(self._drag_rect_id)
            self._drag_rect_id = None
            self._drag_start = None
            return
        student, page_number = context

        box = (
            min(x0, x1) * self._x_factor,
            min(y0, y1) * self._y_factor,
            max(x0, x1) * self._x_factor,
            max(y0, y1) * self._y_factor,
        )

        if self._try_apply_pending_redraw(student_pdf=student.pdf_filename, page_number=page_number, box=box):
            self._reading_canvas.delete(self._drag_rect_id)
            self._drag_rect_id = None
            self._drag_start = None
            self._rerender_active_page()
            return

        if self._naming_mode_active and not self._naming_capture_active:
            self._commit_name_region_from_drag(box=box, page_number=page_number)
            return

        draft_id = f"draft-{uuid4().hex[:10]}"
        draft_student_pdf = student.pdf_filename if self._extra_mode_active else ""
        draft = DraftRegion(
            draft_id=draft_id,
            student_pdf=draft_student_pdf,
            page_number=page_number,
            box=box,
            area_codes=[self._next_area_label()],
            task_specs=[],
        )
        self._draft_regions[draft_id] = draft

        self._selected_region_id = draft_id
        self._selected_region_kind = "draft"
        self._active_region_var.set("Draft")
        self._quick_tasks_var.set("")
        self._form_tasks_text.delete("1.0", ui.END)
        self._refresh_region_tree()
        self._select_region_by_id(draft_id)

        self._rerender_active_page()
        self._drag_rect_id = None
        self._drag_start = None
        if self._extra_mode_active:
            self._status_var.set("Extraseiten-Bereich markiert. Bereich(e) eintragen und Speichern klicken.")
        else:
            self._status_var.set("Bereich markiert. Aufgaben eintragen - wird beim Verlassen des Feldes gespeichert.")
            self._focus_reading_task_input()

    def _arm_redraw_selected_region(self) -> None:
        if self._selected_region_id is None or self._selected_region_kind not in {"region", "extra"}:
            messagebox.showinfo("Hinweis", "Bitte zuerst einen bestehenden Bereich auswaehlen (kein Draft).")
            return
        if self._extra_mode_active and self._selected_region_kind != "extra":
            messagebox.showinfo("Hinweis", "Im Extraseitenmodus kann nur eine Extraseiten-Zuordnung neu gezogen werden.")
            return
        if not self._extra_mode_active and self._selected_region_kind != "region":
            messagebox.showinfo("Hinweis", "Im Einlesemodus kann nur ein Standardbereich neu gezogen werden.")
            return
        self._redraw_target_region_kind = self._selected_region_kind
        self._redraw_target_region_id = self._selected_region_id
        self._redraw_on_next_box = True
        self._status_var.set("Neuziehen aktiv: Die naechste gezogene Box ueberschreibt den ausgewaehlten Bereich.")

    def _clear_pending_redraw(self) -> None:
        self._redraw_target_region_kind = None
        self._redraw_target_region_id = None
        self._redraw_on_next_box = False

    def _try_apply_pending_redraw(
        self,
        *,
        student_pdf: str,
        page_number: int,
        box: tuple[float, float, float, float],
    ) -> bool:
        if not self._redraw_on_next_box or self._redraw_target_region_id is None:
            return False
        if self._controller is None or self._current_exam is None:
            self._clear_pending_redraw()
            return False

        if self._redraw_target_region_kind == "extra":
            assignment = next(
                (item for item in self._current_exam.extra_page_assignments if item.assignment_id == self._redraw_target_region_id),
                None,
            )
            if assignment is None:
                self._clear_pending_redraw()
                messagebox.showerror("Bereich fehlt", "Die ausgewaehlte Extraseiten-Zuordnung konnte nicht gefunden werden.")
                return False

            updated = self._controller.assign_extra_page_immediate(
                exam=self._current_exam,
                student_pdf=student_pdf,
                page_number=page_number,
                box=box,
                area_codes=assignment.assigned_area_codes,
                assignment_id=assignment.assignment_id,
            )
            self._clear_pending_redraw()
            if updated is None:
                return True

            self._current_exam = updated
            self._refresh_region_tree()
            self._select_region_by_id(assignment.assignment_id)
            self._apply_detail_labels(updated)
            area_text = assignment.assigned_area_codes[0] if assignment.assigned_area_codes else assignment.assignment_id
            self._status_var.set(f"Extraseiten-Bereich {area_text} neu gezogen und ueberschrieben.")
            return True

        region = next(
            (item for item in self._current_exam.regions if item.region_id == self._redraw_target_region_id),
            None,
        )
        if region is None:
            self._clear_pending_redraw()
            messagebox.showerror("Bereich fehlt", "Der ausgewaehlte Bereich konnte nicht mehr gefunden werden.")
            return False

        task_specs = [(task.code, float(task.max_points)) for task in region.tasks]
        updated = self._controller.upsert_region_immediate(
            exam=self._current_exam,
            student_pdf="",
            page_number=page_number,
            box=box,
            task_specs=task_specs,
            area_codes=region.assigned_area_codes,
            region_id=region.region_id,
        )
        self._clear_pending_redraw()
        if updated is None:
            return True

        self._current_exam = updated
        self._refresh_region_tree()
        self._select_region_by_id(region.region_id)
        self._apply_detail_labels(updated)
        area_text = region.assigned_area_codes[0] if region.assigned_area_codes else region.region_id
        self._status_var.set(f"Bereich {area_text} neu gezogen und ueberschrieben.")
        return True

    def _on_canvas_mousewheel(self, event: ui.Event[ui.Misc]) -> None:
        if not self._reading_active and not self._extra_mode_active:
            return
        step = int(-1 * (event.delta / 120)) if event.delta else 0
        if step:
            self._reading_canvas.yview_scroll(step, "units")

    def _on_canvas_shift_mousewheel(self, event: ui.Event[ui.Misc]) -> None:
        if not self._reading_active and not self._extra_mode_active:
            return
        step = int(-1 * (event.delta / 120)) if event.delta else 0
        if step:
            self._reading_canvas.xview_scroll(step, "units")
