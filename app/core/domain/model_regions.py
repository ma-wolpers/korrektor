"""Domain models: tasks, regions (Superseiten/Einzelseiten), unscored pages, task categories."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class TaskDefinition:
    code: str
    name: str
    max_points: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "max_points": self.max_points,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "TaskDefinition":
        return cls(
            code=str(raw.get("code", "")).strip(),
            name=str(raw.get("name", "")).strip(),
            max_points=float(raw.get("max_points", 0.0)),
        )


@dataclass(slots=True)
class RegionBox:
    x0: float
    y0: float
    x1: float
    y1: float

    def to_dict(self) -> dict[str, float]:
        return {
            "x0": self.x0,
            "y0": self.y0,
            "x1": self.x1,
            "y1": self.y1,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "RegionBox":
        return cls(
            x0=float(raw.get("x0", 0.0)),
            y0=float(raw.get("y0", 0.0)),
            x1=float(raw.get("x1", 0.0)),
            y1=float(raw.get("y1", 0.0)),
        )


@dataclass(slots=True)
class RegionAssignment:
    """A marked area ("Bereich") that holds one or more tasks (schema v2).

    ``student_pdf == ""``: **Superseiten-Bereich** - the same box on page
    ``page_number`` of every student (Zuschnitt Schritt 1). ``student_pdf``
    set: **Einzelseiten-Bereich** - only on that student's PDF (Zuschnitt
    Schritt 2). ``task_codes`` reference `ExamProject.tasks` (canonical upper
    case); a task may be referenced by any number of regions, which is how a
    task spans a page break or continues on an extra sheet. ``box`` is in
    PyMuPDF page points of the rendered (visible) page, origin top left.
    ``assigned_area_codes[0]`` is the automatic, exam-wide unique display
    label (A, B, ...), never used as an identity - ``region_id`` is.
    """

    region_id: str
    student_pdf: str
    page_number: int
    box: RegionBox
    task_codes: list[str] = field(default_factory=list)
    assigned_area_codes: list[str] = field(default_factory=list)
    is_read_complete: bool = False
    is_corrected: bool = False

    @property
    def is_single_page(self) -> bool:
        """True for an Einzelseiten-Bereich (bound to one student's PDF)."""
        return bool(self.student_pdf)

    def to_dict(self) -> dict[str, Any]:
        """Schema-v2 dict (``task_codes`` instead of the v1 ``tasks``; no ``is_extra_page``)."""
        return {
            "region_id": self.region_id,
            "student_pdf": self.student_pdf,
            "page_number": self.page_number,
            "box": self.box.to_dict(),
            "task_codes": list(self.task_codes),
            "assigned_area_codes": list(self.assigned_area_codes),
            "is_read_complete": self.is_read_complete,
            "is_corrected": self.is_corrected,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "RegionAssignment":
        """Parse a schema-v2 region; codes are canonicalised to upper case."""
        return cls(
            region_id=str(raw.get("region_id", "")).strip(),
            student_pdf=str(raw.get("student_pdf", "")).strip(),
            page_number=int(raw.get("page_number", 1)),
            box=RegionBox.from_dict(raw.get("box", {})),
            task_codes=[str(code).strip().upper() for code in raw.get("task_codes", []) if str(code).strip()],
            assigned_area_codes=[str(code).strip() for code in raw.get("assigned_area_codes", [])],
            is_read_complete=bool(raw.get("is_read_complete", False)),
            is_corrected=bool(raw.get("is_corrected", False)),
        )


@dataclass(slots=True)
class TaskCategory:
    """A teacher-defined grouping of tasks for the Auswertung (Meilenstein 4 der Korrektor-Wunschliste).

    `category_id` is the stable technical identity (same pattern as
    `RegionAssignment.region_id`): renaming only changes `name`, never
    `category_id`, so `ExamProject.task_category_assignments` (keyed by
    `task_code`, valued by `category_id`) stays valid across renames.
    Order in `ExamProject.task_categories` is the display order (Ergebnis-
    seite/Diagramm-Legende) - a category with no tasks assigned to it is a
    normal, valid state (created before assigning anything to it yet).
    """

    category_id: str
    name: str

    def to_dict(self) -> dict[str, Any]:
        return {"category_id": self.category_id, "name": self.name}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "TaskCategory":
        return cls(
            category_id=str(raw.get("category_id", "")).strip(),
            name=str(raw.get("name", "")).strip(),
        )


@dataclass(slots=True, frozen=True)
class UnscoredPage:
    """A page of one student's PDF that is deliberately not scored ("ohne Bewertung", Zuschnitt Schritt 2).

    ``page_number`` is 1-based within ``student_pdf`` (the per-PDF level of
    the page-numbering convention). Such a page has no Superseiten-Bereich
    on its page number and no Einzelseiten-Bereich, and is therefore not an
    open page.
    """

    student_pdf: str
    page_number: int

    def to_dict(self) -> dict[str, Any]:
        return {"student_pdf": self.student_pdf, "page_number": self.page_number}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "UnscoredPage":
        return cls(student_pdf=str(raw.get("student_pdf", "")).strip(), page_number=int(raw.get("page_number", 1)))
