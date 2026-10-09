from __future__ import annotations

from app.core.domain.task_regions import tasks_of_region

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui


class MainWindowRegionFormMixin:
    """Select/save/delete the region chosen in the shared region tree (Superseiten and Einzelseiten).

    One commit path for both Zuschnitt steps: `_commit_reading_fields_if_possible`
    reads the task editor (shorthand, points optional for existing tasks)
    and calls `upsert_region_immediate` with the region's/draft's
    ``student_pdf`` ("" = Superseiten-Bereich, else Einzelseiten-Bereich).
    It runs on Enter, on leaving the field and via "Speichern".
    """

    def _on_region_selected(self, _event: object) -> None:
        """Show the selected region's/draft's tasks in the editor and highlight it on the page."""
        if self._current_exam is None:
            return
        selection = self._regions_tree.selection()
        if not selection:
            self._selected_region_id = None
            self._selected_region_kind = None
            self._active_region_var.set("-")
            self._sync_task_checklist_from_editor()
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
            self._show_task_specs_in_editor(list(draft.task_specs))
        else:
            region = next((item for item in self._current_exam.regions if item.region_id == region_id), None)
            if region is None:
                return
            self._selected_region_id = region_id
            self._active_region_var.set(region.assigned_area_codes[0] if region.assigned_area_codes else "-")
            self._show_task_specs_in_editor([(task.code, task.max_points) for task in tasks_of_region(self._current_exam, region)])
        self._sync_task_checklist_from_editor()
        self._rerender_active_page()

    def _commit_reading_fields_if_possible(self) -> None:
        """Persist the task editor's content for the selected region or draft (both Zuschnitt steps).

        Single commit path (Enter, <FocusOut>, "Speichern"); a draft becomes
        a region on success and stays a draft on any rejection, so typed
        input is never lost.
        """
        if self._current_exam is None or self._selected_region_id is None or self._controller is None:
            return
        task_specs = self._read_task_specs_from_editor()
        if task_specs is None:
            return

        region = next((item for item in self._current_exam.regions if item.region_id == self._selected_region_id), None)
        draft = None if region is not None else self._draft_regions.get(self._selected_region_id)
        if region is None and draft is None:
            return
        if region is not None:
            box = (region.box.x0, region.box.y0, region.box.x1, region.box.y1)
            student_pdf, page_number, labels, region_id = region.student_pdf, region.page_number, region.assigned_area_codes, region.region_id
        else:
            box, student_pdf, page_number, labels, region_id = draft.box, draft.student_pdf, draft.page_number, draft.area_codes, None
        before_ids = {item.region_id for item in self._current_exam.regions}
        updated = self._controller.upsert_region_immediate(
            exam=self._current_exam,
            student_pdf=student_pdf,
            page_number=page_number,
            box=box,
            task_specs=task_specs,
            area_codes=labels,
            region_id=region_id,
        )
        if updated is None:
            return
        persisted_id = region_id or next((item.region_id for item in reversed(updated.regions) if item.region_id not in before_ids), None)
        if draft is not None:
            del self._draft_regions[draft.draft_id]
        self._current_exam = updated
        self._refresh_region_tree()
        self._refresh_task_checklist()
        if persisted_id:
            self._select_region_by_id(persisted_id)
        self._apply_detail_labels(updated)
        self._rerender_active_page()

    def _delete_selected_region(self) -> None:
        """Delete the selected draft (local) or region (one undo step; orphaned tasks/marks go with it)."""
        if self._current_exam is None or self._selected_region_id is None:
            return
        if self._selected_region_id in self._draft_regions:
            del self._draft_regions[self._selected_region_id]
        elif self._controller is not None:
            self._current_exam = self._controller.delete_region_immediate(exam=self._current_exam, region_id=self._selected_region_id)
            self._apply_detail_labels(self._current_exam)
        else:
            return
        self._selected_region_id = None
        self._selected_region_kind = None
        self._active_region_var.set("-")
        self._quick_tasks_var.set("")
        self._form_tasks_text.delete("1.0", ui.END)
        self._refresh_region_tree()
        self._refresh_task_checklist()
        self._rerender_active_page()

    def _on_delete_region_key(self, _event: ui.Event[ui.Misc]) -> None:
        """Entf: Scan-Werkstatt page, correction mark, "ohne Bewertung" (Schritt 2 without selection) or region."""
        if self._active_view == "scan_workshop":
            if not self._is_editable_widget(self.root.focus_get()):
                self._scan_toggle_delete()
            return
        if self._active_view == "correction" and self._correction_mode_active:
            self._delete_selected_correction_annotation()
            return
        if self._is_editable_widget(self.root.focus_get()):
            return
        if self._active_view == "reading" and self._detail_submode == "extra" and self._extra_mode_active and self._selected_region_id is None:
            # Zuschnitt Schritt 2: Entf toggles "ohne Bewertung" for the current page;
            # with a region selected in the list it deletes that region.
            self._toggle_current_page_unscored()
            return
        self._delete_selected_region()
