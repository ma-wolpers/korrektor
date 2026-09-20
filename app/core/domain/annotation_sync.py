from __future__ import annotations

from typing import Sequence
from uuid import uuid4

from app.core.domain.models import PdfAnnotation, StudentExam


def normalize_rotation_deg(raw_deg: float) -> float:
    """Snap a rotation angle to the nearest 90-degree step, wrapped into [0, 360).

    PDF freetext annotation rotation (see the PDF-export code in
    `main_window_correction_markers_export.py`) is only reliably rendered at
    90-degree steps, so every write path that sets `PdfAnnotation.rotation_deg`
    normalizes through this one function - moved here from the GUI
    (`MainWindow._normalize_rotation_deg`, kept as a thin wrapper for its
    existing call sites) so the `UiIntentController` annotation-mutation
    methods (Meilenstein 0.3) can reuse the exact same rule without a
    GUI-layer dependency.
    """
    snapped = int(round(float(raw_deg) / 90.0)) * 90
    return float(snapped % 360)


def sync_group_members(
    annotations: Sequence[PdfAnnotation],
    sync_group_id: str,
    *,
    include_detached: bool,
) -> list[PdfAnnotation]:
    """Return every annotation in `annotations` sharing `sync_group_id`, in their original order.

    Pure lookup, factored out of the GUI (`MainWindow._sync_group_members`)
    so both the GUI (live rendering/info-label) and the
    `UiIntentController` annotation-mutation methods (Meilenstein 0.3 -
    resize/rotate/recolor/detach act on a whole sync group as one atomic
    action) share one definition of "what counts as a group member" instead
    of maintaining two copies. `include_detached=False` excludes members
    whose `position_detached` is set (Alt-Drag-entkoppelte Position - siehe
    `ARCHITEKTUR.md`), used by position-affecting operations; style
    attributes (Farbe/Groesse/Rotation) always pass `include_detached=True`
    since only the *Position*, not der Stil, lokal geloest werden kann.
    An empty/falsy `sync_group_id` returns an empty list - callers that mean
    "just this one annotation" handle that singleton case themselves.
    """
    if not sync_group_id:
        return []
    members = [item for item in annotations if item.sync_group_id == sync_group_id]
    if include_detached:
        return members
    return [item for item in members if not item.position_detached]


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


def build_scored_annotation_clones(
    base: PdfAnnotation,
    students: Sequence[StudentExam],
    content_by_student_id: dict[str, str],
    sync_group_id: str,
) -> list[PdfAnnotation]:
    """Like `build_annotation_clones`, but each clone's `content` is personalized per student.

    Backs the Punkte-/Noten-Superposition (Meilenstein 3): position and
    style (`x`/`y`/`color_hex`/`font_size`/`rotation_deg`) are shared from
    `base` exactly like a normal sync clone, but `content` comes from
    `content_by_student_id[student.student_id]` instead of `base.content` -
    each student sees their own points/grade at the same on-page spot.
    These clones still share one `sync_group_id` (so moving/resizing/
    rotating the group afterwards keeps working via the existing
    `sync_group_members` mechanism), but that mechanism only ever touches
    style attributes, never `content` - see
    `tests/test_annotation_sync.py` for the invariant this relies on.
    A student without a `content_by_student_id` entry is silently skipped
    (never given an empty/placeholder annotation) - callers must resolve
    every target student's content before calling this, and pass only
    resolved students here.
    """
    return [
        PdfAnnotation(
            annotation_id=f"ann-{uuid4().hex[:12]}",
            student_pdf=student.pdf_filename,
            page_number=base.page_number,
            annotation_type=base.annotation_type,
            content=content_by_student_id[student.student_id],
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
        if student.student_id in content_by_student_id
    ]
