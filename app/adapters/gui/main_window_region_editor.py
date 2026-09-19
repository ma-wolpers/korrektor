from __future__ import annotations

from pathlib import Path
from typing import Sequence

import fitz

from app.adapters.gui.dialog_services import messagebox
from app.core.domain.models import StudentExam

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui, widgets


class MainWindowRegionEditorMixin:
    """Region-Editor-Mechanismus, geteilt von Reading und Extraseiten-Modus.

    Line-Budget-Split, keine Verantwortungs-Trennung (siehe Plan/ARCHITEKTUR.md):
    diese eine Datei haelt bewusst den gesamten geteilten Treeview-/Draft-/
    Rendering-Mechanismus zusammen, statt ihn nach Modus zu splitten - Reading
    und Extraseiten-Modus teilen sich einen Treeview (`_regions_tree`), eine
    Selektion (`_selected_region_id`/`_selected_region_kind`) und ein
    Draft-Dict (`_draft_regions`); ein modusbasierter Split wuerde diese
    Kopplung nur ueber mehrere Dateien verteilen statt sie zu kapseln. Die
    Widget-Konstruktion fuer genau diesen Mechanismus (`_build_reading_view_region_editor`)
    gehoert aus demselben Grund hierher, auch wenn die Datei dadurch weiter
    ueber der 300-Zeilen-Konvention liegt (siehe docs/ARCHITEKTUR.md).
    """

    def _build_reading_view_mode_row(self) -> None:
        self._mode_row = widgets.Frame(self._reading_view, style="Surface.TFrame")
        self._mode_row.pack(fill=ui.X, pady=(8, 0))
        widgets.Label(self._mode_row, text="Zuordnung:", style="Muted.TLabel").pack(side=ui.LEFT)
        widgets.Radiobutton(self._mode_row, text="Schnell (Code:Punkte)", value="quick", variable=self._assignment_mode_var).pack(side=ui.LEFT, padx=(8, 0))
        widgets.Radiobutton(self._mode_row, text="Formular", value="form", variable=self._assignment_mode_var).pack(side=ui.LEFT, padx=(8, 0))
        self._assignment_mode_var.trace_add("write", lambda *_args: self._refresh_task_input_mode())

    def _build_reading_view_region_editor(self) -> None:
        self._regions_editor = widgets.Frame(self._reading_editor_panel, style="Surface.TFrame")
        self._regions_editor.pack(fill=ui.BOTH, pady=(10, 0))

        self._extra_overview_frame = widgets.Frame(self._regions_editor, style="Surface.TFrame")
        widgets.Label(self._extra_overview_frame, text="Vorhandene Bereiche/Aufgaben", style="Muted.TLabel").pack(anchor=ui.W)
        widgets.Label(
            self._extra_overview_frame,
            textvariable=self._extra_overview_var,
            style="Muted.TLabel",
            justify=ui.LEFT,
        ).pack(anchor=ui.W, fill=ui.X, pady=(2, 0))
        self._extra_overview_frame.pack_forget()

        regions_tree_shell = widgets.Frame(self._regions_editor, style="Surface.TFrame")
        regions_tree_shell.pack(fill=ui.BOTH, expand=True)

        self._regions_tree = widgets.Treeview(
            regions_tree_shell,
            columns=("area", "tasks", "page"),
            show="headings",
            height=5,
        )
        self._regions_tree.heading("area", text="Bereich")
        self._regions_tree.heading("tasks", text="Aufgaben")
        self._regions_tree.heading("page", text="Seite")
        self._regions_tree.column("area", width=80, anchor=ui.CENTER)
        self._regions_tree.column("tasks", width=220, anchor=ui.W)
        self._regions_tree.column("page", width=80, anchor=ui.CENTER)

        regions_tree_scroll = widgets.Scrollbar(regions_tree_shell, orient=ui.VERTICAL)
        self._regions_tree.configure(yscrollcommand=regions_tree_scroll.set)
        regions_tree_scroll.configure(command=self._regions_tree.yview)
        self._regions_tree.pack(side=ui.LEFT, fill=ui.BOTH, expand=True)
        regions_tree_scroll.pack(side=ui.RIGHT, fill=ui.Y)

        self._regions_tree.bind("<<TreeviewSelect>>", self._on_region_selected)
        self.root.bind_all("<Delete>", self._on_delete_region_key)

        editor_head = widgets.Frame(self._regions_editor, style="Surface.TFrame")
        editor_head.pack(fill=ui.X, pady=(8, 4))
        widgets.Label(editor_head, text="Aktiver Bereich:", style="Muted.TLabel").pack(side=ui.LEFT)
        self._active_region_var = ui.StringVar(value="-")
        widgets.Label(editor_head, textvariable=self._active_region_var, style="Status.TLabel").pack(side=ui.LEFT, padx=(8, 0))

        self._task_input_container = widgets.Frame(self._regions_editor, style="Surface.TFrame")
        self._task_input_container.pack(fill=ui.X)

        self._quick_tasks_var = ui.StringVar(value="")
        self._quick_tasks_entry = widgets.Entry(self._task_input_container, textvariable=self._quick_tasks_var)
        self._quick_tasks_entry.pack(fill=ui.X)
        self._quick_tasks_entry.bind("<FocusOut>", self._on_reading_fields_focus_out)
        self._quick_tasks_entry.bind("<Return>", self._on_reading_fields_commit)
        self._quick_tasks_entry.bind("<Escape>", self._on_reading_fields_escape)

        self._form_tasks_text = ui.Text(self._task_input_container, height=4, wrap="word")
        # No <Return> binding here: Enter must insert a newline between tasks
        # in Formular-Modus. <FocusOut> is the commit path for this widget.
        self._form_tasks_text.bind("<FocusOut>", self._on_reading_fields_focus_out)
        self._form_tasks_text.bind("<Escape>", self._on_reading_fields_escape)

        self._task_input_example_var = ui.StringVar(value="")
        self._task_input_example_label = widgets.Label(
            self._task_input_container,
            textvariable=self._task_input_example_var,
            style="Muted.TLabel",
            justify=ui.LEFT,
        )
        self._task_input_example_label.pack(fill=ui.X, pady=(4, 0))

        self._extra_area_container = widgets.Frame(self._regions_editor, style="Surface.TFrame")
        widgets.Label(self._extra_area_container, text="Bereich(e) fuer Extraseite", style="Muted.TLabel").pack(anchor=ui.W)
        self._extra_area_codes_var = ui.StringVar(value="")
        self._extra_area_entry = widgets.Entry(self._extra_area_container, textvariable=self._extra_area_codes_var)
        self._extra_area_entry.pack(fill=ui.X, pady=(4, 0))
        self._extra_area_hint_var = ui.StringVar(value="Nur bestehende Bereiche, z. B. A,B")
        widgets.Label(
            self._extra_area_container,
            textvariable=self._extra_area_hint_var,
            style="Muted.TLabel",
            justify=ui.LEFT,
        ).pack(anchor=ui.W, pady=(4, 0))
        self._extra_area_container.pack_forget()

        region_actions = widgets.Frame(self._regions_editor, style="Surface.TFrame")
        region_actions.pack(fill=ui.X, pady=(6, 0))
        # Only shown in Extraseiten-Modus: the standard Aufgaben/Punkte editor
        # commits automatically on FocusOut (see _commit_reading_fields_if_possible).
        self._save_region_button = widgets.Button(
            region_actions,
            text="Speichern",
            style="SecondaryAction.TButton",
            command=self._save_selected_extra_region,
        )
        self._save_region_button.pack(side=ui.LEFT)
        self._attach_hover_help(self._save_region_button, label="Extraseiten-Zuordnung speichern", shortcut=None)

        self._delete_region_button = widgets.Button(
            region_actions,
            text="Loeschen",
            style="SecondaryAction.TButton",
            command=self._delete_selected_region,
        )
        self._delete_region_button.pack(side=ui.LEFT, padx=(8, 0))
        self._attach_hover_help(self._delete_region_button, label="Aktiven Bereich loeschen", shortcut="Entf")

        redraw_region_button = widgets.Button(
            region_actions,
            text="Bereich neu ziehen",
            style="SecondaryAction.TButton",
            command=self._arm_redraw_selected_region,
        )
        redraw_region_button.pack(side=ui.LEFT, padx=(8, 0))
        self._attach_hover_help(
            redraw_region_button,
            label="Naechste gezogene Box ueberschreibt den ausgewaehlten Bereich",
            shortcut=None,
        )

        self._refresh_task_input_mode()

    def _build_superposed_pixmap(
        self, *, students: Sequence[StudentExam], page_number: int, target_width: float = 520.0
    ) -> tuple[fitz.Pixmap, fitz.Rect, int] | None:
        """Composite one page across many students' PDFs into a dark-wins grayscale pixmap.

        The shared technical mechanism behind every Superseite use (Einlesemodus,
        Namenmodus region alignment, Supersymbol's filtered view): pure
        computation over "which students, which page" with no canvas/Tkinter
        side effects, so each caller can display the result on its own canvas
        with its own coordinate/scale convention (see `_render_superposed_page`
        for the Einlesemodus/Namenmodus reading-canvas display, and
        `_render_supersymbol_filtered_page` for the Korrekturmodus
        correction-canvas display - the two already use different coordinate
        systems and must not be forced to share display code, only this math).
        Returns `None` if no page of any student could be rendered.
        """
        if self._current_exam is None:
            return None

        pixmaps: list[fitz.Pixmap] = []
        reference_rect: fitz.Rect | None = None

        for student in students:
            if page_number > student.page_count:
                continue
            pdf_path = Path(self._current_exam.folder_path) / student.pdf_filename
            if not pdf_path.exists():
                continue

            document = self._doc_cache.get(student.pdf_filename)
            if document is None:
                try:
                    document = fitz.open(pdf_path)
                except Exception:
                    continue
                self._doc_cache[student.pdf_filename] = document

            try:
                page = document.load_page(page_number - 1)
            except Exception:
                continue

            if reference_rect is None:
                reference_rect = page.rect
            scale = target_width / max(reference_rect.width, 1.0)

            try:
                pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csGRAY, alpha=False)
            except Exception:
                continue

            if not pixmaps:
                pixmaps.append(pix)
                continue

            first = pixmaps[0]
            if pix.width == first.width and pix.height == first.height and pix.n == first.n:
                pixmaps.append(pix)

        if not pixmaps or reference_rect is None:
            return None

        first = pixmaps[0]
        merged = bytearray(first.width * first.height)
        for y in range(first.height):
            source_start = y * first.stride
            target_start = y * first.width
            merged[target_start : target_start + first.width] = first.samples[source_start : source_start + first.width]

        for pix in pixmaps[1:]:
            for y in range(pix.height):
                source_start = y * pix.stride
                target_start = y * pix.width
                row = pix.samples[source_start : source_start + pix.width]
                for x, value in enumerate(row):
                    index = target_start + x
                    if value < merged[index]:
                        merged[index] = value

        merged_pixmap = fitz.Pixmap(fitz.csGRAY, first.width, first.height, bytes(merged), False)
        # Keep the PPM/PhotoImage encoding local to callers (each targets a
        # different Tkinter Canvas) - return the raw merged pixmap, the
        # reference page rect callers need for their own scale-factor math,
        # and the number of students actually merged into it (for "Quellen: N").
        return merged_pixmap, reference_rect, len(pixmaps)

    @staticmethod
    def _wheel_direction(event: ui.Event[ui.Misc]) -> int:
        if getattr(event, "num", None) == 4:
            return 1
        if getattr(event, "num", None) == 5:
            return -1
        delta = getattr(event, "delta", 0)
        if delta > 0:
            return 1
        if delta < 0:
            return -1
        return 0

    def _render_pdf_page(self, *, student: StudentExam, page_number: int) -> None:
        if self._current_exam is None:
            return

        pdf_path = Path(self._current_exam.folder_path) / student.pdf_filename
        if not pdf_path.exists():
            self._reading_info_var.set(f"Datei fehlt: {student.pdf_filename}")
            self._reading_canvas.delete("all")
            return

        document = self._doc_cache.get(student.pdf_filename)
        if document is None:
            document = fitz.open(pdf_path)
            self._doc_cache[student.pdf_filename] = document

        try:
            page = document.load_page(page_number - 1)
            page_rect = page.rect
            target_width = 520.0
            scale = target_width / max(page_rect.width, 1.0)
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)

            self._x_factor = page_rect.width / max(pix.width, 1)
            self._y_factor = page_rect.height / max(pix.height, 1)

            self._render_photo = ui.PhotoImage(data=pix.tobytes("ppm"), format="ppm")
            self._reading_canvas.configure(width=pix.width, height=pix.height)
            self._reading_canvas.delete("all")
            self._canvas_image_id = self._reading_canvas.create_image(0, 0, anchor=ui.NW, image=self._render_photo)
            self._reading_canvas.configure(scrollregion=(0, 0, pix.width, pix.height))
        except Exception as exc:
            self._reading_canvas.delete("all")
            self._reading_info_var.set(f"Fehler beim PDF-Rendering: {exc}")
            return

        self._draw_existing_regions(student.pdf_filename, page_number)

    def _refresh_extra_overview(self) -> None:
        if not self._extra_mode_active:
            self._extra_overview_var.set("")
            return

        area_tasks = self._build_standard_area_task_map()
        if not area_tasks:
            self._extra_overview_var.set("Noch keine Standardbereiche vorhanden.")
            return

        lines = [
            f"{area_code}: {self._format_task_specs_text(task_specs)}"
            for area_code, task_specs in sorted(area_tasks.items())
        ]
        self._extra_overview_var.set("\n".join(lines))

    def _refresh_region_tree(self) -> None:
        self._region_tree_rows.clear()
        for item in self._regions_tree.get_children():
            self._regions_tree.delete(item)

        if self._current_exam is None:
            self._extra_overview_var.set("")
            return

        self._refresh_extra_overview()

        if self._extra_mode_active and self._extra_sequence:
            student_index, page_number = self._extra_sequence[self._extra_cursor]
            student_pdf = self._current_exam.students[student_index].pdf_filename
            for assignment in self._current_exam.extra_page_assignments:
                if assignment.student_pdf != student_pdf or assignment.page_number != page_number:
                    continue
                area = self._format_area_label(assignment.assigned_area_codes)
                row_id = self._regions_tree.insert(
                    "",
                    ui.END,
                    values=(area, self._format_tasks_for_areas(assignment.assigned_area_codes), assignment.page_number),
                )
                self._region_tree_rows[row_id] = ("extra", assignment.assignment_id)
        else:
            for region in self._current_exam.regions:
                area = self._format_area_label(region.assigned_area_codes)
                tasks_text = self._format_task_specs_text([(task.code, task.max_points) for task in region.tasks])
                row_id = self._regions_tree.insert(
                    "",
                    ui.END,
                    values=(area, tasks_text, region.page_number),
                )
                self._region_tree_rows[row_id] = ("region", region.region_id)

        for draft in self._draft_regions.values():
            if self._extra_mode_active and self._extra_sequence:
                student_index, page_number = self._extra_sequence[self._extra_cursor]
                student_pdf = self._current_exam.students[student_index].pdf_filename
                if draft.student_pdf != student_pdf or draft.page_number != page_number:
                    continue
            elif draft.student_pdf:
                continue
            area = self._format_area_label(draft.area_codes)
            tasks_text = (
                self._format_tasks_for_areas(draft.area_codes)
                if self._extra_mode_active
                else self._format_task_specs_text(draft.task_specs)
            )
            row_id = self._regions_tree.insert(
                "",
                ui.END,
                values=(f"{area}*", tasks_text, draft.page_number),
            )
            self._region_tree_rows[row_id] = ("draft", draft.draft_id)

    def _select_region_by_id(self, region_id: str) -> None:
        for row_id, candidate in self._region_tree_rows.items():
            if candidate[1] == region_id:
                self._regions_tree.selection_set(row_id)
                self._regions_tree.focus(row_id)
                self._on_region_selected(None)
                return

    def _on_region_selected(self, _event: object) -> None:
        if self._current_exam is None:
            return
        selection = self._regions_tree.selection()
        if not selection:
            self._selected_region_id = None
            self._selected_region_kind = None
            self._active_region_var.set("-")
            return

        row_value = self._region_tree_rows.get(selection[0])
        if row_value is None:
            return
        kind, region_id = row_value
        self._selected_region_kind = kind

        if kind == "draft":
            draft = self._draft_regions.get(region_id)
            if draft is None:
                return
            self._selected_region_id = draft.draft_id
            area = draft.area_codes[0] if draft.area_codes else "-"
            self._active_region_var.set(f"{area} (Draft)")
            if self._extra_mode_active:
                self._extra_area_codes_var.set(",".join(code.strip().upper() for code in draft.area_codes if code.strip()))
                self._rerender_active_page()
                return
            quick_text = ";".join(f"{code}:{points:g}" for code, points in draft.task_specs)
            form_text = "\n".join(f"{code}:{points:g}" for code, points in draft.task_specs)
            self._quick_tasks_var.set(quick_text)
            self._form_tasks_text.delete("1.0", ui.END)
            self._form_tasks_text.insert("1.0", form_text)
            self._rerender_active_page()
            return

        if kind == "extra":
            assignment = next(
                (item for item in self._current_exam.extra_page_assignments if item.assignment_id == region_id),
                None,
            )
            if assignment is None:
                return
            self._selected_region_id = assignment.assignment_id
            area = assignment.assigned_area_codes[0] if assignment.assigned_area_codes else "-"
            self._active_region_var.set(area)
            self._extra_area_codes_var.set(",".join(code.strip().upper() for code in assignment.assigned_area_codes if code.strip()))
            self._rerender_active_page()
            return

        region = next((item for item in self._current_exam.regions if item.region_id == region_id), None)
        if region is None:
            return

        self._selected_region_id = region_id
        area = region.assigned_area_codes[0] if region.assigned_area_codes else "-"
        self._active_region_var.set(area)
        if self._extra_mode_active:
            self._extra_area_codes_var.set(",".join(code.strip().upper() for code in region.assigned_area_codes if code.strip()))
            self._rerender_active_page()
            return

        quick_text = ";".join(f"{task.code}:{task.max_points:g}" for task in region.tasks)
        form_text = "\n".join(f"{task.code}:{task.max_points:g}" for task in region.tasks)
        self._quick_tasks_var.set(quick_text)
        self._form_tasks_text.delete("1.0", ui.END)
        self._form_tasks_text.insert("1.0", form_text)
        self._rerender_active_page()

    def _commit_reading_fields_if_possible(self) -> None:
        """Persist the Aufgaben/Punkte editor's current content, if any is selected.

        This is the single commit path for the Einlesemodus task/points
        editor (`_quick_tasks_entry`/`_form_tasks_text`) — it runs on
        <FocusOut> and <Return>, replacing the former manual "Speichern"
        button for this editor. Extraseiten-Zuordnung uses its own, separate
        `_save_selected_extra_region` (still triggered via a visible button).
        """
        if self._extra_mode_active:
            return
        if self._current_exam is None or self._selected_region_id is None or self._controller is None:
            return

        task_specs = self._read_task_specs_from_editor()
        if task_specs is None:
            return

        region = next((item for item in self._current_exam.regions if item.region_id == self._selected_region_id), None)
        if region is not None:
            updated = self._controller.upsert_region_immediate(
                exam=self._current_exam,
                student_pdf="",
                page_number=region.page_number,
                box=(region.box.x0, region.box.y0, region.box.x1, region.box.y1),
                task_specs=task_specs,
                area_codes=region.assigned_area_codes,
                region_id=region.region_id,
            )
            if updated is None:
                return
            self._current_exam = updated
            self._refresh_region_tree()
            self._select_region_by_id(region.region_id)
            self._apply_detail_labels(updated)
            self._rerender_active_page()
            return

        draft = self._draft_regions.get(self._selected_region_id)
        if draft is None:
            return

        if not task_specs:
            messagebox.showerror("Ungültige Eingabe", "Bitte mindestens eine Aufgabe mit Code und Punkten angeben.")
            return

        before_ids = {region.region_id for region in self._current_exam.regions}

        updated = self._controller.upsert_region_immediate(
            exam=self._current_exam,
            student_pdf="",
            page_number=draft.page_number,
            box=draft.box,
            task_specs=task_specs,
            area_codes=draft.area_codes,
        )
        if updated is None:
            return
        persisted_id = next(
            (
                region.region_id
                for region in reversed(updated.regions)
                if region.region_id not in before_ids
            ),
            None,
        )

        del self._draft_regions[draft.draft_id]
        self._current_exam = updated
        self._refresh_region_tree()
        if persisted_id:
            self._select_region_by_id(persisted_id)
        self._apply_detail_labels(updated)
        self._rerender_active_page()

    def _save_selected_extra_region(self) -> None:
        if self._current_exam is None or self._selected_region_id is None or self._controller is None:
            return

        area_codes = [code.strip().upper() for code in self._extra_area_codes_var.get().split(",") if code.strip()]
        if not area_codes:
            messagebox.showerror("Ungültige Eingabe", "Bitte mindestens einen bestehenden Bereich angeben, z. B. A.")
            return

        draft = self._draft_regions.get(self._selected_region_id)
        if draft is not None:
            before_ids = {assignment.assignment_id for assignment in self._current_exam.extra_page_assignments}
            updated = self._controller.assign_extra_page_immediate(
                exam=self._current_exam,
                student_pdf=draft.student_pdf,
                page_number=draft.page_number,
                box=draft.box,
                area_codes=area_codes,
            )
            if updated is None:
                return
            persisted_id = next(
                (
                    assignment.assignment_id
                    for assignment in reversed(updated.extra_page_assignments)
                    if assignment.assignment_id not in before_ids
                ),
                None,
            )
            del self._draft_regions[draft.draft_id]
            self._current_exam = updated
            self._refresh_region_tree()
            if persisted_id:
                self._select_region_by_id(persisted_id)
            self._apply_detail_labels(updated)
            self._rerender_active_page()
            return

        assignment = next(
            (item for item in self._current_exam.extra_page_assignments if item.assignment_id == self._selected_region_id),
            None,
        )
        if assignment is None:
            return
        updated = self._controller.assign_extra_page_immediate(
            exam=self._current_exam,
            student_pdf=assignment.student_pdf,
            page_number=assignment.page_number,
            box=(assignment.box.x0, assignment.box.y0, assignment.box.x1, assignment.box.y1),
            area_codes=area_codes,
        )
        if updated is None:
            return
        self._current_exam = updated
        self._refresh_region_tree()
        self._select_region_by_id(assignment.assignment_id)
        self._apply_detail_labels(updated)
        self._rerender_active_page()

    def _delete_selected_region(self) -> None:
        if self._current_exam is None or self._selected_region_id is None:
            return

        if self._selected_region_id in self._draft_regions:
            del self._draft_regions[self._selected_region_id]
            self._selected_region_id = None
            self._selected_region_kind = None
            self._active_region_var.set("-")
            self._quick_tasks_var.set("")
            self._form_tasks_text.delete("1.0", ui.END)
            self._refresh_region_tree()
            self._rerender_active_page()
            return

        if self._controller is None:
            return

        if self._selected_region_kind == "extra":
            updated = self._controller.delete_extra_page_assignment_immediate(
                exam=self._current_exam,
                assignment_id=self._selected_region_id,
            )
        else:
            updated = self._controller.delete_region_immediate(exam=self._current_exam, region_id=self._selected_region_id)
        self._current_exam = updated

        self._selected_region_id = None
        self._selected_region_kind = None
        self._active_region_var.set("-")
        self._quick_tasks_var.set("")
        self._form_tasks_text.delete("1.0", ui.END)
        self._refresh_region_tree()
        self._apply_detail_labels(self._current_exam)
        self._rerender_active_page()

    def _on_delete_region_key(self, _event: ui.Event[ui.Misc]) -> None:
        if self._active_view == "correction" and self._correction_mode_active:
            self._delete_selected_correction_annotation()
            return
        self._delete_selected_region()
