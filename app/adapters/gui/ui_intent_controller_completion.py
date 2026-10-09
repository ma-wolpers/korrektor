from __future__ import annotations

from typing import Sequence

from app.adapters.gui.dialog_services import messagebox
from app.core.domain.models import ExamProject, PersonTaskCompletion


class UiIntentControllerCompletionMixin:
    """"Fertig" per person and (sub)task (schema v2); locks the points of that task in the correction view."""

    def is_person_task_finished(self, *, exam: ExamProject, student_id: str, task_code: str) -> bool:
        """Whether ``student_id`` is marked finished for ``task_code``."""
        code = task_code.strip().upper()
        return any(
            item.student_id == student_id and item.task_code == code and item.is_finished
            for item in exam.person_task_completions
        )

    def are_person_tasks_finished(self, *, exam: ExamProject, student_id: str, task_codes: Sequence[str]) -> bool:
        """True if ``student_id`` is finished for *every* code in ``task_codes`` (``False`` for no codes)."""
        codes = {code.strip().upper() for code in task_codes if code.strip()}
        finished = {item.task_code for item in exam.person_task_completions if item.student_id == student_id and item.is_finished}
        return bool(codes) and codes <= finished

    def count_persons_tasks_finished(self, *, exam: ExamProject, task_codes: Sequence[str], student_ids: Sequence[str]) -> int:
        """Count students (unique sequence expected, see the GUI's canonical caller) finished for every code.

        One pass over the completions builds ``{student: finished codes}``,
        one pass over ``student_ids`` counts - O(completions + persons).
        """
        codes = {code.strip().upper() for code in task_codes if code.strip()}
        if not codes:
            return 0
        finished: dict[str, set[str]] = {}
        for item in exam.person_task_completions:
            if item.is_finished:
                finished.setdefault(item.student_id, set()).add(item.task_code)
        return sum(1 for student_id in student_ids if codes <= finished.get(student_id, set()))

    def set_persons_tasks_finished_immediate(
        self,
        *,
        exam: ExamProject,
        student_ids: Sequence[str],
        task_codes: Sequence[str],
        is_finished: bool,
    ) -> ExamProject | None:
        """Set/clear "Fertig" for every (student, task) pair, with one undo step.

        All-or-nothing validation: ``student_ids`` is de-duplicated (stable
        order) but never filtered - one unknown person or unknown task code
        rejects the whole call (no partial update, no history entry), since
        the ids always come from the GUI's canonical population and an
        unknown one signals an inconsistent state.
        """
        codes = list(dict.fromkeys(code.strip().upper() for code in task_codes if code.strip()))
        if not codes:
            messagebox.showerror("Ungültige Eingabe", "Aufgabe fehlt.")
            return None
        target_ids = list(dict.fromkeys(student_ids))
        if not target_ids:
            messagebox.showerror("Ungültige Eingabe", "Keine Personen für Fertigstatus ausgewählt.")
            return None
        known_ids = {student.student_id for student in exam.students}
        unknown_ids = [student_id for student_id in target_ids if student_id not in known_ids]
        if unknown_ids:
            messagebox.showerror("Ungültige Eingabe", f"Unbekannte Person(en) für Fertigstatus: {', '.join(unknown_ids)}")
            return None
        unknown_codes = [code for code in codes if code not in {task.code for task in exam.tasks}]
        if unknown_codes:
            messagebox.showerror("Unbekannte Aufgabe", f"Diese Aufgabe(n) existieren nicht (mehr): {', '.join(unknown_codes)}")
            return None

        before_payload = exam.to_dict()
        pairs = {(student_id, code) for student_id in target_ids for code in codes}
        exam.person_task_completions = [
            item for item in exam.person_task_completions if (item.student_id, item.task_code) not in pairs
        ]
        if is_finished:
            exam.person_task_completions.extend(
                PersonTaskCompletion(student_id=student_id, task_code=code, is_finished=True)
                for student_id in target_ids
                for code in codes
            )
        exam_file = self._save_exam_guarded(exam)
        if exam_file is None:
            return None
        updated = self._deps.exam_repository.load_exam(exam_file)
        label = ", ".join(codes)
        state = "fertig" if is_finished else "offen"
        if len(target_ids) == 1:
            description = f"Aufgabe {label} als {state} markiert"
        else:
            description = f"Aufgabe {label}: {len(target_ids)} Personen als {state} markiert"
        self._record_exam_payload_action(
            description=description,
            exam_id=updated.exam_id,
            before_payload=before_payload,
            after_payload=updated.to_dict(),
        )
        self.refresh_exam_overview()
        self._app.set_status(description)
        return updated
