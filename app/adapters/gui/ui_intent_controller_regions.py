from __future__ import annotations

from uuid import uuid4

from app.adapters.gui.dialog_services import messagebox
from app.core.domain.models import ExamProject, ExtraPageAssignment, RegionAssignment, RegionBox, TaskDefinition


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
                "Im Extraseitenmodus koennen keine Aufgaben definiert werden. Bitte nur Bereich(e) zuordnen.",
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
        updated = self._deps.upsert_region_usecase.execute(exam=exam, region=region)
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
        exam_file = self._deps.exam_repository.save_exam(exam)
        updated = self._deps.exam_repository.load_exam(exam_file)
        self._record_exam_payload_action(
            description="Bereich geloescht",
            exam_id=updated.exam_id,
            before_payload=before_payload,
            after_payload=updated.to_dict(),
        )
        self.refresh_exam_overview()
        self._app.set_status("Bereich geloescht")
        return updated

    def delete_extra_page_assignment_immediate(self, *, exam: ExamProject, assignment_id: str) -> ExamProject:
        before_payload = exam.to_dict()
        exam.extra_page_assignments = [
            assignment for assignment in exam.extra_page_assignments if assignment.assignment_id != assignment_id
        ]
        exam_file = self._deps.exam_repository.save_exam(exam)
        updated = self._deps.exam_repository.load_exam(exam_file)
        self._record_exam_payload_action(
            description="Extraseiten-Zuordnung geloescht",
            exam_id=updated.exam_id,
            before_payload=before_payload,
            after_payload=updated.to_dict(),
        )
        self.refresh_exam_overview()
        self._app.set_status("Extraseiten-Zuordnung geloescht")
        return updated

    def finish_reading_mode(self, *, exam: ExamProject) -> ExamProject:
        before_payload = exam.to_dict()
        expected = set(range(1, exam.standard_page_count + 1))
        marked = {
            region.page_number
            for region in exam.regions
            if 1 <= region.page_number <= exam.standard_page_count
        }
        missing_pages = sorted(expected - marked)

        if missing_pages:
            joined = ", ".join(str(page) for page in missing_pages)
            proceed = messagebox.askyesno(
                "Unvollständiges Einlesen",
                f"Es fehlen noch Markierungen auf Standardseiten: {joined}.\nTrotzdem abschließen?",
            )
            if not proceed:
                return exam

        updated = self._deps.set_reading_complete_usecase.execute(exam=exam, is_complete=True)
        self._record_exam_payload_action(
            description="Einlesemodus abgeschlossen",
            exam_id=updated.exam_id,
            before_payload=before_payload,
            after_payload=updated.to_dict(),
        )
        self.refresh_exam_overview()
        self._app.set_status("Einlesemodus abgeschlossen")
        return updated

    def assign_extra_page_immediate(
        self,
        *,
        exam: ExamProject,
        student_pdf: str,
        page_number: int,
        box: tuple[float, float, float, float],
        area_codes: list[str],
        assignment_id: str | None = None,
    ) -> ExamProject | None:
        before_payload = exam.to_dict()
        normalized_areas = [code.strip().upper() for code in area_codes if code.strip()]
        if not normalized_areas:
            messagebox.showerror("Ungültige Eingabe", "Bitte mindestens einen Bereich angeben, z. B. A.")
            return None

        existing_areas = self._existing_standard_area_codes(exam)
        if not existing_areas:
            messagebox.showerror("Keine Bereiche", "Bitte zuerst Standardbereiche im Einlesemodus anlegen.")
            return None

        unknown = [code for code in normalized_areas if code not in existing_areas]
        if unknown:
            unknown_text = ", ".join(unknown)
            messagebox.showerror(
                "Unbekannter Bereich",
                f"Folgende Bereiche existieren nicht als Standardbereich: {unknown_text}",
            )
            return None

        existing = None
        if assignment_id is not None:
            existing = next(
                (item for item in exam.extra_page_assignments if item.assignment_id == assignment_id),
                None,
            )
        if existing is None:
            existing = next(
                (
                    assignment
                    for assignment in exam.extra_page_assignments
                    if assignment.student_pdf == student_pdf and assignment.page_number == page_number
                ),
                None,
            )

        assignment_id = existing.assignment_id if existing else f"x-{uuid4().hex[:10]}"
        assignment = ExtraPageAssignment(
            assignment_id=assignment_id,
            student_pdf=student_pdf,
            page_number=page_number,
            box=RegionBox(x0=box[0], y0=box[1], x1=box[2], y1=box[3]),
            assigned_area_codes=normalized_areas,
            is_read_complete=True,
            is_corrected=existing.is_corrected if existing else False,
        )

        replaced = False
        for index, item in enumerate(exam.extra_page_assignments):
            if item.assignment_id == assignment.assignment_id:
                exam.extra_page_assignments[index] = assignment
                replaced = True
                break
        if not replaced:
            exam.extra_page_assignments.append(assignment)

        exam_file = self._deps.exam_repository.save_exam(exam)
        updated = self._deps.exam_repository.load_exam(exam_file)
        self._record_exam_payload_action(
            description="Extraseite zugeordnet",
            exam_id=updated.exam_id,
            before_payload=before_payload,
            after_payload=updated.to_dict(),
        )
        self.refresh_exam_overview()
        self._app.set_status("Extraseite sofort zugeordnet")
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
        exam_file = self._deps.exam_repository.save_exam(exam)
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
