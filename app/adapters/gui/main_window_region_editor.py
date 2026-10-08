from __future__ import annotations

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui, widgets


class MainWindowRegionEditorMixin:
    """Region-Editor: widgets, shared region tree and its selection (Zuschnitt and Extraseiten).

    Zuschnitt and Extraseiten share one Treeview (`_regions_tree`), one
    selection (`_selected_region_id`/`_selected_region_kind`) and one draft
    dict (`_draft_regions`). Split by responsibility (file-size rule):
    this mixin builds the widgets and keeps tree and selection in sync;
    editing/saving/deleting the selected region lives in
    `MainWindowRegionFormMixin` (`main_window_region_form.py`), page
    rendering in `MainWindowPageRenderMixin` (`main_window_page_render.py`).
    """

    def _build_reading_view_mode_row(self) -> None:
        self._mode_row = widgets.Frame(self._reading_view, style="Surface.TFrame")
        self._mode_row.pack(fill=ui.X, pady=(8, 0))
        widgets.Label(self._mode_row, text="Zuordnung:", style="Muted.TLabel").pack(side=ui.LEFT)
        widgets.Radiobutton(self._mode_row, text="Schnell (Code:Punkte)", value="quick", variable=self._assignment_mode_var).pack(side=ui.LEFT, padx=(8, 0))
        widgets.Radiobutton(self._mode_row, text="Formular", value="form", variable=self._assignment_mode_var).pack(side=ui.LEFT, padx=(8, 0))
        self._assignment_mode_var.trace_add("write", lambda *_args: self._refresh_task_input_mode())

    def _build_reading_view_region_editor(self) -> None:
        self._regions_editor = widgets.Frame(self._reading_editor_panel.content, style="Surface.TFrame")
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
