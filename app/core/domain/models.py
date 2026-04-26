from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime(ISO_FORMAT)


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
class StudentExam:
    student_id: str
    display_name: str
    pdf_filename: str
    page_count: int
    extra_pages: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "student_id": self.student_id,
            "display_name": self.display_name,
            "pdf_filename": self.pdf_filename,
            "page_count": self.page_count,
            "extra_pages": list(self.extra_pages),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "StudentExam":
        return cls(
            student_id=str(raw.get("student_id", "")).strip(),
            display_name=str(raw.get("display_name", "")).strip(),
            pdf_filename=str(raw.get("pdf_filename", "")).strip(),
            page_count=int(raw.get("page_count", 0)),
            extra_pages=[int(page) for page in raw.get("extra_pages", [])],
        )


@dataclass(slots=True)
class ExamProject:
    exam_id: str
    exam_name: str
    folder_path: str
    created_at: str
    updated_at: str
    standard_page_count: int
    students: list[StudentExam] = field(default_factory=list)
    regions: list[RegionAssignment] = field(default_factory=list)
    is_reading_complete: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "exam_id": self.exam_id,
            "exam_name": self.exam_name,
            "folder_path": self.folder_path,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "standard_page_count": self.standard_page_count,
            "students": [student.to_dict() for student in self.students],
            "regions": [region.to_dict() for region in self.regions],
            "is_reading_complete": self.is_reading_complete,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ExamProject":
        return cls(
            exam_id=str(raw.get("exam_id", "")).strip(),
            exam_name=str(raw.get("exam_name", "")).strip(),
            folder_path=str(raw.get("folder_path", "")).strip(),
            created_at=str(raw.get("created_at", utc_now_iso())),
            updated_at=str(raw.get("updated_at", utc_now_iso())),
            standard_page_count=int(raw.get("standard_page_count", 0)),
            students=[StudentExam.from_dict(item) for item in raw.get("students", [])],
            regions=[RegionAssignment.from_dict(item) for item in raw.get("regions", [])],
            is_reading_complete=bool(raw.get("is_reading_complete", False)),
        )

    @property
    def folder(self) -> Path:
        return Path(self.folder_path)
