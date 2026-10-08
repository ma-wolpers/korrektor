from __future__ import annotations

from app.adapters.gui.dialog_services import messagebox

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui


class MainWindowRegionFormMixin:
    """Edit/save/delete of the region selected in the shared region tree (Zuschnitt and Extraseiten).

    Moved out of `main_window_region_editor.py` (file-size rule) without changes;
    it operates on the shared selection (`_selected_region_id`/`_selected_region_kind`)
    and draft dict (`_draft_regions`) that the region editor builds.
    """

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
        if self._active_view == "scan_workshop":
            if not self._is_editable_widget(self.root.focus_get()):
                self._scan_toggle_delete()
            return
        if self._active_view == "correction" and self._correction_mode_active:
            self._delete_selected_correction_annotation()
            return
        if (
            self._active_view == "reading"
            and self._detail_submode == "extra"
            and self._extra_mode_active
            and not self._is_editable_widget(self.root.focus_get())
            and self._selected_region_id is None
        ):
            # Zuschnitt Schritt 2: Entf toggles "ohne Bewertung" for the current page;
            # with an assignment selected in the tree it still deletes that assignment.
            self._toggle_current_page_unscored()
            return
        self._delete_selected_region()
