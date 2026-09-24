from __future__ import annotations

from uuid import uuid4

from app.adapters.gui.dialog_services import messagebox
from app.core.domain.grading_scale import STATUS_ACTIVE, STATUS_ARCHIVED, GradingScale, GradingScaleUsageEntry
from app.core.domain.models import ExamProject, utc_now_iso


class UiIntentControllerGradingScaleMixin:
    """CRUD/Verwaltung fuer globale Notenschluessel-Vorlagen (Meilenstein 2.4).

    Bewusst getrennt von den `_immediate`-Annotation-/Exam-Mutatoren: eine
    `GradingScale` lebt global in `%APPDATA%/<app_name>/grading_scales.json`
    (`JsonGradingScaleRepository`), nicht als Teil einer `ExamProject`-Datei
    - Bearbeiten/Archivieren/Loeschen einer Vorlage ist deshalb **keine**
    Session-History-Aktion (kein `_record_exam_payload_action`, kein
    `Strg+Z`), da hier keine offene Klausur betroffen ist. Nur die
    Zuordnung einer Vorlage zu einer konkreten Klausur
    (`assign_grading_scale_immediate`, Meilenstein 2.5) mutiert ein
    `ExamProject` und folgt deshalb dem gewohnten Snapshot-vor-Mutation ->
    `save_exam` -> `_record_exam_payload_action`-Muster.
    """

    def list_grading_scales(self) -> list[GradingScale]:
        return self._deps.grading_scale_repository.list_scales()

    def list_active_grading_scales(self) -> list[GradingScale]:
        """Only "active" scales - the assignment dropdown (2.5) offers no archived templates."""
        return [scale for scale in self.list_grading_scales() if scale.status == STATUS_ACTIVE]

    def list_grading_scale_usage(self, scale_id: str) -> list[GradingScaleUsageEntry]:
        return self._deps.grading_scale_repository.list_usage(scale_id)

    def save_grading_scale_immediate(self, *, scale: GradingScale) -> GradingScale:
        """Create (empty `scale_id`) or update an existing template."""
        if not scale.scale_id:
            scale.scale_id = f"gs-{uuid4().hex[:12]}"
        saved = self._deps.grading_scale_repository.save_scale(scale)
        self._app.set_status(f"Notenschluessel gespeichert: {saved.name}")
        return saved

    def archive_grading_scale_immediate(self, *, scale_id: str) -> GradingScale | None:
        scale = self._deps.grading_scale_repository.get_scale(scale_id)
        if scale is None:
            return None
        scale.status = STATUS_ARCHIVED
        saved = self._deps.grading_scale_repository.save_scale(scale)
        self._app.set_status(f"Notenschluessel archiviert: {saved.name}")
        return saved

    def reactivate_grading_scale_immediate(self, *, scale_id: str) -> GradingScale | None:
        scale = self._deps.grading_scale_repository.get_scale(scale_id)
        if scale is None:
            return None
        scale.status = STATUS_ACTIVE
        saved = self._deps.grading_scale_repository.save_scale(scale)
        self._app.set_status(f"Notenschluessel reaktiviert: {saved.name}")
        return saved

    def delete_grading_scale_immediate(self, *, scale_id: str) -> bool:
        """Hard-delete a never-used template; reject (with a clear error) one that has usage history.

        A scale with recorded usage must be archived instead
        (`archive_grading_scale_immediate`) - deleting it would sever the
        Verwendungsuebersicht's `source_scale_id` link for entries that
        otherwise stay meaningful forever (`GradingScaleUsageEntry` never
        expires an exam's own reference to a scale it no longer needs to
        look up, but the Verwaltung's "wo verwendet" display does).
        """
        repo = self._deps.grading_scale_repository
        scale = repo.get_scale(scale_id)
        if scale is None:
            return False
        if repo.has_usage(scale_id):
            messagebox.showerror(
                "Loeschen nicht moeglich",
                f"'{scale.name}' wurde bereits mindestens einer Klausur zugeordnet und kann deshalb nicht "
                "geloescht werden - bitte stattdessen archivieren.",
            )
            return False
        repo.delete_scale(scale_id)
        self._app.set_status(f"Notenschluessel geloescht: {scale.name}")
        return True

    def assign_grading_scale_immediate(self, *, exam: ExamProject, scale_id: str) -> ExamProject | None:
        """Assign a global scale to `exam`: snapshot it in, record usage, one undoable HistoryAction.

        The snapshot (`GradingScale.to_snapshot()`) is what `resolve_grade`
        will ever read for this exam - see `docs/ARCHITEKTUR.md`
        "Notenschluessel". The usage-log write is deliberately *not* part of
        the exam's undo/redo: it is an append-only fact ("this scale was
        assigned to this exam at this time") that stays true regardless of
        whether the assignment is later undone within this session.
        """
        scale = self._deps.grading_scale_repository.get_scale(scale_id)
        if scale is None:
            messagebox.showerror("Fehler", "Dieser Notenschluessel existiert nicht (mehr).")
            return None

        before_payload = exam.to_dict()
        assigned_at = utc_now_iso()
        exam.grading_scale_snapshot = scale.to_snapshot(assigned_at=assigned_at)
        exam_file = self._save_exam_guarded(exam)
        if exam_file is None:
            return None
        updated = self._deps.exam_repository.load_exam(exam_file)

        self._deps.grading_scale_repository.record_usage(
            GradingScaleUsageEntry(
                source_scale_id=scale.scale_id,
                exam_id=updated.exam_id,
                exam_name=updated.exam_name,
                exam_folder_path=updated.folder_path,
                assigned_at=assigned_at,
            )
        )

        self._record_exam_payload_action(
            description=f"Notenschluessel zugeordnet: {scale.name}",
            exam_id=updated.exam_id,
            before_payload=before_payload,
            after_payload=updated.to_dict(),
        )
        self.refresh_exam_overview()
        self._app.set_status(f"Notenschluessel zugeordnet: {scale.name}")
        return updated
