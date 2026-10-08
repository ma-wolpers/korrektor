from __future__ import annotations

from app.adapters.gui.dialog_services import messagebox

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui


class MainWindowRegionRedrawMixin:
    """"Bereich neu ziehen": arm a redraw for the selected region and apply it on the next drawn box.

    Moved out of `main_window_reading_canvas.py` (file-size rule) without changes.
    """

    def _arm_redraw_selected_region(self) -> None:
        if self._selected_region_id is None or self._selected_region_kind not in {"region", "extra"}:
            messagebox.showinfo("Hinweis", "Bitte zuerst einen bestehenden Bereich auswählen (kein Draft).")
            return
        if self._extra_mode_active and self._selected_region_kind != "extra":
            messagebox.showinfo("Hinweis", "Im Extraseitenmodus kann nur eine Extraseiten-Zuordnung neu gezogen werden.")
            return
        if not self._extra_mode_active and self._selected_region_kind != "region":
            messagebox.showinfo("Hinweis", "Im Zuschnitt kann nur ein Standardbereich neu gezogen werden.")
            return
        self._redraw_target_region_kind = self._selected_region_kind
        self._redraw_target_region_id = self._selected_region_id
        self._redraw_on_next_box = True
        self._status_var.set("Neuziehen aktiv: Die nächste gezogene Box überschreibt den ausgewählten Bereich.")

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
                messagebox.showerror("Bereich fehlt", "Die ausgewählte Extraseiten-Zuordnung konnte nicht gefunden werden.")
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
            self._status_var.set(f"Extraseiten-Bereich {area_text} neu gezogen und überschrieben.")
            return True

        region = next(
            (item for item in self._current_exam.regions if item.region_id == self._redraw_target_region_id),
            None,
        )
        if region is None:
            self._clear_pending_redraw()
            messagebox.showerror("Bereich fehlt", "Der ausgewählte Bereich konnte nicht mehr gefunden werden.")
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
        self._status_var.set(f"Bereich {area_text} neu gezogen und überschrieben.")
        return True
