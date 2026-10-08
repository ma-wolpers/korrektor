from __future__ import annotations

from uuid import uuid4

from app.adapters.gui.dialog_services import messagebox
from app.core.domain.models import ExamProject, ExtraPageAssignment, RegionBox, UnscoredPage


class UiIntentControllerPageCoverageMixin:
    """Zuschnitt Schritt 2: pages without a template region - assign them to areas or mark them "ohne Bewertung".

    Every mutation is an `_immediate` action with one undo step (`_record_exam_payload_action`).
    Moved here from `ui_intent_controller_regions.py` (file-size rule): the single-page
    assignment and its deletion, plus the new unscored/for-all actions.
    """

    def delete_extra_page_assignment_immediate(self, *, exam: ExamProject, assignment_id: str) -> ExamProject:
        before_payload = exam.to_dict()
        exam.extra_page_assignments = [
            assignment for assignment in exam.extra_page_assignments if assignment.assignment_id != assignment_id
        ]
        exam_file = self._save_exam_guarded(exam)
        if exam_file is None:
            return exam
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
            messagebox.showerror("Keine Bereiche", "Bitte zuerst Standardbereiche im Zuschnitt anlegen.")
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

        exam_file = self._save_exam_guarded(exam)
        if exam_file is None:
            return None
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

    def set_pages_unscored_immediate(
        self, *, exam: ExamProject, student_pdfs: list[str], page_number: int, unscored: bool
    ) -> ExamProject | None:
        """Mark (or unmark) page ``page_number`` of the given students as "ohne Bewertung" - one undo step.

        Used for the current page (one student) and for "Seite N bei allen"
        (the students of `plan_page_for_all`, which never includes pages
        already assigned to a region). Unmarking only removes marks; it never
        touches extra-page assignments.
        """
        before_payload = exam.to_dict()
        targets = {(pdf, page_number) for pdf in student_pdfs}
        remaining = [item for item in exam.unscored_pages if (item.student_pdf, item.page_number) not in targets]
        if unscored:
            remaining.extend(UnscoredPage(student_pdf=pdf, page_number=page_number) for pdf in sorted(set(student_pdfs)))
        exam.unscored_pages = remaining
        exam_file = self._save_exam_guarded(exam)
        if exam_file is None:
            return None
        updated = self._deps.exam_repository.load_exam(exam_file)
        count = len(set(student_pdfs))
        self._record_exam_payload_action(
            description=f"Seite {page_number} {'ohne Bewertung' if unscored else 'wieder zu bewerten'} ({count} Person(en))",
            exam_id=updated.exam_id,
            before_payload=before_payload,
            after_payload=updated.to_dict(),
        )
        self.refresh_exam_overview()
        self._app.set_status(f"Seite {page_number}: {'ohne Bewertung' if unscored else 'wird bewertet'} ({count} Person(en))")
        return updated

    def assign_extra_pages_for_all_immediate(
        self,
        *,
        exam: ExamProject,
        page_number: int,
        box_by_pdf: dict[str, tuple[float, float, float, float]],
        area_codes: list[str],
    ) -> ExamProject | None:
        """Assign page ``page_number`` of several students to the same area(s) - one undo step.

        ``box_by_pdf`` contains only the students of `plan_page_for_all(...,
        "assign")`: students whose page is already assigned or "ohne
        Bewertung" are never passed in, so conscious individual decisions stay.
        Each box is that student's full visible page (the extra-page box model).
        """
        before_payload = exam.to_dict()
        normalized_areas = [code.strip().upper() for code in area_codes if code.strip()]
        existing_areas = self._existing_standard_area_codes(exam)
        unknown = [code for code in normalized_areas if code not in existing_areas]
        if not normalized_areas or unknown:
            messagebox.showerror(
                "Ungültige Eingabe",
                "Bitte vorhandene Bereiche angeben, z. B. A." + (f" Unbekannt: {', '.join(unknown)}" if unknown else ""),
            )
            return None
        for pdf, box in box_by_pdf.items():
            exam.extra_page_assignments.append(
                ExtraPageAssignment(
                    assignment_id=f"x-{uuid4().hex[:10]}",
                    student_pdf=pdf,
                    page_number=page_number,
                    box=RegionBox(x0=box[0], y0=box[1], x1=box[2], y1=box[3]),
                    assigned_area_codes=normalized_areas,
                    is_read_complete=True,
                )
            )
        exam_file = self._save_exam_guarded(exam)
        if exam_file is None:
            return None
        updated = self._deps.exam_repository.load_exam(exam_file)
        self._record_exam_payload_action(
            description=f"Seite {page_number} für {len(box_by_pdf)} Person(en) zugeordnet",
            exam_id=updated.exam_id,
            before_payload=before_payload,
            after_payload=updated.to_dict(),
        )
        self.refresh_exam_overview()
        self._app.set_status(f"Seite {page_number} für {len(box_by_pdf)} Person(en) zugeordnet")
        return updated
