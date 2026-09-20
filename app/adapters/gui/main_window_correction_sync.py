from __future__ import annotations

from app.adapters.gui.dialog_services import messagebox
from app.core.domain.annotation_sync import sync_group_members
from app.core.domain.models import PdfAnnotation


class MainWindowCorrectionSyncMixin:
    """"Durchdruecken"-Sync-Gruppen-Verwaltung fuer Korrektur-Annotationen.

    Ausgelagert aus `main_window_correction_markers_clipboard.py` (Meilenstein
    0.3 der Korrektor-Wunschliste), das mit 485 Rohzeilen bereits ueber der
    projektweiten ~300-Zeilen-Konvention lag und hier strukturell erweitert
    wird (siehe `docs/ARCHITEKTUR.md` "Datei-Organisation"). Enthaelt die
    reine Sync-Gruppen-Zugehoerigkeit sowie Ein-/Ausschalten von
    "Durchdruecken" - beide jetzt sofort persistiert und atomar rueckgaengig
    machbar ueber `UiIntentControllerAnnotationsMixin.enable_annotation_sync_immediate`/
    `disable_annotation_sync_immediate`, vorher mutierten sie nur den
    In-Memory-Zustand ohne Persistenz/History. Das Entkoppeln nur des
    ausgewaehlten Symbols (Meilenstein 1.3, "nur dieses Symbol entkoppeln")
    ergaenzt diese Datei in einem eigenen Schritt.
    """

    def _sync_group_members(self, annotation: PdfAnnotation, *, include_detached: bool) -> list[PdfAnnotation]:
        """Thin GUI-layer wrapper around the pure domain lookup `sync_group_members`.

        Returns `[annotation]` (not `[]`) for an unsynced annotation - "no
        sync group" means "act on just this one", which the domain function
        itself does not decide (it only knows how to resolve an actual
        `sync_group_id`).
        """
        if self._current_exam is None or not annotation.sync_group_id:
            return [annotation]
        return sync_group_members(self._current_exam.pdf_annotations, annotation.sync_group_id, include_detached=include_detached)

    def _refresh_correction_sync_info(self) -> None:
        annotation = self._selected_correction_annotation()
        if annotation is None:
            self._correction_sync_info_var.set("Sync: keine Auswahl")
            return

        if not annotation.sync_group_id:
            self._correction_sync_info_var.set("Sync: lokal")
            return

        members = self._sync_group_members(annotation, include_detached=True)
        detached_suffix = " | Position lokal geloest (Alt-Drag)" if annotation.position_detached else ""
        self._correction_sync_info_var.set(f"Sync: aktiv ({len(members)} Kopien){detached_suffix}")

    def _toggle_selected_annotation_sync(self) -> None:
        if self._current_exam is None or self._controller is None:
            return
        annotation = self._selected_correction_annotation()
        if annotation is None:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Markierung auswaehlen.")
            return

        if annotation.sync_group_id:
            updated = self._controller.disable_annotation_sync_immediate(
                exam=self._current_exam,
                annotation_id=annotation.annotation_id,
            )
            if updated is None:
                return
            self._current_exam = updated
            self._render_correction_annotations()
            self._status_var.set("Durchdruecken deaktiviert: Kopien bei anderen Personen entfernt")
            return

        other_student_pdfs = [
            self._current_exam.students[student_index].pdf_filename
            for student_index in self._correction_student_indices
            if self._current_exam.students[student_index].pdf_filename != annotation.student_pdf
        ]
        annotations_before = len(self._current_exam.pdf_annotations)
        updated = self._controller.enable_annotation_sync_immediate(
            exam=self._current_exam,
            annotation_id=annotation.annotation_id,
            other_student_pdfs=other_student_pdfs,
        )
        if updated is None:
            return
        created = len(updated.pdf_annotations) - annotations_before
        self._current_exam = updated
        self._render_correction_annotations()
        self._status_var.set(f"Durchgedrueckt: {created} Kopien erzeugt")

    def _detach_selected_annotation_from_sync(self) -> None:
        """"Nur dieses Symbol entkoppeln": leave the sync group, others stay synced.

        Unlike `_toggle_selected_annotation_sync`'s "Durchdruecken
        deaktivieren" path (dissolves the whole group), this removes only
        the selected annotation - the remaining members keep propagating
        colour/size/rotation/position among themselves unchanged.
        """
        if self._current_exam is None or self._controller is None:
            return
        annotation = self._selected_correction_annotation()
        if annotation is None:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Markierung auswaehlen.")
            return
        if not annotation.sync_group_id:
            messagebox.showinfo("Hinweis", "Diese Markierung ist nicht Teil einer Sync-Gruppe.")
            return

        updated = self._controller.detach_annotation_from_sync_immediate(
            exam=self._current_exam, annotation_id=annotation.annotation_id
        )
        if updated is None:
            return
        self._current_exam = updated
        self._render_correction_annotations()
        self._status_var.set("Symbol vom Sync entkoppelt - bei allen anderen bleibt es gesynct")
