from __future__ import annotations

import csv
from pathlib import Path

from app.adapters.gui.dialog_services import filedialog, messagebox
from app.core.domain.models import ExamProject


class UiIntentControllerScoringMixin:
    def save_score_immediate(
        self,
        *,
        exam: ExamProject,
        student_id: str,
        task_code: str,
        points_text: str,
        max_points_text: str,
    ) -> bool:
        if not task_code.strip():
            messagebox.showinfo("Hinweis", "Bitte zuerst einen Aufgaben-Code eintragen, z. B. A1.")
            return False

        try:
            points = float(points_text.replace(",", ".")) if points_text.strip() else 0.0
            max_points = float(max_points_text.replace(",", ".")) if max_points_text.strip() else 0.0
        except ValueError:
            messagebox.showerror("Ungültige Eingabe", "Punkte und Max-Punkte müssen Zahlen sein.")
            return False

        score_file = Path(exam.folder_path) / "korrektor_scores.csv"
        before_csv = self._read_text_or_none(score_file)

        self._deps.save_score_usecase.execute(
            exam=exam,
            student_id=student_id,
            task_code=task_code.strip(),
            points=points,
            max_points=max_points,
        )
        after_csv = self._read_text_or_none(score_file)
        if before_csv != after_csv:
            self._record_history_action(
                description=f"Punkte gesetzt: {task_code.strip()}",
                undo=lambda: self._restore_text(score_file, before_csv),
                redo=lambda: self._restore_text(score_file, after_csv),
            )
        self._app.set_status("Punkte sofort gespeichert")
        return True

    def load_saved_points(self, *, exam: ExamProject, student_id: str, task_code: str) -> str | None:
        score_file = Path(exam.folder_path) / "korrektor_scores.csv"
        if not score_file.exists():
            return None

        points_col = f"{task_code.strip()}_points"
        try:
            with score_file.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    if row.get("student_id", "").strip() != student_id:
                        continue
                    raw_points = str(row.get(points_col, "") or "").strip()
                    return raw_points or None
        except Exception:
            return None
        return None

    def load_saved_comment(self, *, exam: ExamProject, student_id: str, task_code: str) -> str | None:
        normalized_task = task_code.strip().upper()
        if not normalized_task:
            return None
        return exam.task_comments.get(student_id, {}).get(normalized_task)

    def set_task_comment_immediate(
        self,
        *,
        exam: ExamProject,
        student_id: str,
        task_code: str,
        comment_text: str,
    ) -> ExamProject | None:
        normalized_task = task_code.strip().upper()
        if not normalized_task:
            messagebox.showerror("Ungueltige Eingabe", "Aufgabencode fehlt.")
            return None

        if student_id not in {student.student_id for student in exam.students}:
            messagebox.showerror("Ungueltige Eingabe", "Unbekannte Person fuer Aufgabenkommentar.")
            return None

        valid_tasks = self._existing_task_codes(exam)
        if normalized_task not in valid_tasks:
            messagebox.showerror("Unbekannte Aufgabe", f"Aufgabe {normalized_task} existiert nicht.")
            return None

        normalized_comment = comment_text.strip()
        current_comment = exam.task_comments.get(student_id, {}).get(normalized_task, "")
        if current_comment == normalized_comment:
            return exam

        before_payload = exam.to_dict()

        if normalized_comment:
            by_student = exam.task_comments.setdefault(student_id, {})
            by_student[normalized_task] = normalized_comment
        else:
            by_student = exam.task_comments.get(student_id)
            if by_student is not None and normalized_task in by_student:
                del by_student[normalized_task]
                if not by_student:
                    del exam.task_comments[student_id]

        exam_file = self._deps.exam_repository.save_exam(exam)
        updated = self._deps.exam_repository.load_exam(exam_file)
        self._record_exam_payload_action(
            description=(
                f"Aufgabenkommentar gesetzt: {normalized_task}"
                if normalized_comment
                else f"Aufgabenkommentar entfernt: {normalized_task}"
            ),
            exam_id=updated.exam_id,
            before_payload=before_payload,
            after_payload=updated.to_dict(),
        )
        self.refresh_exam_overview()
        self._app.set_status(
            f"Kommentar gespeichert: {normalized_task}"
            if normalized_comment
            else f"Kommentar entfernt: {normalized_task}"
        )
        return updated

    def export_scores_for_exam(self, *, exam: ExamProject) -> bool:
        default_name = f"{exam.exam_name}_punkte_export.csv" if exam.exam_name.strip() else "punkte_export.csv"
        output_path_raw = filedialog.asksaveasfilename(
            title="Punkte exportieren",
            defaultextension=".csv",
            filetypes=[("CSV-Dateien", "*.csv"), ("Alle Dateien", "*.*")],
            initialdir=str(Path(exam.folder_path)),
            initialfile=default_name,
        )
        if not output_path_raw:
            return False

        output_path = Path(output_path_raw)
        try:
            self._deps.export_scores_usecase.execute(exam=exam, output_csv=output_path)
        except Exception as exc:
            messagebox.showerror("Export fehlgeschlagen", str(exc))
            return False

        self._app.set_status(f"Punkte exportiert: {output_path.name}")
        return True

    def load_scores_for_exam(self, *, exam: ExamProject) -> dict[str, dict[str, float]]:
        """Load every recorded points value for `exam`, keyed by student_id then task_code.

        Thin pass-through to the score repository, used by the Supersymbol
        filter to evaluate a points condition across all students at once.
        """
        return self._deps.score_repository.load_scores(exam=exam)
