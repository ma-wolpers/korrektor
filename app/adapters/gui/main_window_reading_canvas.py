from __future__ import annotations

from uuid import uuid4

from app.adapters.gui.main_window_types import DraftRegion

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui, widgets
from bw_gui.widgets import ScrollableFrame


class MainWindowReadingCanvasMixin:
    def _build_reading_view_canvas(self) -> None:
        self._reading_split = widgets.PanedWindow(self._reading_view, orient=ui.HORIZONTAL)
        self._reading_split.pack(fill=ui.BOTH, expand=True, pady=(10, 0))

        canvas_panel = widgets.Frame(self._reading_split, style="Surface.TFrame", padding=(0, 0, 8, 0))
        # ScrollableFrame (bw-gui scroll SSOT, see bw-gui/docs/SCROLLABILITY_CONTRACT.md):
        # same rationale as the Korrekturmodus form panel
        # (main_window_correction_markers.py) - this pane hosts the
        # Regionen-Editor across Einlesemodus/Extraseiten/Namenmodus and
        # can outgrow its available height with many regions/tasks.
        self._reading_editor_panel = ScrollableFrame(self._reading_split, style="Surface.TFrame", padding=(8, 0, 0, 0))
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
        """Draw the regions of this page plus open drafts (the name field lives in the naming window).

        Schritt 1: Superseiten-Bereiche (editable). Schritt 2: the student's
        Einzelseiten-Bereiche (editable) and - when the page also carries
        Superseiten-Bereiche - those in grey, not selectable, so it is
        visible where they lie.
        """
        if not self._current_exam:
            return
        step2 = self._extra_mode_active
        for region in self._current_exam.regions:
            if region.page_number != page_number:
                continue
            if region.student_pdf and (not step2 or region.student_pdf != student_pdf):
                continue
            coords = (region.box.x0 / self._x_factor, region.box.y0 / self._y_factor, region.box.x1 / self._x_factor, region.box.y1 / self._y_factor)
            if step2 and not region.student_pdf:
                self._reading_canvas.create_rectangle(*coords, outline="#9ca3af", dash=(3, 3), width=2, tags=("superseite",))
                label = region.assigned_area_codes[0] if region.assigned_area_codes else ""
                self._reading_canvas.create_text(coords[0] + 4, coords[1] + 4, anchor=ui.NW, text=f"{label} (Superseite)", fill="#6b7280")
                continue
            is_selected = self._selected_region_kind == "region" and region.region_id == self._selected_region_id
            rect_id = self._reading_canvas.create_rectangle(
                *coords,
                outline="#d17a00" if is_selected else "#0b8f59",
                width=3 if is_selected else 2,
                tags=("region", f"region:{region.region_id}"),
            )
            self._reading_canvas.tag_bind(rect_id, "<Button-1>", self._on_canvas_region_click)

        for draft in self._draft_regions.values():
            if draft.page_number != page_number or draft.student_pdf != (student_pdf if step2 else ""):
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
        """Click on a drawn region or draft: select it in the list (grey Superseiten-Bereiche in Schritt 2 are not clickable)."""
        current = self._reading_canvas.find_withtag("current")
        if not current:
            return
        tags = self._reading_canvas.gettags(current[0])
        region_tag = next(
            (tag for tag in tags if tag.startswith("region:") or tag.startswith("draft:")),
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

        After creating a new draft (both steps), focus moves straight
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
            self._status_var.set("Einzelseiten-Bereich markiert. Aufgaben eintippen oder anhaken – Enter oder „Speichern“ übernimmt.")
        else:
            self._status_var.set("Bereich markiert. Aufgaben eintragen - wird beim Verlassen des Feldes gespeichert.")
        self._focus_reading_task_input()

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
