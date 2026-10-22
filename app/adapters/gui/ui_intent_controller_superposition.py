from __future__ import annotations

from uuid import uuid4

from app.adapters.gui.dialog_services import messagebox
from app.core.domain.annotation_sync import build_scored_annotation_clones
from app.core.domain.live_text import current_live_texts, live_text
from app.core.domain.model_students import LIVE_GRADE, LIVE_PERCENT, LIVE_POINTS, LiveValue
from app.core.domain.models import ExamProject, PdfAnnotation


class UiIntentControllerSuperpositionMixin:
    """Punkte-/Prozent-/Noten-Superposition: ein gemeinsamer Ort, individueller Inhalt je Person.

    Alle drei Aktionen sind Bulk-Vorgaenge ueber eine Personenmenge mit **einem**
    fachlichen Ergebnis (analog Supersymbol) - fehlt fuer irgendeine
    Zielperson ein benoetigter Wert, wird die **gesamte** Aktion
    abgelehnt statt teilweise ausgefuehrt: die Vollstaendigkeitspruefung
    laeuft komplett durch, bevor auch nur eine `PdfAnnotation` angelegt
    wird. Jede Markierung bekommt ihre Quelle (`LiveValue`) mit; ihr Text
    kommt beim Einfuegen, in der Vorschau und beim "Alle PDFs ueberschreiben"
    aus derselben Berechnung (`live_text`), zeigt also immer die aktuellen
    Punkte. Nutzt denselben `_save_annotation_mutation_immediate`-Tail wie
    `ui_intent_controller_annotations.py` (eine Sync-Gruppe, ein
    `HistoryAction`, Rollback bei Speicherfehlern).
    """

    def _live_contents_or_none(self, *, exam: ExamProject, value: LiveValue, student_ids: list[str]):
        """``(target_students, {student_id: text})``, or ``None`` after naming the first person without a value.

        Shared first pass of every Superposition: resolves all targets before
        any annotation exists (all-or-nothing, see the class docstring).
        """
        students_by_id = {student.student_id: student for student in exam.students}
        target_students = [students_by_id[sid] for sid in student_ids if sid in students_by_id]
        if not target_students:
            return None
        scores = self._deps.score_repository.load_scores(exam=exam)
        contents: dict[str, str] = {}
        for student in target_students:
            result = live_text(
                value,
                tasks=exam.tasks,
                scores_by_task=scores.get(student.student_id, {}),
                grading_scale_snapshot=exam.grading_scale_snapshot,
            )
            if result.text is None:
                messagebox.showerror(
                    "Superposition nicht möglich",
                    f"Für {student.display_name} {result.problem}. Deshalb konnte die Superposition nicht angewendet werden.",
                )
                return None
            contents[student.student_id] = result.text
        return target_students, contents

    def apply_scored_superposition_immediate(
        self,
        *,
        exam: ExamProject,
        region_id: str,
        page_number: int,
        task_codes: list[str],
        student_ids: list[str],
        annotation_type: str,
        color_hex: str,
        font_size: float,
        x: float,
        y: float,
        show_max_points: bool = False,
    ) -> ExamProject | None:
        """Place each target student's points sum over ``task_codes`` at one shared position, as one undoable action.

        ``task_codes`` empty = the whole exam. ``show_max_points`` inserts
        "7/10" instead of "7"; the maximum comes from the tasks themselves
        (`live_text`), so it is right for a whole task with several subtasks too.
        """
        value = LiveValue(LIVE_POINTS, tuple(task_codes), show_max_points)
        resolved = self._live_contents_or_none(exam=exam, value=value, student_ids=student_ids)
        if resolved is None:
            return None
        return self._apply_superposition_clones(
            exam=exam, region_id=region_id, page_number=page_number, target_students=resolved[0],
            content_by_student_id=resolved[1], live_value=value,
            annotation_type=annotation_type, color_hex=color_hex, font_size=font_size, x=x, y=y,
            description_prefix="Punkte-Superposition",
        )

    def apply_percent_superposition_immediate(
        self,
        *,
        exam: ExamProject,
        region_id: str,
        page_number: int,
        task_codes: list[str],
        student_ids: list[str],
        annotation_type: str,
        color_hex: str,
        font_size: float,
        x: float,
        y: float,
    ) -> ExamProject | None:
        """Place each target student's percentage of ``task_codes`` ("75 %"; empty = whole exam, as in the Auswertung)."""
        value = LiveValue(LIVE_PERCENT, tuple(task_codes))
        resolved = self._live_contents_or_none(exam=exam, value=value, student_ids=student_ids)
        if resolved is None:
            return None
        return self._apply_superposition_clones(
            exam=exam, region_id=region_id, page_number=page_number, target_students=resolved[0],
            content_by_student_id=resolved[1], live_value=value,
            annotation_type=annotation_type, color_hex=color_hex, font_size=font_size, x=x, y=y,
            description_prefix="Prozent-Superposition",
        )

    def apply_grade_superposition_immediate(
        self,
        *,
        exam: ExamProject,
        region_id: str,
        page_number: int,
        task_codes: list[str],
        student_ids: list[str],
        annotation_type: str,
        color_hex: str,
        font_size: float,
        x: float,
        y: float,
    ) -> ExamProject | None:
        """Place each target student's grade at one shared position, matching the Auswertung exactly.

        The grade is always exam-wide (all tasks of every Bereich, like the
        Auswertung) - earlier versions summed only the active Bereich, which
        silently diverged from the Auswertung. ``task_codes`` is therefore
        ignored; it stays for the uniform call-site contract.

        Requires an assigned Notenschluessel-Snapshot. ``page_number`` may
        come from a preview navigated independent of the Bereich
        (`_change_superposition_page`), so **every** target student must
        have that page; otherwise nothing is placed (all-or-nothing) and the
        message names each affected person with their page count.
        """
        if exam.grading_scale_snapshot is None:
            messagebox.showerror("Kein Notenschlüssel", "Dieser Klausur ist noch kein Notenschlüssel zugeordnet.")
            return None
        students_by_id = {student.student_id: student for student in exam.students}
        missing_page_students = [
            f"{student.display_name} ({student.page_count} Seiten)"
            for student in (students_by_id[sid] for sid in student_ids if sid in students_by_id)
            if page_number > student.page_count
        ]
        if missing_page_students:
            messagebox.showerror(
                "Superposition nicht möglich",
                f"Die Note kann nicht auf Seite {page_number} eingefügt werden, weil bei "
                f"{', '.join(missing_page_students)} nicht so viele Seiten vorhanden sind.",
            )
            return None
        value = LiveValue(LIVE_GRADE)
        resolved = self._live_contents_or_none(exam=exam, value=value, student_ids=student_ids)
        if resolved is None:
            return None
        return self._apply_superposition_clones(
            exam=exam, region_id=region_id, page_number=page_number, target_students=resolved[0],
            content_by_student_id=resolved[1], live_value=value,
            annotation_type=annotation_type, color_hex=color_hex, font_size=font_size, x=x, y=y,
            description_prefix="Noten-Superposition",
        )

    def refresh_live_contents(self, *, exam: ExamProject) -> tuple[ExamProject, list[tuple[PdfAnnotation, str]]]:
        """Bring every Superposition text to the current points before "Alle PDFs überschreiben".

        Returns the exam to export and ``(mark, problem)`` for marks whose
        value cannot be computed now - those keep their last text (the
        caller names them afterwards). Changed texts are saved to the exam
        file *without* an undo step: they are derived values, and preview
        and export recompute them anyway, so an undo that brings back an
        older text is harmless. A failing save keeps the in-memory texts
        (the PDF is still written with the current values).
        """
        texts = current_live_texts(exam, self._deps.score_repository.load_scores(exam=exam))
        problems: list[tuple[PdfAnnotation, str]] = []
        changed = False
        for annotation in exam.pdf_annotations:
            result = texts.get(annotation.annotation_id)
            if result is None:
                continue
            if result.text is None:
                problems.append((annotation, result.problem))
            elif result.text != annotation.content:
                annotation.content = result.text
                changed = True
        if not changed:
            return exam, problems
        try:
            exam = self._deps.exam_repository.load_exam(self._deps.exam_repository.save_exam(exam))
        except Exception:
            pass
        return exam, problems

    def _apply_superposition_clones(
        self,
        *,
        exam: ExamProject,
        region_id: str,
        page_number: int,
        target_students,
        content_by_student_id: dict[str, str],
        annotation_type: str,
        color_hex: str,
        font_size: float,
        x: float,
        y: float,
        description_prefix: str,
        live_value: LiveValue | None = None,
    ) -> ExamProject | None:
        """Shared tail: all values already resolved, only the clone-and-persist step remains."""
        before_payload = exam.to_dict()
        sync_group_id = f"sg-{uuid4().hex[:12]}"
        base = PdfAnnotation(
            annotation_id="",
            student_pdf="",
            page_number=page_number,
            annotation_type=annotation_type,
            content="",
            color_hex=color_hex,
            x=x,
            y=y,
            task_code="",
            region_id=region_id,
            font_size=font_size,
            rotation_deg=0.0,
            live_value=live_value,
        )
        clones = build_scored_annotation_clones(base, target_students, content_by_student_id, sync_group_id)
        if not clones:
            return None
        exam.pdf_annotations.extend(clones)

        def _rollback() -> None:
            exam.pdf_annotations[:] = [item for item in exam.pdf_annotations if item.sync_group_id != sync_group_id]

        return self._save_annotation_mutation_immediate(
            exam=exam,
            description=f"{description_prefix} gesetzt ({len(clones)} Personen)",
            before_payload=before_payload,
            rollback=_rollback,
        )
