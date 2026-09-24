from __future__ import annotations

from uuid import uuid4

from app.core.domain.models import ExamProject, TaskCategory


class UiIntentControllerTaskCategoriesMixin:
    """CRUD/Zuordnung fuer Aufgaben-Kategorien (Meilenstein 4 der Korrektor-Wunschliste).

    Anders als die globalen Notenschluessel-Vorlagen sind Kategorien Teil
    des Exams selbst (`ExamProject.task_categories`/`task_category_assignments`)
    - jede Mutation hier ist deshalb ein normaler Exam-Content-Mutator nach
    dem etablierten `<verb>_immediate`-Muster (Snapshot -> Mutation ->
    `save_exam` -> ein `_record_exam_payload_action`).
    """

    def save_task_category_immediate(self, *, exam: ExamProject, category_id: str | None, name: str) -> ExamProject | None:
        """Create (category_id=None) or rename (category_id known) a category; append/updates preserve order."""
        name = name.strip()
        if not name:
            return None

        before_payload = exam.to_dict()
        if category_id is None:
            exam.task_categories.append(TaskCategory(category_id=f"cat-{uuid4().hex[:10]}", name=name))
            description = f"Kategorie angelegt: {name}"
        else:
            category = next((item for item in exam.task_categories if item.category_id == category_id), None)
            if category is None:
                return None
            category.name = name
            description = f"Kategorie umbenannt: {name}"

        exam_file = self._save_exam_guarded(exam)
        if exam_file is None:
            return None
        updated = self._deps.exam_repository.load_exam(exam_file)
        self._record_exam_payload_action(
            description=description,
            exam_id=updated.exam_id,
            before_payload=before_payload,
            after_payload=updated.to_dict(),
        )
        self.refresh_exam_overview()
        self._app.set_status(description)
        return updated

    def delete_task_category_immediate(self, *, exam: ExamProject, category_id: str) -> ExamProject | None:
        """Remove a category; every task assigned to it becomes unkategorisiert (assignment entry removed, not the task)."""
        category = next((item for item in exam.task_categories if item.category_id == category_id), None)
        if category is None:
            return None

        before_payload = exam.to_dict()
        exam.task_categories = [item for item in exam.task_categories if item.category_id != category_id]
        exam.task_category_assignments = {
            task_code: assigned_category_id
            for task_code, assigned_category_id in exam.task_category_assignments.items()
            if assigned_category_id != category_id
        }
        exam_file = self._save_exam_guarded(exam)
        if exam_file is None:
            return None
        updated = self._deps.exam_repository.load_exam(exam_file)
        self._record_exam_payload_action(
            description=f"Kategorie geloescht: {category.name}",
            exam_id=updated.exam_id,
            before_payload=before_payload,
            after_payload=updated.to_dict(),
        )
        self.refresh_exam_overview()
        self._app.set_status(f"Kategorie geloescht: {category.name}")
        return updated

    def reorder_task_categories_immediate(self, *, exam: ExamProject, ordered_category_ids: list[str]) -> ExamProject | None:
        """Replace the display order of `task_categories` with `ordered_category_ids`.

        A category_id missing from `ordered_category_ids` (should not
        normally happen - the GUI always passes the full current set) is
        dropped rather than silently kept at an undefined position; an
        unknown id in `ordered_category_ids` is ignored.
        """
        categories_by_id = {item.category_id: item for item in exam.task_categories}
        reordered = [categories_by_id[cid] for cid in ordered_category_ids if cid in categories_by_id]
        if len(reordered) != len(exam.task_categories):
            return None

        before_payload = exam.to_dict()
        exam.task_categories = reordered
        exam_file = self._save_exam_guarded(exam)
        if exam_file is None:
            return None
        updated = self._deps.exam_repository.load_exam(exam_file)
        self._record_exam_payload_action(
            description="Kategorien-Reihenfolge geaendert",
            exam_id=updated.exam_id,
            before_payload=before_payload,
            after_payload=updated.to_dict(),
        )
        self.refresh_exam_overview()
        return updated

    def assign_task_to_category_immediate(
        self, *, exam: ExamProject, task_code: str, category_id: str | None
    ) -> ExamProject | None:
        """Assign `task_code` to `category_id`, or unassign it (`category_id=None`) - one task, at most one category."""
        task_code = task_code.strip().upper()
        if not task_code:
            return None
        if category_id is not None and not any(item.category_id == category_id for item in exam.task_categories):
            return None

        before_payload = exam.to_dict()
        if category_id is None:
            exam.task_category_assignments.pop(task_code, None)
            description = f"Aufgabe {task_code} unkategorisiert"
        else:
            exam.task_category_assignments[task_code] = category_id
            category = next(item for item in exam.task_categories if item.category_id == category_id)
            description = f"Aufgabe {task_code} zu Kategorie '{category.name}' zugeordnet"

        exam_file = self._save_exam_guarded(exam)
        if exam_file is None:
            return None
        updated = self._deps.exam_repository.load_exam(exam_file)
        self._record_exam_payload_action(
            description=description,
            exam_id=updated.exam_id,
            before_payload=before_payload,
            after_payload=updated.to_dict(),
        )
        self.refresh_exam_overview()
        self._app.set_status(description)
        return updated
