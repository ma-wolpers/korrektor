from __future__ import annotations

from typing import Sequence

from app.adapters.gui.dialog_services import messagebox
from app.core.domain.models import ExamProject, PersonAreaCompletion


class UiIntentControllerCompletionMixin:
    @staticmethod
    def _area_label_for_region(exam: ExamProject, region_id: str) -> str:
        """Resolve a region's display label for status/history messages.

        `region_id` stays the technical lookup key; this only affects text
        shown to the user, never how `PersonAreaCompletion` entries are matched.
        """
        region = next((item for item in exam.regions if item.region_id == region_id), None)
        if region is not None and region.assigned_area_codes:
            return region.assigned_area_codes[0]
        return region_id

    def is_person_area_finished(self, *, exam: ExamProject, student_id: str, region_id: str) -> bool:
        """Check whether the given student is marked finished for this region."""
        normalized_region_id = region_id.strip()
        if not normalized_region_id:
            return False
        return any(
            item.student_id == student_id and item.region_id == normalized_region_id and item.is_finished
            for item in exam.person_area_completions
        )

    def count_persons_area_finished(
        self, *, exam: ExamProject, region_id: str, student_ids: Sequence[str]
    ) -> int:
        """Count how many of the given students are marked finished for this region.

        Expects `student_ids` to already be a unique sequence (contract, not
        re-deduplicated here) — the same invariant `MainWindow._correction_region_student_ids()`
        establishes at its one canonical call site. Deliberately no defensive
        de-duplication here: the population is canonicalized at exactly one
        place, not re-guarded in every function that consumes it — otherwise
        different consumers could drift apart depending on whether (or how)
        each one deduplicates. A call with a list that contains duplicates
        therefore overcounts accordingly (each duplicate is counted again)
        — a documented contract violation by the calling side, not a bug in
        this method.

        One pass over `exam.person_area_completions` builds the finished-id
        set, then one pass over `student_ids` counts matches — O(Completions
        + Personen), not the O(N×M) full-CSV-per-cell cost that
        `load_saved_points` would incur if called once per person and task.
        """
        normalized_region_id = region_id.strip()
        if not normalized_region_id:
            return 0
        finished_ids = {
            item.student_id
            for item in exam.person_area_completions
            if item.region_id == normalized_region_id and item.is_finished
        }
        return sum(1 for student_id in student_ids if student_id in finished_ids)

    def set_persons_area_finished_immediate(
        self,
        *,
        exam: ExamProject,
        student_ids: Sequence[str],
        region_id: str,
        is_finished: bool,
    ) -> ExamProject | None:
        """Set/clear the finished flag for one or more student+region pairs, with undo/redo.

        Generalizes the former single-student `set_person_area_finished_immediate`:
        for `len(student_ids) == 1` behavior is unchanged byte-for-byte (same
        error messages, same status/history texts) — everything below only
        branches on the count to pick between the singular and plural text.

        Validation is all-or-nothing: `student_ids` is de-duplicated
        (`dict.fromkeys`, stable order) but never silently filtered down. If
        even one id is unknown, the *entire* call is rejected (no partial
        update, no `HistoryAction`) rather than proceeding with the known
        subset — `student_ids` always comes from
        `MainWindow._correction_region_student_ids()` internally, so an
        unknown id here signals an inconsistent program/data state, not a
        legitimate partial case worth a best-effort attempt.

        Unlike the read-only `count_persons_area_finished`, this method
        deliberately does de-duplicate its own input: it writes and creates
        a `HistoryAction`, so an accidental duplicate here must not distort
        the reported person count or do redundant work, whereas a miscount
        in a display-only counter is comparatively harmless.
        """
        normalized_region_id = region_id.strip()
        if not normalized_region_id:
            messagebox.showerror("Ungueltige Eingabe", "Bereich fehlt.")
            return None

        target_ids = list(dict.fromkeys(student_ids))
        if not target_ids:
            messagebox.showerror("Ungueltige Eingabe", "Keine Personen fuer Fertigstatus ausgewaehlt.")
            return None

        known_ids = {student.student_id for student in exam.students}
        unknown_ids = [student_id for student_id in target_ids if student_id not in known_ids]
        if unknown_ids:
            messagebox.showerror(
                "Ungueltige Eingabe",
                f"Unbekannte Person(en) fuer Fertigstatus: {', '.join(unknown_ids)}",
            )
            return None

        if normalized_region_id not in {region.region_id for region in exam.regions}:
            messagebox.showerror("Unbekannter Bereich", "Dieser Bereich existiert nicht (mehr).")
            return None

        area_label = self._area_label_for_region(exam, normalized_region_id)
        before_payload = exam.to_dict()
        target_id_set = set(target_ids)
        exam.person_area_completions = [
            item
            for item in exam.person_area_completions
            if not (item.student_id in target_id_set and item.region_id == normalized_region_id)
        ]
        if is_finished:
            exam.person_area_completions.extend(
                PersonAreaCompletion(student_id=student_id, region_id=normalized_region_id, is_finished=True)
                for student_id in target_ids
            )

        exam_file = self._save_exam_guarded(exam)
        if exam_file is None:
            return None
        updated = self._deps.exam_repository.load_exam(exam_file)
        if len(target_ids) == 1:
            description = (
                f"Bereich als fertig markiert: {area_label}"
                if is_finished
                else f"Bereich als offen markiert: {area_label}"
            )
            status = (
                f"Fertigstatus aktualisiert: {area_label}"
                if is_finished
                else f"Fertigstatus entfernt: {area_label}"
            )
        else:
            description = (
                f"Bereich {area_label}: {len(target_ids)} Personen als fertig markiert"
                if is_finished
                else f"Bereich {area_label}: {len(target_ids)} Personen als offen markiert"
            )
            status = description
        self._record_exam_payload_action(
            description=description,
            exam_id=updated.exam_id,
            before_payload=before_payload,
            after_payload=updated.to_dict(),
        )
        self.refresh_exam_overview()
        self._app.set_status(status)
        return updated
