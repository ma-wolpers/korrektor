from __future__ import annotations

from app.adapters.gui.dialog_services import messagebox
from app.core.domain.models import ExamProject
from app.core.domain.task_spec import format_task_specs, parse_task_specs

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui


class MainWindowRegionSpecsMixin:
    """Reine Formatierungs-/Lookup-Helfer fuer den Region-Editor, ohne geteilten mutable State.

    Bewusst getrennt von `main_window_region_editor.py`: dort liegt der
    geteilte Treeview-/Selektions-/Draft-Mechanismus (echter mutable State,
    Reading+Extraseiten-Modus gemeinsam), hier nur zustandslose Formatierung/
    Parsing/Lookup - eine echte zweite Verantwortlichkeit, keine reine
    Zeilenbudget-Aufteilung.
    """

    def _refresh_correction_area_choices(self, exam: ExamProject) -> None:
        areas = sorted(
            {
                code.strip().upper()
                for region in exam.regions
                for code in region.assigned_area_codes
                if code.strip()
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

    def _existing_standard_areas(self) -> list[str]:
        if self._current_exam is None:
            return []
        return sorted(
            {
                code.strip().upper()
                for region in self._current_exam.regions
                for code in region.assigned_area_codes
                if code.strip()
            }
        )

    def _refresh_task_input_mode(self) -> None:
        mode = self._assignment_mode_var.get()
        if mode == "form":
            self._quick_tasks_entry.pack_forget()
            self._form_tasks_text.pack_forget()
            self._form_tasks_text.pack(fill=ui.X, pady=(4, 0))
            self._task_input_example_var.set("Beispiel (Formular):\n4a-d:1,4,2,3\n5a:2")
        else:
            self._form_tasks_text.pack_forget()
            self._quick_tasks_entry.pack_forget()
            self._quick_tasks_entry.pack(fill=ui.X)
            self._task_input_example_var.set("Beispiel (Schnell): 4a-d:1,4,2,3; 5a:2 (4a-d = 4a bis 4d)")

        self._task_input_example_label.pack_forget()
        self._task_input_example_label.pack(fill=ui.X, pady=(4, 0))

    def _read_task_specs_from_editor(self) -> list[tuple[str, float]] | None:
        """Parse the Aufgaben/Punkte editor (quick or form mode) with the shorthand grammar.

        Both modes share `parse_task_specs` (``4a-d:1,4,2,3;5a:2`` or one entry
        per line). Returns ``[(CODE, points)]``, ``[]`` for an empty editor, or
        ``None`` after showing the parser's German error message.
        """
        if self._assignment_mode_var.get() == "form":
            raw = self._form_tasks_text.get("1.0", ui.END).strip()
        else:
            raw = self._quick_tasks_var.get().strip()
        if not raw:
            return []
        result = parse_task_specs(raw, require_points=True)
        if result.error is not None:
            messagebox.showerror("Ungültige Aufgabeneingabe", result.error)
            return None
        return [(item.code, float(item.points)) for item in result.items]

    def _show_task_specs_in_editor(self, task_specs: list[tuple[str, float]]) -> None:
        """Fill both editor modes with ``task_specs`` in shorthand (runs compressed, see `format_task_specs`)."""
        self._quick_tasks_var.set(format_task_specs(task_specs))
        self._form_tasks_text.delete("1.0", ui.END)
        self._form_tasks_text.insert("1.0", format_task_specs(task_specs, separator="\n"))

    @staticmethod
    def _index_to_area_label(index: int) -> str:
        letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        result = ""
        value = index
        while True:
            value, remainder = divmod(value, 26)
            result = letters[remainder] + result
            if value == 0:
                break
            value -= 1
        return result

    @staticmethod
    def _format_area_label(area_codes: list[str]) -> str:
        labels = [code.strip().upper() for code in area_codes if code.strip()]
        return ", ".join(labels) if labels else "-"

    @staticmethod
    def _format_task_specs_text(task_specs: list[tuple[str, float]]) -> str:
        if not task_specs:
            return "-"
        return ", ".join(f"{code}({max_points:g})" for code, max_points in task_specs)

    def _build_standard_area_task_map(self) -> dict[str, list[tuple[str, float]]]:
        mapping: dict[str, list[tuple[str, float]]] = {}
        if self._current_exam is None:
            return mapping

        for region in self._current_exam.regions:
            task_specs = [(task.code, task.max_points) for task in region.tasks]
            for code in region.assigned_area_codes:
                normalized = code.strip().upper()
                if not normalized or normalized in mapping:
                    continue
                mapping[normalized] = task_specs
        return mapping

    def _format_tasks_for_areas(self, area_codes: list[str]) -> str:
        normalized_area_codes = [code.strip().upper() for code in area_codes if code.strip()]
        if not normalized_area_codes:
            return "-"

        area_tasks = self._build_standard_area_task_map()
        parts: list[str] = []
        for area_code in normalized_area_codes:
            task_text = self._format_task_specs_text(area_tasks.get(area_code, []))
            parts.append(f"{area_code}: {task_text}")
        return " | ".join(parts)
