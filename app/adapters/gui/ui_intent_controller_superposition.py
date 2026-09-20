from __future__ import annotations

from uuid import uuid4

from app.adapters.gui.dialog_services import messagebox
from app.core.domain.annotation_sync import build_scored_annotation_clones
from app.core.domain.models import ExamProject, PdfAnnotation
from app.core.domain.score_filter import compute_student_value


class UiIntentControllerSuperpositionMixin:
    """Punkte-/Noten-Superposition (Meilenstein 3): ein gemeinsamer Ort, individueller Inhalt je Person.

    Beide Aktionen sind Bulk-Vorgaenge ueber eine Personenmenge mit **einem**
    fachlichen Ergebnis (analog Supersymbol) - fehlt fuer irgendeine
    Zielperson ein benoetigter Wert, wird die **gesamte** Aktion
    abgelehnt statt teilweise ausgefuehrt: die Vollstaendigkeitspruefung
    laeuft komplett durch, bevor auch nur eine `PdfAnnotation` angelegt
    wird, nie mit bereits teilweise erzeugten Annotationen im Fehlerfall.
    Nutzt denselben `_save_annotation_mutation_immediate`-Tail wie
    `ui_intent_controller_annotations.py` (eine Sync-Gruppe, ein
    `HistoryAction`, Rollback bei Speicherfehlern).
    """

    @staticmethod
    def _area_code_for_region(exam: ExamProject, region_id: str) -> str:
        region = next((item for item in exam.regions if item.region_id == region_id), None)
        if region is None or not region.assigned_area_codes:
            return region_id
        return region.assigned_area_codes[0]

    def _resolve_superposition_targets_or_none(
        self, *, exam: ExamProject, region_id: str, task_codes: list[str], student_ids: list[str]
    ) -> tuple[list, dict[str, float]] | None:
        """Resolve target students and their summed points, or show a diagnostic error and return None.

        Shared first pass for both 3.1 (Punkte) and 3.2 (Note): identifies
        exactly which person/Aufgabe is missing a value rather than a
        generic "unvollstaendig" message, and aborts before either caller
        creates any annotation - see the class docstring.
        """
        students_by_id = {student.student_id: student for student in exam.students}
        target_students = [students_by_id[sid] for sid in student_ids if sid in students_by_id]
        if not target_students:
            return None

        scores = self._deps.score_repository.load_scores(exam=exam)
        area_code = self._area_code_for_region(exam, region_id)
        values_by_student_id: dict[str, float] = {}
        for student in target_students:
            student_scores = scores.get(student.student_id, {})
            value = compute_student_value(student_scores, task_codes)
            if value is None:
                missing_code = next((code for code in task_codes if code not in student_scores), task_codes[0])
                messagebox.showerror(
                    "Superposition nicht moeglich",
                    f"Fuer {student.display_name} fehlt die Bewertung von Aufgabe {missing_code} im Bereich "
                    f"{area_code}. Deshalb konnte die Superposition nicht angewendet werden.",
                )
                return None
            values_by_student_id[student.student_id] = value
        return target_students, values_by_student_id

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
    ) -> ExamProject | None:
        """Place each target student's own points-sum at one shared position, as one undoable action.

        Snapshot semantics match Supersymbol: a one-time bulk apply, not a
        live filter - later points changes never retroactively move or
        recompute already-placed Superposition annotations. Re-running the
        action (with the same/updated targets) applies fresh values again.
        """
        resolved = self._resolve_superposition_targets_or_none(
            exam=exam, region_id=region_id, task_codes=task_codes, student_ids=student_ids
        )
        if resolved is None:
            return None
        target_students, values_by_student_id = resolved
        content_by_student_id = {
            student_id: f"{value:g}" for student_id, value in values_by_student_id.items()
        }

        return self._apply_superposition_clones(
            exam=exam,
            region_id=region_id,
            page_number=page_number,
            target_students=target_students,
            content_by_student_id=content_by_student_id,
            annotation_type=annotation_type,
            color_hex=color_hex,
            font_size=font_size,
            x=x,
            y=y,
            description_prefix="Punkte-Superposition",
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

        The grade is resolved via `compute_student_result_for_exam` - the
        same exam-wide computation the Auswertung uses (`all_tasks` across
        every Bereich/region, not just the currently selected one). This is
        deliberate: earlier this method computed its own, Bereich-scoped
        grade (points/max-points summed only over `task_codes` of the
        active Bereich) via `resolve_grade` directly, which silently
        diverged from the Auswertung's exam-wide grade for any exam with
        more than one Bereich - the two are only equal by coincidence when
        a Bereich happens to cover the whole exam. The original wish for
        this feature explicitly says "(siehe Auswertung)"; reusing the
        Auswertung's own computation instead of a second, parallel
        implementation is the only way to guarantee that. `region_id`/
        `page_number`/`task_codes` stay in the signature (same call-site
        contract as `apply_scored_superposition_immediate`, both dispatched
        uniformly from `main_window_supersymbol.py`) but `task_codes` no
        longer influences the grade value itself - only `region_id`/
        `page_number` are still used, for placing the annotation.

        Requires an assigned Notenschluessel-Snapshot; without one the
        action is rejected outright before resolving any student data.
        For each target student, exactly one of three distinguishable
        reasons aborts the whole action (all-or-nothing, matching
        `apply_scored_superposition_immediate`'s validate-then-execute
        contract): the exam-wide Auswertung is incomplete for that student
        (`total_achieved_points is None`), the exam has no bewertbare
        Aufgaben at all (`total_max_points <= 0`), or the student's
        percentage falls below the lowest Notenschluessel-Schwelle
        (`grade_label is None` despite a complete, positive total - the
        `GradingError` case, already caught inside `compute_student_result`).
        """
        if exam.grading_scale_snapshot is None:
            messagebox.showerror(
                "Kein Notenschluessel", "Dieser Klausur ist noch kein Notenschluessel zugeordnet."
            )
            return None

        students_by_id = {student.student_id: student for student in exam.students}
        target_students = [students_by_id[sid] for sid in student_ids if sid in students_by_id]
        if not target_students:
            return None

        scores = self._deps.score_repository.load_scores(exam=exam)
        content_by_student_id: dict[str, str] = {}
        for student in target_students:
            result = self.compute_student_result_for_exam(exam=exam, student_id=student.student_id, scores=scores)
            if result is None or result.total_achieved_points is None:
                messagebox.showerror(
                    "Superposition nicht moeglich",
                    f"Fuer {student.display_name} ist die Auswertung noch nicht vollstaendig - es fehlt "
                    "mindestens eine Punktbewertung im gesamten Exam (nicht nur im aktuellen Bereich). "
                    "Deshalb konnte keine Note ermittelt werden.",
                )
                return None
            if result.total_max_points <= 0:
                messagebox.showerror(
                    "Superposition nicht moeglich",
                    "Dieses Exam hat keine bewertbaren Aufgaben - es kann keine Note ermittelt werden.",
                )
                return None
            if result.grade_label is None:
                messagebox.showerror(
                    "Superposition nicht moeglich",
                    f"Fuer {student.display_name} liegt die erreichte Punktzahl unterhalb der niedrigsten "
                    "Schwelle des zugeordneten Notenschluessels - es kann keine Note ermittelt werden.",
                )
                return None
            content_by_student_id[student.student_id] = result.grade_label

        return self._apply_superposition_clones(
            exam=exam,
            region_id=region_id,
            page_number=page_number,
            target_students=target_students,
            content_by_student_id=content_by_student_id,
            annotation_type=annotation_type,
            color_hex=color_hex,
            font_size=font_size,
            x=x,
            y=y,
            description_prefix="Noten-Superposition",
        )

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
