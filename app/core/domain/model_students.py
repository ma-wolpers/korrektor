"""Domain models per student: the student's PDF, per-area completion, placed correction marks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class PersonAreaCompletion:
    """Finished-status for one person on one region.

    `region_id` references `RegionAssignment.region_id` — the region's
    stable technical identity, not its (renameable, potentially reused)
    `assigned_area_codes` display label. Raw JSON keyed by the legacy
    `area_code` field is migrated to `region_id` before this class ever
    parses it (see `app/infrastructure/repositories/legacy_migration.py`).
    """

    student_id: str
    region_id: str
    is_finished: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "student_id": self.student_id,
            "region_id": self.region_id,
            "is_finished": self.is_finished,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "PersonAreaCompletion":
        return cls(
            student_id=str(raw.get("student_id", "")).strip(),
            region_id=str(raw.get("region_id", "")).strip(),
            is_finished=bool(raw.get("is_finished", True)),
        )


@dataclass(slots=True)
class PdfAnnotation:
    """One placed correction mark/comment on a student's PDF page.

    `region_id` references `RegionAssignment.region_id` — the region's
    stable technical identity, used to resolve the annotation's clip box
    (see `MainWindow._resolve_annotation_clip_box`). It is not the
    (renameable, potentially reused) `assigned_area_codes` display label.
    `task_code` is a `TaskDefinition.code` and is unrelated to region
    identity; it is never rewritten by region relabeling.
    """

    annotation_id: str
    student_pdf: str
    page_number: int
    annotation_type: str
    content: str
    color_hex: str
    x: float
    y: float
    task_code: str = ""
    region_id: str = ""
    font_size: float = 20.0
    rotation_deg: float = 0.0
    sync_group_id: str = ""
    position_detached: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "annotation_id": self.annotation_id,
            "student_pdf": self.student_pdf,
            "page_number": self.page_number,
            "annotation_type": self.annotation_type,
            "content": self.content,
            "color_hex": self.color_hex,
            "x": self.x,
            "y": self.y,
            "task_code": self.task_code,
            "region_id": self.region_id,
            "font_size": self.font_size,
            "rotation_deg": self.rotation_deg,
            "sync_group_id": self.sync_group_id,
            "position_detached": self.position_detached,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "PdfAnnotation":
        return cls(
            annotation_id=str(raw.get("annotation_id", "")).strip(),
            student_pdf=str(raw.get("student_pdf", "")).strip(),
            page_number=int(raw.get("page_number", 1)),
            annotation_type=str(raw.get("annotation_type", "symbol")).strip().lower() or "symbol",
            content=str(raw.get("content", "")).strip(),
            color_hex=str(raw.get("color_hex", "#d62828")).strip() or "#d62828",
            x=float(raw.get("x", 0.0)),
            y=float(raw.get("y", 0.0)),
            task_code=str(raw.get("task_code", "")).strip().upper(),
            region_id=str(raw.get("region_id", "")).strip(),
            font_size=float(raw.get("font_size", 20.0)),
            rotation_deg=float(raw.get("rotation_deg", 0.0)),
            sync_group_id=str(raw.get("sync_group_id", "")).strip(),
            position_detached=bool(raw.get("position_detached", False)),
        )


@dataclass(slots=True)
class StudentExam:
    """One student's PDF in an exam.

    Legacy contract: the former ``extra_pages`` attribute no longer exists. Extra pages are
    always *computed* (`app.core.domain.page_coverage`: pages without a template region),
    so there is exactly one truth. ``from_dict`` ignores an old ``extra_pages`` key and
    ``to_dict`` no longer writes it - it disappears from a file on the next save.
    """

    student_id: str
    display_name: str
    pdf_filename: str
    page_count: int
    stats_report_appended: bool = False
    """Whether the Auswertungs-Statistikseite is currently appended as the last page of `pdf_filename`.

    Does **not** count towards `page_count` - that field bounds the exam's
    real Standardseiten (used for Bereichs-/Namenserfassungs-Navigation
    across the Reading/Naming/Region-Editor views), and an appended
    Statistikseite is not one. This flag alone is not treated as proof of
    the PDF's actual physical state - see
    `app/infrastructure/pdf/pdf_document_writer.py`'s marker mechanism,
    which the append/remove controller cross-checks this flag against
    before ever mutating the file.
    """

    def to_dict(self) -> dict[str, Any]:
        return {
            "student_id": self.student_id,
            "display_name": self.display_name,
            "pdf_filename": self.pdf_filename,
            "page_count": self.page_count,
            "stats_report_appended": self.stats_report_appended,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "StudentExam":
        return cls(
            student_id=str(raw.get("student_id", "")).strip(),
            display_name=str(raw.get("display_name", "")).strip(),
            pdf_filename=str(raw.get("pdf_filename", "")).strip(),
            page_count=int(raw.get("page_count", 0)),
            stats_report_appended=bool(raw.get("stats_report_appended", False)),
        )
