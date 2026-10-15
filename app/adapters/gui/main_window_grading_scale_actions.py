"""Notenschlüssel-Verwaltung: Formular- und Bestandsaktionen (Speichern, Archivieren, Reaktivieren, Löschen, Zuweisen, Import/Export).

Aus ``main_window_grading_scale.py`` ausgelagert (300-Zeilen-Regel), Methoden unverändert."""

from __future__ import annotations

from app.adapters.gui.dialog_services import messagebox
from app.adapters.gui.main_window_constants import GRADING_SCALE_TYPE_BY_LABEL, GRADING_SCALE_TYPE_LABELS
from app.core.domain.grading_scale import GradeThreshold, GradingScale

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui


class MainWindowGradingScaleActionsMixin:
    """Notenschlüssel-Verwaltung: Formular- und Bestandsaktionen (Speichern, Archivieren, Reaktivieren, Löschen, Zuweisen, Import/Export)."""

    def _clear_grading_scale_form(self) -> None:
        self._grading_scale_selected_id = None
        if self._grading_scale_tree is not None:
            self._grading_scale_tree.selection_remove(*self._grading_scale_tree.selection())
        self._gs_name_var.set("")
        self._gs_subject_var.set("")
        self._gs_year_var.set("")
        self._gs_school_var.set("")
        self._gs_type_var.set(GRADING_SCALE_TYPE_LABELS[0])
        if hasattr(self, "_gs_thresholds_text"):
            self._gs_thresholds_text.delete("1.0", ui.END)
        if hasattr(self, "_grading_scale_usage_var"):
            self._grading_scale_usage_var.set("Verwendung: -")
        if hasattr(self, "_gs_reactivate_button"):
            self._gs_reactivate_button.pack_forget()
        if hasattr(self, "_gs_archive_button"):
            self._gs_archive_button.pack(side=ui.LEFT)

    def _parse_grading_scale_thresholds_from_text(self) -> list[GradeThreshold] | None:
        """Parse the "Prozent:Note"-per-line editor, same CODE:VALUE convention as the Aufgaben-Editor.

        Returns `None` (having already shown an error) on any malformed
        line - never a partially-parsed list.
        """
        raw = self._gs_thresholds_text.get("1.0", ui.END).strip()
        if not raw:
            messagebox.showerror("Ungültige Eingabe", "Bitte mindestens eine Notenstufe angeben, z. B. 80:1")
            return None
        thresholds: list[GradeThreshold] = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = [part.strip() for part in line.split(":")]
            if len(parts) != 2:
                messagebox.showerror("Ungültiges Format", f"Nutze Prozent:Note, z. B. 80:1 - nicht '{line}'")
                return None
            percent_text, grade_label = parts
            try:
                min_percent = float(percent_text.replace(",", "."))
            except ValueError:
                messagebox.showerror("Ungültiger Prozentwert", f"'{percent_text}' ist keine Zahl.")
                return None
            if not grade_label:
                messagebox.showerror("Ungültige Note", "Bitte für jede Zeile eine Note angeben.")
                return None
            thresholds.append(GradeThreshold(min_percent=min_percent, grade_label=grade_label))
        return thresholds

    def _save_grading_scale_from_form(self) -> None:
        if self._controller is None:
            return
        name = self._gs_name_var.get().strip()
        if not name:
            messagebox.showerror("Ungültige Eingabe", "Bitte einen Namen angeben.")
            return
        thresholds = self._parse_grading_scale_thresholds_from_text()
        if thresholds is None:
            return

        scale = GradingScale(
            scale_id=self._grading_scale_selected_id or "",
            name=name,
            subject=self._gs_subject_var.get().strip(),
            year=self._gs_year_var.get().strip(),
            school=self._gs_school_var.get().strip(),
            scale_type=GRADING_SCALE_TYPE_BY_LABEL.get(self._gs_type_var.get(), GRADING_SCALE_TYPE_LABELS[0]),
            thresholds=thresholds,
        )
        saved = self._controller.save_grading_scale_immediate(scale=scale)
        self._refresh_grading_scale_tree()
        if self._grading_scale_tree is not None:
            self._grading_scale_tree.selection_set(saved.scale_id)
        self._grading_scale_selected_id = saved.scale_id
        self._refresh_grading_scale_assignment_choices()

    def _archive_selected_grading_scale(self) -> None:
        if self._controller is None or self._grading_scale_selected_id is None:
            return
        self._controller.archive_grading_scale_immediate(scale_id=self._grading_scale_selected_id)
        self._refresh_grading_scale_tree()
        self._on_grading_scale_selected(None)
        self._refresh_grading_scale_assignment_choices()

    def _reactivate_selected_grading_scale(self) -> None:
        if self._controller is None or self._grading_scale_selected_id is None:
            return
        self._controller.reactivate_grading_scale_immediate(scale_id=self._grading_scale_selected_id)
        self._refresh_grading_scale_tree()
        self._on_grading_scale_selected(None)
        self._refresh_grading_scale_assignment_choices()

    def _delete_selected_grading_scale(self) -> None:
        if self._controller is None or self._grading_scale_selected_id is None:
            return
        if self._controller.delete_grading_scale_immediate(scale_id=self._grading_scale_selected_id):
            self._clear_grading_scale_form()
            self._refresh_grading_scale_tree()
            self._refresh_grading_scale_assignment_choices()

    def _refresh_grading_scale_assignment_choices(self) -> None:
        """Populate the Detailansicht's Zuordnungs-Combobox and status label from the current exam.

        Called whenever the detail view needs to reflect current data:
        opening a Klausur (`open_exam_detail`), a content-preserving
        undo/redo refresh (`refresh_exam_content_in_place`), and right
        after a save/archive/delete in the Notenschluessel-Verwaltung
        popup, since those can change which scales are offered here.
        """
        if self._controller is None:
            return
        active_scales = self._controller.list_active_grading_scales()
        self._grading_scale_assign_id_by_label = {
            f"{scale.name} ({scale.school})" if scale.school else scale.name: scale.scale_id for scale in active_scales
        }
        labels = tuple(self._grading_scale_assign_id_by_label.keys())
        self._grading_scale_assign_combo["values"] = labels
        if self._grading_scale_assign_choice_var.get() not in labels:
            self._grading_scale_assign_choice_var.set(labels[0] if labels else "")

        if self._current_exam is not None and self._current_exam.grading_scale_snapshot is not None:
            snapshot = self._current_exam.grading_scale_snapshot
            self._grading_scale_assignment_var.set(f"Notenschlüssel: {snapshot.name} (zugeordnet am {snapshot.assigned_at[:10]})")
        else:
            self._grading_scale_assignment_var.set("Notenschlüssel: keiner zugeordnet")

    def _assign_selected_grading_scale_to_current_exam(self) -> None:
        if self._current_exam is None or self._controller is None:
            return
        label = self._grading_scale_assign_choice_var.get()
        scale_id = self._grading_scale_assign_id_by_label.get(label)
        if scale_id is None:
            messagebox.showinfo("Hinweis", "Bitte zuerst einen Notenschlüssel auswählen.")
            return
        updated = self._controller.assign_grading_scale_immediate(exam=self._current_exam, scale_id=scale_id)
        if updated is None:
            return
        self._current_exam = updated
        self._refresh_grading_scale_assignment_choices()

    def _export_grading_scales(self) -> None:
        if self._controller is None:
            return
        self._controller.export_grading_scales_to_file()

    def _import_grading_scales(self) -> None:
        if self._controller is None:
            return
        summary = self._controller.import_grading_scales_from_file()
        if summary is None or summary.is_empty:
            return

        self._refresh_grading_scale_tree()
        self._refresh_grading_scale_assignment_choices()

        lines = []
        if summary.added:
            lines.append(f"Neu hinzugefügt ({len(summary.added)}): {', '.join(summary.added)}")
        if summary.skipped_identical:
            lines.append(f"Bereits vorhanden, übersprungen ({len(summary.skipped_identical)}): {', '.join(summary.skipped_identical)}")
        if summary.skipped_conflict:
            lines.append(
                f"Konflikt - gleicher Notenschlüssel existiert bereits mit anderem Inhalt, "
                f"nicht überschrieben ({len(summary.skipped_conflict)}): {', '.join(summary.skipped_conflict)}"
            )
        messagebox.showinfo("Notenschlüssel-Import", "\n".join(lines))
