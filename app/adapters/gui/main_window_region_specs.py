from __future__ import annotations

from app.adapters.gui.dialog_services import messagebox
from app.core.domain.models import ExamProject
from app.core.domain.task_spec import TaskSpec, format_task_specs, parse_task_specs

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui


class MainWindowRegionSpecsMixin:
    """Reine Formatierungs-/Parsing-/Lookup-Helfer für den Region-Editor, ohne geteilten mutable State.

    Bewusst getrennt von `main_window_region_editor.py`: dort liegt der
    geteilte Treeview-/Selektions-/Draft-Mechanismus (echter mutable State,
    Superseiten und Einzelseiten gemeinsam), hier nur zustandslose
    Formatierung/Parsing/Lookup.
    """

    def _refresh_correction_area_choices(self, exam: ExamProject) -> None:
        """Area combo of the correction view: labels of Superseiten-Bereiche (until the view becomes task-centric)."""
        areas = sorted(
            {
                region.assigned_area_codes[0].strip().upper()
                for region in exam.regions
                if not region.student_pdf and region.assigned_area_codes and region.assigned_area_codes[0].strip()
            }
        )
        if not areas:
            areas = ["A"]
        values = tuple(areas)
        self._correction_area_combo["values"] = values
        if hasattr(self, "_correction_area_combo_view"):
            self._correction_area_combo_view["values"] = values
        if self._correction_area_var.get() not in areas:
            self._correction_area_var.set(areas[0])

    def _refresh_task_input_mode(self) -> None:
        """Show the quick entry or the form text with a matching example."""
        mode = self._assignment_mode_var.get()
        if mode == "form":
            self._quick_tasks_entry.pack_forget()
            self._form_tasks_text.pack_forget()
            self._form_tasks_text.pack(fill=ui.X, pady=(4, 0))
            self._task_input_example_var.set("Beispiel (Formular):\n4a-d:1,4,2,3\n5a:2\n6c (vorhandene Aufgabe, ohne Punkte)")
        else:
            self._form_tasks_text.pack_forget()
            self._quick_tasks_entry.pack_forget()
            self._quick_tasks_entry.pack(fill=ui.X)
            self._task_input_example_var.set("Beispiel: 4a-d:1,4,2,3; 5a:2 (4a-d = 4a bis 4d); vorhandene Aufgaben auch ohne Punkte: 6c")

        self._task_input_example_label.pack_forget()
        self._task_input_example_label.pack(fill=ui.X, pady=(4, 0))

    def _read_task_specs_from_editor(self) -> list[TaskSpec] | None:
        """Parse the task editor (quick or form mode) with the shorthand grammar.

        Points are optional: a code without points references an existing
        task (``6c``); whether it exists is checked when saving. Returns the
        specs, ``[]`` for an empty editor, or ``None`` after showing the
        parser's German error message.
        """
        if self._assignment_mode_var.get() == "form":
            raw = self._form_tasks_text.get("1.0", ui.END).strip()
        else:
            raw = self._quick_tasks_var.get().strip()
        if not raw:
            return []
        result = parse_task_specs(raw, require_points=False)
        if result.error is not None:
            messagebox.showerror("Ungültige Aufgabeneingabe", result.error)
            return None
        return list(result.items)

    def _show_task_specs_in_editor(self, task_specs: list) -> None:
        """Fill both editor modes with ``task_specs`` in shorthand (runs compressed, see `format_task_specs`)."""
        self._quick_tasks_var.set(format_task_specs(task_specs))
        self._form_tasks_text.delete("1.0", ui.END)
        self._form_tasks_text.insert("1.0", format_task_specs(task_specs, separator="\n"))

    @staticmethod
    def _format_area_label(area_codes: list[str]) -> str:
        """Display label(s) of a region for lists (``"-"`` if none)."""
        labels = [code.strip().upper() for code in area_codes if code.strip()]
        return ", ".join(labels) if labels else "-"
