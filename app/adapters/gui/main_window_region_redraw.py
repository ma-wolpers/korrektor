from __future__ import annotations

from app.adapters.gui.dialog_services import messagebox


class MainWindowRegionRedrawMixin:
    """"Bereich neu ziehen": arm a redraw for the selected region and apply it on the next drawn box.

    Works the same for Superseiten- and Einzelseiten-Bereiche (schema v2: both are regions).
    """

    def _arm_redraw_selected_region(self) -> None:
        """Arm "Bereich neu ziehen" for the selected saved region (Superseiten or Einzelseiten)."""
        if self._selected_region_id is None or self._selected_region_kind != "region":
            messagebox.showinfo("Hinweis", "Bitte zuerst einen bestehenden Bereich auswählen (kein Draft).")
            return
        self._redraw_target_region_kind = self._selected_region_kind
        self._redraw_target_region_id = self._selected_region_id
        self._redraw_on_next_box = True
        self._status_var.set("Neuziehen aktiv: Die nächste gezogene Box überschreibt den ausgewählten Bereich.")

    def _clear_pending_redraw(self) -> None:
        """Disarm „Bereich neu ziehen“."""
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
        """Apply an armed redraw with the drawn ``box``; ``True`` if the box was consumed.

        The region keeps its id, label, tasks and kind (Superseiten stays
        Superseiten); only page and box change. ``student_pdf`` is the page
        the box was drawn on and is used for Einzelseiten-Bereiche only.
        """
        if not self._redraw_on_next_box or self._redraw_target_region_id is None:
            return False
        if self._controller is None or self._current_exam is None:
            self._clear_pending_redraw()
            return False
        region = next((item for item in self._current_exam.regions if item.region_id == self._redraw_target_region_id), None)
        if region is None:
            self._clear_pending_redraw()
            messagebox.showerror("Bereich fehlt", "Der ausgewählte Bereich konnte nicht mehr gefunden werden.")
            return False
        updated = self._controller.upsert_region_immediate(
            exam=self._current_exam,
            student_pdf=student_pdf if region.student_pdf else "",
            page_number=page_number,
            box=box,
            task_specs=[(code, None) for code in region.task_codes],
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
