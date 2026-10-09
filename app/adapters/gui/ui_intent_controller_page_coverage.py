from __future__ import annotations

from app.adapters.gui.dialog_services import messagebox
from app.core.domain.models import ExamProject, UnscoredPage
from app.core.domain.page_coverage import assigned_set


class UiIntentControllerPageCoverageMixin:
    """Zuschnitt Schritt 2 (Einzelseiten): mark pages "ohne Bewertung" - one undo step per action.

    Einzelseiten-Bereiche themselves are ordinary regions with a
    ``student_pdf`` and go through `upsert_region_immediate` /
    `delete_region_immediate` (the former per-page area assignment and
    "Für alle zuordnen…" were replaced by them, see ARCHITEKTUR).
    """

    def set_pages_unscored_immediate(
        self, *, exam: ExamProject, student_pdfs: list[str], page_number: int, unscored: bool
    ) -> ExamProject | None:
        """Mark (or unmark) page ``page_number`` of the given students as "ohne Bewertung" - one undo step.

        Used for the current page (one student) and for "Seite N bei allen"
        (the students of `plan_page_for_all`). A page that carries an
        Einzelseiten-Bereich is never marked (it is being scored); such
        students are skipped. Unmarking only removes marks.
        """
        before_payload = exam.to_dict()
        with_regions = assigned_set(exam)
        targets = {(pdf, page_number) for pdf in student_pdfs if not (unscored and (pdf, page_number) in with_regions)}
        if not targets:
            messagebox.showinfo("Hinweis", "Auf dieser Seite ist ein Einzelseiten-Bereich markiert – sie wird bewertet.")
            return None
        remaining = [item for item in exam.unscored_pages if (item.student_pdf, item.page_number) not in targets]
        if unscored:
            remaining.extend(UnscoredPage(student_pdf=pdf, page_number=page_number) for pdf, _page in sorted(targets))
        exam.unscored_pages = remaining
        exam_file = self._save_exam_guarded(exam)
        if exam_file is None:
            return None
        updated = self._deps.exam_repository.load_exam(exam_file)
        count = len(targets)
        self._record_exam_payload_action(
            description=f"Seite {page_number} {'ohne Bewertung' if unscored else 'wieder zu bewerten'} ({count} Person(en))",
            exam_id=updated.exam_id,
            before_payload=before_payload,
            after_payload=updated.to_dict(),
        )
        self.refresh_exam_overview()
        self._app.set_status(f"Seite {page_number}: {'ohne Bewertung' if unscored else 'wird bewertet'} ({count} Person(en))")
        return updated
