from __future__ import annotations

from uuid import uuid4

from app.core.domain.page_coverage import pages_missing_markings
from app.adapters.gui.dialog_services import messagebox
from app.core.domain.models import ExamProject, RegionAssignment, RegionBox, TaskDefinition
from app.core.domain.validation import ExamConflictError


class UiIntentControllerRegionsMixin:
    @staticmethod
    def _existing_standard_area_codes(exam: ExamProject) -> set[str]:
        return {
            code.strip().upper()
            for region in exam.regions
            for code in region.assigned_area_codes
            if code.strip()
        }

    @staticmethod
    def _existing_task_codes(exam: ExamProject) -> set[str]:
        return {
            task.code.strip().upper()
            for region in exam.regions
            for task in region.tasks
            if task.code.strip()
        }

    def _reject_max_points_change_for_scored_tasks(
        self, *, exam: ExamProject, region_id: str | None, new_tasks: list[TaskDefinition]
    ) -> bool:
        """Block editing `max_points` for a task that already has recorded scores; show a clear error.

        Meilenstein 2.7 der Korrektor-Wunschliste: `TaskDefinition.max_points`
        must stay historically stable once a task has been graded, so an
        already-computed Note-/Kompetenzwert never silently drifts under
        someone's feet. `upsert_region_immediate` is the single place
        `RegionAssignment.tasks` gets (re-)written, so this check runs here
        rather than duplicated per call site. Only compares against an
        *existing* region (a brand-new one, `region_id is None`, has no
        history to protect); only the max_points actually changed matters,
        not whether the task existed before with the same value. Returns
        `True` (and shows the error) if the edit must be rejected.
        """
        if region_id is None:
            return False
        existing_region = next((region for region in exam.regions if region.region_id == region_id), None)
        if existing_region is None:
            return False
        old_max_points_by_code = {task.code: task.max_points for task in existing_region.tasks}
        changed_codes = [
            task.code
            for task in new_tasks
            if task.code in old_max_points_by_code and task.max_points != old_max_points_by_code[task.code]
        ]
        if not changed_codes:
            return False

        scores = self._deps.score_repository.load_scores(exam=exam)
        already_scored = sorted(
            code for code in changed_codes if any(code in student_scores for student_scores in scores.values())
        )
        if not already_scored:
            return False

        joined = ", ".join(already_scored)
        messagebox.showerror(
            "Änderung abgelehnt",
            f"Die maximale Punktzahl von bereits bewerteten Aufgaben ({joined}) kann nicht mehr geändert werden, "
            "damit bereits erfasste Punkte/Noten nicht rückwirkend verfälscht werden.",
        )
        return True

    def upsert_region_immediate(
        self,
        *,
        exam: ExamProject,
        student_pdf: str,
        page_number: int,
        box: tuple[float, float, float, float],
        task_specs: list[tuple[str, float]],
        area_codes: list[str],
        region_id: str | None = None,
    ) -> ExamProject | None:
        if page_number > exam.standard_page_count:
            messagebox.showerror(
                "Ungültige Eingabe",
                "Im Extraseitenmodus können keine Aufgaben definiert werden. Bitte nur Bereich(e) zuordnen.",
            )
            return None

        before_payload = exam.to_dict()
        tasks = [
            TaskDefinition(code=code.strip().upper(), name=code.strip().upper(), max_points=max_points)
            for code, max_points in task_specs
            if code.strip()
        ]
        if not tasks:
            messagebox.showerror("Ungültige Eingabe", "Bitte mindestens eine Aufgabe mit Code und Punkten angeben.")
            return None

        if not area_codes:
            messagebox.showerror("Ungültige Eingabe", "Bitte mindestens einen Aufgabenbereich angeben, z. B. A.")
            return None

        blocked = self._reject_max_points_change_for_scored_tasks(exam=exam, region_id=region_id, new_tasks=tasks)
        if blocked:
            return None

        region = RegionAssignment(
            region_id=region_id or f"r-{uuid4().hex[:12]}",
            student_pdf="",
            page_number=page_number,
            box=RegionBox(x0=box[0], y0=box[1], x1=box[2], y1=box[3]),
            tasks=tasks,
            assigned_area_codes=area_codes,
            is_read_complete=True,
            is_corrected=False,
            is_extra_page=False,
        )
        try:
            updated = self._deps.upsert_region_usecase.execute(exam=exam, region=region)
        except ExamConflictError as exc:
            messagebox.showerror("Speichern abgebrochen", str(exc))
            return None
        self._record_exam_payload_action(
            description=f"Bereich gespeichert: {region.assigned_area_codes[0]}",
            exam_id=updated.exam_id,
            before_payload=before_payload,
            after_payload=updated.to_dict(),
        )
        self.refresh_exam_overview()
        self._app.set_status("Bereich sofort gespeichert")
        return updated

    def delete_region_immediate(self, *, exam: ExamProject, region_id: str) -> ExamProject:
        """Remove one region without touching any other region's identity.

        Previously this relabeled every remaining region's `assigned_area_codes`
        by list index, which silently rewrote other regions' visible labels
        (and, before the region_id migration, corrupted any stored reference
        keyed by that label) on every unrelated deletion. Area codes are now
        stable once assigned (see `_next_area_label`) and `region_id` is the
        only technical identity, so no relabeling is needed here.
        """
        before_payload = exam.to_dict()
        exam.regions = [region for region in exam.regions if region.region_id != region_id]
        exam_file = self._save_exam_guarded(exam)
        if exam_file is None:
            return exam
        updated = self._deps.exam_repository.load_exam(exam_file)
        self._record_exam_payload_action(
            description="Bereich gelöscht",
            exam_id=updated.exam_id,
            before_payload=before_payload,
            after_payload=updated.to_dict(),
        )
        self.refresh_exam_overview()
        self._app.set_status("Bereich gelöscht")
        return updated

    def finish_reading_mode(self, *, exam: ExamProject) -> ExamProject:
        before_payload = exam.to_dict()
        # Standard pages without a region that are still open for someone
        # (a Deckblatt marked "ohne Bewertung" for everybody is not missing).
        missing_pages = pages_missing_markings(exam)

        if missing_pages:
            joined = ", ".join(str(page) for page in missing_pages)
            proceed = messagebox.askyesno(
                "Zuschnitt unvollständig",
                f"Es fehlen noch Markierungen auf Standardseiten: {joined}.\nTrotzdem abschließen?",
            )
            if not proceed:
                return exam

        try:
            updated = self._deps.set_reading_complete_usecase.execute(exam=exam, is_complete=True)
        except ExamConflictError as exc:
            messagebox.showerror("Speichern abgebrochen", str(exc))
            return exam
        self._record_exam_payload_action(
            description="Zuschnitt abgeschlossen",
            exam_id=updated.exam_id,
            before_payload=before_payload,
            after_payload=updated.to_dict(),
        )
        self.refresh_exam_overview()
        self._app.set_status("Zuschnitt abgeschlossen")
        return updated

    def set_name_region_immediate(
        self,
        *,
        exam: ExamProject,
        box: tuple[float, float, float, float],
        page_number: int,
    ) -> ExamProject:
        """Persist the (single, shared) Namenmodus region immediately.

        Unlike a standard Aufgaben-Bereich, a name region needs no
        accompanying task/points input, so a drag commits directly here
        instead of going through a draft-then-save step. Any previous
        `name_region` is replaced outright (only one may exist); each
        replacement is its own undo/redo entry, since the region is
        meaningful configuration independent of whether names have been
        typed yet.
        """
        before_payload = exam.to_dict()
        exam.name_region = RegionBox(x0=box[0], y0=box[1], x1=box[2], y1=box[3])
        exam.name_region_page = page_number
        exam_file = self._save_exam_guarded(exam)
        if exam_file is None:
            return exam
        updated = self._deps.exam_repository.load_exam(exam_file)
        self._record_exam_payload_action(
            description="Namensbereich gesetzt",
            exam_id=updated.exam_id,
            before_payload=before_payload,
            after_payload=updated.to_dict(),
        )
        self.refresh_exam_overview()
        self._app.set_status("Namensbereich gespeichert")
        return updated
