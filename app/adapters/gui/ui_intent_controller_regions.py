from __future__ import annotations

from app.adapters.gui.dialog_services import messagebox
from app.core.domain.models import ExamProject, RegionBox
from app.core.domain.page_coverage import pages_missing_markings
from app.core.domain.region_edit import RegionEditResult, apply_region_delete, apply_region_upsert, region_placement_error
from app.core.domain.task_regions import TaskChangePlan, plan_task_changes
from app.core.domain.task_spec import TaskSpec
from app.core.domain.validation import ExamConflictError, ExamStructureError

_MAX_LISTED = 12


class UiIntentControllerRegionsMixin:
    """Regions (Superseiten and Einzelseiten) with their tasks - every edit is one undoable `_immediate` action.

    Order of checks in `upsert_region_immediate` (binding): placement (rule
    A4) -> unknown codes -> point change of a scored task (rejected) -> code
    re-created with old CSV scores of a different maximum (rejected, A5) ->
    confirm point changes -> pure edit on a copy (`region_edit`) -> confirm
    removed marks -> save -> one history action with full payload snapshots.
    Any "no"/error leaves the exam and the files unchanged.
    """

    @staticmethod
    def _existing_task_codes(exam: ExamProject) -> set[str]:
        """Codes of the exam's tasks (comments and scores may only reference these)."""
        return {task.code for task in exam.tasks}

    def _reject_scored_point_changes(self, *, exam: ExamProject, plan: TaskChangePlan) -> bool:
        """Block changing ``max_points`` of a task that already has recorded scores; ``True`` = rejected.

        Meilenstein 2.7: `TaskDefinition.max_points` stays historically stable
        once a task has been graded, so a computed grade never drifts. Since
        points belong to the task (not the region), this checks the task
        exam-wide, whichever region the edit came from.
        """
        if not plan.changed:
            return False
        scores = self._deps.score_repository.load_scores(exam=exam)
        already_scored = sorted(
            code for code, _old, _new in plan.changed if any(code in student_scores for student_scores in scores.values())
        )
        if not already_scored:
            return False
        messagebox.showerror(
            "Änderung abgelehnt",
            f"Die maximale Punktzahl von bereits bewerteten Aufgaben ({', '.join(already_scored)}) kann nicht mehr "
            "geändert werden, damit bereits erfasste Punkte/Noten nicht rückwirkend verfälscht werden.",
        )
        return True

    def _check_recreated_tasks(self, *, exam: ExamProject, plan: TaskChangePlan) -> str | None:
        """Rule A5 for codes created (again) while old scores remain in the CSV.

        Same maximum: the old scores apply again (returns a status note).
        Different maximum: rejected with a way out (returns ``None``). The
        CSV is never deleted. Returns ``""`` when nothing applies.
        """
        recorded = self._deps.score_repository.load_recorded_max_points(exam=exam)
        notes = []
        for code, points in plan.new:
            if code not in recorded:
                continue
            old_max, count = recorded[code]
            if abs(old_max - points) > 1e-9:
                messagebox.showerror(
                    "Alte Bewertungen vorhanden",
                    f"Für {code} sind noch Bewertungen von {count} Person(en) mit max. {old_max:g} P. gespeichert. "
                    f"Bitte {code}:{old_max:g} verwenden oder einen anderen Aufgaben-Code wählen.",
                )
                return None
            notes.append(f"alte Bewertungen von {count} Person(en) für {code} wieder aktiv")
        return "; ".join(notes)

    def upsert_region_immediate(
        self,
        *,
        exam: ExamProject,
        student_pdf: str,
        page_number: int,
        box: tuple[float, float, float, float],
        task_specs: list,
        area_codes: list[str] | None = None,
        region_id: str | None = None,
    ) -> ExamProject | None:
        """Create or change a region (``student_pdf == ""`` = Superseiten, else Einzelseiten); see the class docstring.

        ``task_specs`` are `TaskSpec`s or ``(code, points | None)`` tuples;
        ``points=None`` references an existing task. ``area_codes[0]`` is the
        preferred display label of a new region (the draft's label).
        """
        specs = [
            spec if isinstance(spec, TaskSpec) else TaskSpec(str(spec[0]).strip().upper(), spec[1])
            for spec in task_specs
            if (spec.code if isinstance(spec, TaskSpec) else str(spec[0])).strip()
        ]
        if not specs:
            messagebox.showerror("Ungültige Eingabe", "Bitte mindestens eine Aufgabe angeben, z. B. 4a:2 oder 4a-c:1,2,1.")
            return None
        problem = region_placement_error(exam, student_pdf, page_number)
        if problem:
            messagebox.showerror("Bereich nicht möglich", problem)
            return None
        plan = plan_task_changes(exam, specs)
        if plan.unknown:
            first = plan.unknown[0]
            messagebox.showerror(
                "Unbekannte Aufgabe",
                f"{', '.join(plan.unknown)} ist noch nicht festgelegt – Punkte angeben, z. B. {first}:2.",
            )
            return None
        if self._reject_scored_point_changes(exam=exam, plan=plan):
            return None
        note = self._check_recreated_tasks(exam=exam, plan=plan)
        if note is None:
            return None
        if plan.changed and not messagebox.askyesno(
            "Punkte ändern?",
            "\n".join(f"{code}: {old:g} → {new:g} P." for code, old, new in plan.changed)
            + "\n\nDie Punkte gelten für alle Bereiche dieser Aufgaben. Ändern?",
        ):
            return None
        try:
            result = apply_region_upsert(
                exam,
                region_id=region_id,
                student_pdf=student_pdf,
                page_number=page_number,
                box=box,
                specs=specs,
                label=(area_codes or [None])[0],
            )
        except ExamStructureError as exc:
            messagebox.showerror("Bereich nicht gespeichert", str(exc))
            return None
        label = next(r.assigned_area_codes[0] for r in result.exam.regions if r.region_id == result.region_id)
        return self._save_region_edit(exam, result, description=f"Bereich gespeichert: {label}", note=note)

    def delete_region_immediate(self, *, exam: ExamProject, region_id: str) -> ExamProject:
        """Remove one region (other regions keep id and label); orphaned tasks and invalid marks go with it.

        Returns the unchanged ``exam`` if the user declines or saving fails.
        """
        try:
            result = apply_region_delete(exam, region_id)
        except ExamStructureError as exc:
            messagebox.showerror("Bereich nicht gelöscht", str(exc))
            return exam
        updated = self._save_region_edit(exam, result, description="Bereich gelöscht", note="")
        return exam if updated is None else updated

    def _save_region_edit(self, exam: ExamProject, result: RegionEditResult, *, description: str, note: str) -> ExamProject | None:
        """Confirm removed marks, save ``result.exam`` and record one history action (payload snapshots)."""
        if result.removed_marks:
            listed = list(result.removed_marks[:_MAX_LISTED])
            if len(result.removed_marks) > _MAX_LISTED:
                listed.append(f"… und {len(result.removed_marks) - _MAX_LISTED} weitere")
            if not messagebox.askyesno(
                "Symbole werden entfernt",
                "Diese Symbole gehören danach zu keiner Aufgabe ihres Bereichs mehr und werden entfernt:\n"
                + "\n".join(f"• {item}" for item in listed)
                + "\n\nRückgängig ist mit Strg+Z möglich. Fortfahren?",
            ):
                return None
        before_payload = exam.to_dict()
        try:
            exam_file = self._deps.exam_repository.save_exam(result.exam)
        except ExamConflictError as exc:
            messagebox.showerror("Speichern abgebrochen", str(exc))
            return None
        updated = self._deps.exam_repository.load_exam(exam_file)
        self._record_exam_payload_action(
            description=description,
            exam_id=updated.exam_id,
            before_payload=before_payload,
            after_payload=updated.to_dict(),
        )
        self.refresh_exam_overview()
        extras = [note] if note else []
        if result.pruned_tasks:
            extras.append(f"Aufgabe(n) ohne Bereich entfernt: {', '.join(result.pruned_tasks)}")
        self._app.set_status(" · ".join([description, *extras]))
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
