"""Domain models: tasks, region templates, extra-page assignments, unscored pages, task categories."""

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
    region_id: str
    student_pdf: str
    page_number: int
    box: RegionBox
    tasks: list[TaskDefinition] = field(default_factory=list)
    assigned_area_codes: list[str] = field(default_factory=list)
    is_read_complete: bool = False
    is_corrected: bool = False
    is_extra_page: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "region_id": self.region_id,
            "student_pdf": self.student_pdf,
            "page_number": self.page_number,
            "box": self.box.to_dict(),
            "tasks": [task.to_dict() for task in self.tasks],
            "assigned_area_codes": list(self.assigned_area_codes),
            "is_read_complete": self.is_read_complete,
            "is_corrected": self.is_corrected,
            "is_extra_page": self.is_extra_page,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "RegionAssignment":
        return cls(
            region_id=str(raw.get("region_id", "")).strip(),
            student_pdf=str(raw.get("student_pdf", "")).strip(),
            page_number=int(raw.get("page_number", 1)),
            box=RegionBox.from_dict(raw.get("box", {})),
            tasks=[TaskDefinition.from_dict(item) for item in raw.get("tasks", [])],
            assigned_area_codes=[str(code).strip() for code in raw.get("assigned_area_codes", [])],
            is_read_complete=bool(raw.get("is_read_complete", False)),
            is_corrected=bool(raw.get("is_corrected", False)),
            is_extra_page=bool(raw.get("is_extra_page", False)),
        )


@dataclass(slots=True)
class ExtraPageAssignment:
    assignment_id: str
    student_pdf: str
    page_number: int
    box: RegionBox
    assigned_area_codes: list[str] = field(default_factory=list)
    is_read_complete: bool = True
    is_corrected: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "assignment_id": self.assignment_id,
            "student_pdf": self.student_pdf,
            "page_number": self.page_number,
            "box": self.box.to_dict(),
            "assigned_area_codes": list(self.assigned_area_codes),
            "is_read_complete": self.is_read_complete,
            "is_corrected": self.is_corrected,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ExtraPageAssignment":
        return cls(
            assignment_id=str(raw.get("assignment_id", raw.get("region_id", ""))).strip(),
            student_pdf=str(raw.get("student_pdf", "")).strip(),
            page_number=int(raw.get("page_number", 1)),
            box=RegionBox.from_dict(raw.get("box", {})),
            assigned_area_codes=[str(code).strip() for code in raw.get("assigned_area_codes", [])],
            is_read_complete=bool(raw.get("is_read_complete", True)),
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
    the page-numbering convention). Such a page has no template region and
    no extra-page assignment and is therefore not an open page.
    """

    student_pdf: str
    page_number: int

    def to_dict(self) -> dict[str, Any]:
        return {"student_pdf": self.student_pdf, "page_number": self.page_number}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "UnscoredPage":
        return cls(student_pdf=str(raw.get("student_pdf", "")).strip(), page_number=int(raw.get("page_number", 1)))
