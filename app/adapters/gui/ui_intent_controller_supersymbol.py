from __future__ import annotations

from uuid import uuid4

from app.core.domain.annotation_sync import build_annotation_clones
from app.core.domain.models import ExamProject, PdfAnnotation


class UiIntentControllerSupersymbolMixin:
    def apply_super_symbol_immediate(
        self,
        *,
        exam: ExamProject,
        region_id: str,
        page_number: int,
        matched_student_ids: list[str],
        annotation_type: str,
        content: str,
        color_hex: str,
        font_size: float,
        x: float,
        y: float,
    ) -> ExamProject | None:
        """Place one annotation per matched student at (x, y), as one undoable action.

        A single logical HistoryAction (whole-exam before/after snapshot,
        same convention as every other `_immediate` mutator) covers every
        annotation created here - it is a one-time bulk apply, not a live
        filter: later changes to the underlying points never retroactively
        move, remove, or recompute these annotations. Uses the same
        `build_annotation_clones` mechanism as "Durchdruecken"
        (`MainWindow._enable_selected_annotation_sync`), with the
        score-filtered student set as the clone target instead of the
        current correction student list.
        """
        if not matched_student_ids:
            return None

        before_payload = exam.to_dict()
        sync_group_id = f"sg-{uuid4().hex[:12]}"
        base = PdfAnnotation(
            annotation_id="",
            student_pdf="",
            page_number=page_number,
            annotation_type=annotation_type,
            content=content,
            color_hex=color_hex,
            x=x,
            y=y,
            task_code="",
            region_id=region_id,
            font_size=font_size,
            rotation_deg=0.0,
        )
        students_by_id = {student.student_id: student for student in exam.students}
        matched_students = [students_by_id[sid] for sid in matched_student_ids if sid in students_by_id]
        clones = build_annotation_clones(base, matched_students, sync_group_id)
        if not clones:
            return None
        exam.pdf_annotations.extend(clones)

        exam_file = self._save_exam_guarded(exam)
        if exam_file is None:
            return None
        updated = self._deps.exam_repository.load_exam(exam_file)
        self._record_exam_payload_action(
            description=f"Supersymbol gesetzt ({len(clones)} Personen)",
            exam_id=updated.exam_id,
            before_payload=before_payload,
            after_payload=updated.to_dict(),
        )
        self.refresh_exam_overview()
        self._app.set_status(f"Supersymbol fuer {len(clones)} Person(en) gesetzt")
        return updated
