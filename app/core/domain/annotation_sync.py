from __future__ import annotations

from typing import Sequence
from uuid import uuid4

from app.core.domain.models import PdfAnnotation, StudentExam


def build_annotation_clones(
    base: PdfAnnotation,
    students: Sequence[StudentExam],
    sync_group_id: str,
) -> list[PdfAnnotation]:
    """Clone `base` for each given student's PDF, sharing one sync_group_id.

    The single shared mechanism behind bulk annotation placement: "Durchdruecken"
    (`MainWindow._enable_selected_annotation_sync`, clones onto every other
    correction student) and the Supersymbol bulk apply
    (`UiIntentController.apply_super_symbol_immediate`, clones onto a
    score-filtered subset) both call this with a different `students`
    sequence - the function itself never decides *which* students, only how
    to clone. Pure: it neither mutates `base` nor appends anywhere; callers
    own persistence and undo/redo.
    """
    return [
        PdfAnnotation(
            annotation_id=f"ann-{uuid4().hex[:12]}",
            student_pdf=student.pdf_filename,
            page_number=base.page_number,
            annotation_type=base.annotation_type,
            content=base.content,
            color_hex=base.color_hex,
            x=base.x,
            y=base.y,
            task_code=base.task_code,
            region_id=base.region_id,
            font_size=base.font_size,
            rotation_deg=base.rotation_deg,
            sync_group_id=sync_group_id,
            position_detached=False,
        )
        for student in students
    ]
