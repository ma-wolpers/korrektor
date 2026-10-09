from __future__ import annotations

from app.core.domain.task_spec import TaskSpec, format_task_specs, parse_task_specs, task_sort_key

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui, widgets
from bw_gui.widgets import Checkbox, ScrollableFrame


class TaskChecklistRejected(Exception):
    """Raised from a checkbox callback so bw-gui rolls the tick back (the text could not be parsed)."""


class MainWindowTaskChecklistMixin:
    """Zuschnitt Schritt 2: tick existing tasks for the selected Einzelseiten-Bereich.

    Contract (binding, A1): the task **text field is the only draft state**;
    the checklist is a view on it. A tick parses the current text; if that
    fails, the text is left untouched, the tick rolls back and a hint is
    shown. Otherwise only the ticked code is added (without points) or
    removed - every other entry, including new codes with points such as
    ``7A:2`` and points of existing codes, stays - and the text is rewritten
    with `format_task_specs`. Nothing is saved: Enter, leaving the field or
    "Speichern" commits, exactly as in Schritt 1. The checkboxes are bw-gui
    `Checkbox`es (staged selection: their callback only changes local
    presentation state).
    """

    def _build_task_checklist(self, parent) -> None:
        """Create the (initially hidden) checklist frame below the task editor."""
        self._task_checklist_frame = widgets.Frame(parent, style="Surface.TFrame")
        widgets.Label(self._task_checklist_frame, text="Vorhandene Aufgaben anhaken:", style="Muted.TLabel").pack(anchor=ui.W)
        self._task_checklist_scroll = ScrollableFrame(self._task_checklist_frame)
        self._task_checklist_scroll.canvas.configure(height=120)
        self._task_checklist_scroll.pack(fill=ui.X, pady=(2, 0))
        self._task_checklist_hint_var = ui.StringVar(value="")
        widgets.Label(self._task_checklist_frame, textvariable=self._task_checklist_hint_var, style="Status.TLabel", anchor=ui.W).pack(fill=ui.X)
        self._task_check_vars: dict[str, ui.BooleanVar] = {}
        self._task_check_boxes: dict[str, Checkbox] = {}
        for widget in (self._quick_tasks_entry, self._form_tasks_text):
            widget.bind("<KeyRelease>", lambda _event: self._sync_task_checklist_from_editor(), add="+")

    def _refresh_task_checklist(self) -> None:
        """Rebuild one checkbox per exam task and tick those named in the editor text."""
        for box in self._task_check_boxes.values():
            box.destroy()
        self._task_check_vars.clear()
        self._task_check_boxes.clear()
        exam = self._current_exam
        if exam is None:
            return
        for task in exam.tasks:
            variable = ui.BooleanVar(value=False)
            box = Checkbox(
                self._task_checklist_scroll.content,
                text=f"{task.code} ({task.max_points:g} P.)",
                variable=variable,
                on_select=lambda requested, code=task.code: self._on_task_checked(code, requested),
                takefocus=False,
            )
            box.pack(anchor=ui.W)
            self._task_check_vars[task.code] = variable
            self._task_check_boxes[task.code] = box
        if not exam.tasks:
            self._task_checklist_hint_var.set("Noch keine Aufgaben – in Schritt 1 festlegen oder hier mit Punkten eintippen (z. B. 4a:2).")
        self._sync_task_checklist_from_editor()

    def _task_editor_text(self) -> str:
        """Current text of the active editor mode (quick entry or form text)."""
        if self._assignment_mode_var.get() == "form":
            return self._form_tasks_text.get("1.0", ui.END).strip()
        return self._quick_tasks_var.get().strip()

    def _sync_task_checklist_from_editor(self) -> None:
        """Tick exactly the codes named in the editor text (invalid text: leave the ticks, show the problem)."""
        if not self._task_check_vars:
            return
        result = parse_task_specs(self._task_editor_text(), require_points=False)
        if result.error is not None:
            self._task_checklist_hint_var.set(f"Eingabe prüfen: {result.error}")
            return
        named = {item.code for item in result.items}
        for code, variable in self._task_check_vars.items():
            variable.set(code in named)
        self._task_checklist_hint_var.set("Mit Enter oder „Speichern“ übernehmen." if self._selected_region_id else "Erst einen Bereich ziehen oder auswählen.")

    def _on_task_checked(self, code: str, requested: bool) -> None:
        """Checkbox callback: add/remove exactly ``code`` in the editor text, keep everything else (A1)."""
        if self._selected_region_id is None:
            self._task_checklist_hint_var.set("Erst einen Bereich ziehen oder auswählen.")
            raise TaskChecklistRejected(code)
        result = parse_task_specs(self._task_editor_text(), require_points=False)
        if result.error is not None:
            self._task_checklist_hint_var.set(f"Eingabe erst korrigieren: {result.error}")
            raise TaskChecklistRejected(code)
        items = [item for item in result.items if item.code != code]
        if requested:
            items.append(TaskSpec(code, None))
        self._write_task_editor(sorted(items, key=lambda item: task_sort_key(item.code)))
        self._task_checklist_hint_var.set("Mit Enter oder „Speichern“ übernehmen.")

    def _write_task_editor(self, items: list[TaskSpec]) -> None:
        """Rewrite both editor modes from ``items`` (shorthand; see `format_task_specs`)."""
        self._quick_tasks_var.set(format_task_specs(items))
        self._form_tasks_text.delete("1.0", ui.END)
        self._form_tasks_text.insert("1.0", format_task_specs(items, separator="\n"))
