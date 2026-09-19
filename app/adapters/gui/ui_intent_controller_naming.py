from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.adapters.gui.dialog_services import messagebox
from app.core.domain.models import ExamProject
from app.core.domain.rename_planning import find_external_conflicts, plan_target_filenames, validate_rename_set


class UiIntentControllerNamingMixin:
    @staticmethod
    def _rename_file(folder: Path, source_name: str, target_name: str) -> None:
        (folder / source_name).rename(folder / target_name)

    @classmethod
    def _apply_staged_renames(cls, folder: Path, pairs: list[tuple[str, str]]) -> None:
        """Rename every (old, new) filename pair via a unique temp name in between.

        Two phases (old -> temp, then temp -> new) so pairs that swap names
        (A->B and B->A in the same batch) never collide on an intermediate
        state. If any single rename in either phase fails, every rename
        already applied within this call is undone, in reverse order,
        before the original `OSError` is re-raised - the folder ends up
        exactly as it was before this call. This does not protect against a
        hard process/OS crash mid-call (see docs/ARCHITEKTUR.md); it only
        guarantees a clean rollback for errors raised during the call.
        """
        temp_by_old = {old: f"{old}.__rename_tmp_{uuid4().hex[:8]}__" for old, _new in pairs}
        applied: list[tuple[str, str]] = []

        def _rollback() -> None:
            for source, target in reversed(applied):
                try:
                    cls._rename_file(folder, target, source)
                except OSError:
                    pass

        try:
            for old, _new in pairs:
                temp = temp_by_old[old]
                cls._rename_file(folder, old, temp)
                applied.append((old, temp))
            for old, new in pairs:
                temp = temp_by_old[old]
                cls._rename_file(folder, temp, new)
                applied.append((temp, new))
        except OSError:
            _rollback()
            raise

    def rename_students_immediate(
        self,
        *,
        exam: ExamProject,
        name_by_student_id: dict[str, str],
    ) -> ExamProject | None:
        """Batch-rename every student's PDF from newly entered Namenmodus names.

        One rollback-capable operation: preflight (1:1 rename-set check,
        target-name planning, external-conflict check) -> staged physical
        rename -> in-memory exam update -> `save_exam` -> a single
        `HistoryAction`. A failure at any step reverts whatever was already
        applied, so the filesystem and the exam JSON never end up
        disagreeing about filenames (see docs/ARCHITEKTUR.md for the
        accepted crash-atomicity limitation). `student_id` is never
        touched - only `pdf_filename` (sanitized target) and `display_name`
        (the raw entered name, unmodified) change.
        """
        folder = Path(exam.folder_path)
        actual_pdf_filenames = {path.name for path in folder.glob("*.pdf")}

        set_errors = validate_rename_set(exam.students, actual_pdf_filenames)
        if set_errors:
            messagebox.showerror("Umbenennen nicht moeglich", "\n".join(set_errors))
            return None

        plan = plan_target_filenames(exam.students, name_by_student_id)
        if plan.errors:
            messagebox.showerror("Ungueltige Namen", "\n".join(plan.errors))
            return None

        rename_set_filenames = {student.pdf_filename for student in exam.students}
        external_conflicts = find_external_conflicts(
            plan.target_filename_by_student_id, actual_pdf_filenames, rename_set_filenames
        )
        if external_conflicts:
            messagebox.showerror("Umbenennen nicht moeglich", "\n".join(external_conflicts))
            return None

        rename_operations = [
            (student.student_id, student.pdf_filename, plan.target_filename_by_student_id[student.student_id])
            for student in exam.students
            if plan.target_filename_by_student_id[student.student_id] != student.pdf_filename
        ]
        if not rename_operations:
            messagebox.showinfo("Hinweis", "Keine Umbenennung noetig - alle Namen entsprechen bereits den Dateinamen.")
            return exam

        rename_pairs = [(old, new) for _sid, old, new in rename_operations]
        old_to_new = {old: new for old, new in rename_pairs}

        self._app.invalidate_doc_cache(old_to_new.keys())
        before_payload = exam.to_dict()

        try:
            self._apply_staged_renames(folder, rename_pairs)
        except OSError as exc:
            messagebox.showerror("Umbenennen fehlgeschlagen", f"Dateisystem-Fehler, keine Datei wurde veraendert: {exc}")
            return None

        for student in exam.students:
            new_filename = old_to_new.get(student.pdf_filename)
            if new_filename is None:
                continue
            student.display_name = name_by_student_id[student.student_id].strip()
            student.pdf_filename = new_filename
        for assignment in exam.extra_page_assignments:
            if assignment.student_pdf in old_to_new:
                assignment.student_pdf = old_to_new[assignment.student_pdf]
        for annotation in exam.pdf_annotations:
            if annotation.student_pdf in old_to_new:
                annotation.student_pdf = old_to_new[annotation.student_pdf]

        try:
            exam_file = self._deps.exam_repository.save_exam(exam)
            updated = self._deps.exam_repository.load_exam(exam_file)
        except Exception as exc:
            try:
                self._apply_staged_renames(folder, [(new, old) for old, new in rename_pairs])
            except OSError:
                pass
            messagebox.showerror(
                "Umbenennen fehlgeschlagen",
                f"Klausur konnte nicht gespeichert werden, Dateinamen wurden zurueckgesetzt: {exc}",
            )
            return None

        after_payload = updated.to_dict()
        exam_file_path = exam_file

        def _undo() -> None:
            self._app.invalidate_doc_cache(new for _old, new in rename_pairs)
            self._apply_staged_renames(folder, [(new, old) for old, new in rename_pairs])
            self._write_exam_payload(exam_file_path, before_payload)

        def _redo() -> None:
            self._app.invalidate_doc_cache(old for old, _new in rename_pairs)
            self._apply_staged_renames(folder, rename_pairs)
            self._write_exam_payload(exam_file_path, after_payload)

        self._record_history_action(
            description=f"{len(rename_operations)} Schueler:in(nen) umbenannt",
            undo=_undo,
            redo=_redo,
        )
        self.refresh_exam_overview()
        self._app.set_status(f"{len(rename_operations)} PDF(s) umbenannt")
        return updated
