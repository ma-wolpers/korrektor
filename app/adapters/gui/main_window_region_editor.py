from __future__ import annotations

from app.core.domain.task_regions import tasks_of_region
from app.core.domain.task_spec import format_task_specs

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui, widgets


class MainWindowRegionEditorMixin:
    """Region-Editor: widgets, shared region tree and its selection (Zuschnitt Schritt 1 and 2).

    Superseiten (Schritt 1) and Einzelseiten (Schritt 2) share one Treeview
    (`_regions_tree`), one selection (`_selected_region_id`/
    `_selected_region_kind`: "region" or "draft"), one draft dict
    (`_draft_regions`) and one task editor; Schritt 2 adds the task
    checklist (`main_window_task_checklist.py`). Split by responsibility (file-size rule):
    this mixin builds the widgets and keeps tree and selection in sync;
    editing/saving/deleting the selected region lives in
    `MainWindowRegionFormMixin` (`main_window_region_form.py`), page
    rendering in `MainWindowPageRenderMixin` (`main_window_page_render.py`).
    """

    def _build_reading_view_mode_row(self) -> None:
        """Quick/form switch of the task editor (used in both Zuschnitt steps)."""
        self._mode_row = widgets.Frame(self._reading_view, style="Surface.TFrame")
        self._mode_row.pack(fill=ui.X, pady=(8, 0))
        widgets.Label(self._mode_row, text="Aufgaben-Eingabe:", style="Muted.TLabel").pack(side=ui.LEFT)
        widgets.Radiobutton(self._mode_row, text="Schnell (z. B. 4a-c:1,2,1)", value="quick", variable=self._assignment_mode_var).pack(side=ui.LEFT, padx=(8, 0))
        widgets.Radiobutton(self._mode_row, text="Formular", value="form", variable=self._assignment_mode_var).pack(side=ui.LEFT, padx=(8, 0))
        self._assignment_mode_var.trace_add("write", lambda *_args: self._refresh_task_input_mode())

    def _build_reading_view_region_editor(self) -> None:
        """Region list, task editor (both steps), checklist (Schritt 2) and region actions."""
        self._regions_editor = widgets.Frame(self._reading_editor_panel.content, style="Surface.TFrame")
        self._regions_editor.pack(fill=ui.BOTH, pady=(10, 0))

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

        self._build_task_checklist(self._regions_editor)

        self._region_actions = widgets.Frame(self._regions_editor, style="Surface.TFrame")
        self._region_actions.pack(fill=ui.X, pady=(6, 0))
        # Shown in Schritt 2 (Einzelseiten), where ticking tasks needs an explicit
        # commit; Enter/leaving the field commits in both steps.
        self._save_region_button = widgets.Button(
            self._region_actions,
            text="Speichern",
            style="SecondaryAction.TButton",
            command=self._commit_reading_fields_if_possible,
        )
        self._save_region_button.pack(side=ui.LEFT)
        self._attach_hover_help(self._save_region_button, label="Aufgaben des Bereichs speichern", shortcut="Enter")

        self._delete_region_button = widgets.Button(
            self._region_actions,
            text="Löschen",
            style="SecondaryAction.TButton",
            command=self._delete_selected_region,
        )
        self._delete_region_button.pack(side=ui.LEFT, padx=(8, 0))
        self._attach_hover_help(self._delete_region_button, label="Aktiven Bereich löschen", shortcut="Entf")

        redraw_region_button = widgets.Button(
            self._region_actions,
            text="Bereich neu ziehen",
            style="SecondaryAction.TButton",
            command=self._arm_redraw_selected_region,
        )
        redraw_region_button.pack(side=ui.LEFT, padx=(8, 0))
        self._attach_hover_help(
            redraw_region_button,
            label="Nächste gezogene Box überschreibt den ausgewählten Bereich",
            shortcut=None,
        )

        self._refresh_task_input_mode()

    def _region_list_scope(self) -> tuple[str, int | None]:
        """``(student_pdf, page)`` the list shows: ``("", None)`` = all Superseiten (Schritt 1), else one Einzelseite."""
        if self._extra_mode_active:
            target = self._current_extra_target()
            if target is not None:
                student, page_number = target
                return student.pdf_filename, page_number
        return "", None

    def _refresh_region_tree(self) -> None:
        """List Superseiten-Bereiche (Schritt 1) or the current Einzelseite's regions (Schritt 2), plus drafts."""
        self._region_tree_rows.clear()
        for item in self._regions_tree.get_children():
            self._regions_tree.delete(item)
        if self._current_exam is None:
            return

        student_pdf, page_number = self._region_list_scope()
        step2 = self._extra_mode_active
        for region in self._current_exam.regions:
            if region.student_pdf != student_pdf or (step2 and region.page_number != page_number):
                continue
            tasks = tasks_of_region(self._current_exam, region)
            tasks_text = format_task_specs([(task.code, task.max_points) for task in tasks]) or "-"
            row_id = self._regions_tree.insert("", ui.END, values=(self._format_area_label(region.assigned_area_codes), tasks_text, region.page_number))
            self._region_tree_rows[row_id] = ("region", region.region_id)

        for draft in self._draft_regions.values():
            if draft.student_pdf != student_pdf or (step2 and draft.page_number != page_number):
                continue
            tasks_text = format_task_specs(draft.task_specs) or "-"
            row_id = self._regions_tree.insert("", ui.END, values=(f"{self._format_area_label(draft.area_codes)}*", tasks_text, draft.page_number))
            self._region_tree_rows[row_id] = ("draft", draft.draft_id)

    def _select_region_by_id(self, region_id: str) -> None:
        for row_id, candidate in self._region_tree_rows.items():
            if candidate[1] == region_id:
                self._regions_tree.selection_set(row_id)
                self._regions_tree.focus(row_id)
                self._on_region_selected(None)
                return
