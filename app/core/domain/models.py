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
class PersonAreaCompletion:
    student_id: str
    area_code: str
    is_finished: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "student_id": self.student_id,
            "area_code": self.area_code,
            "is_finished": self.is_finished,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "PersonAreaCompletion":
        return cls(
            student_id=str(raw.get("student_id", "")).strip(),
            area_code=str(raw.get("area_code", "")).strip().upper(),
            is_finished=bool(raw.get("is_finished", True)),
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
    # Standardbereich-Templates (seiten-/koordinatenbasiert, nicht studentgebunden).
    regions: list[RegionAssignment] = field(default_factory=list)
    # Extraseiten-Zuordnungen bleiben student- und seitenbezogen.
    extra_page_assignments: list[ExtraPageAssignment] = field(default_factory=list)
    # Korrekturabschluss je Person+Bereich.
    person_area_completions: list[PersonAreaCompletion] = field(default_factory=list)
    # Freitextkommentare je Person+Aufgabe (student_id -> task_code -> comment).
    task_comments: dict[str, dict[str, str]] = field(default_factory=dict)
    is_reading_complete: bool = False

    def to_dict(self) -> dict[str, Any]:
        normalized_task_comments: dict[str, dict[str, str]] = {}
        for student_id, comments in self.task_comments.items():
            normalized_student = student_id.strip()
            if not normalized_student:
                continue
            normalized_comments = {
                task_code.strip().upper(): str(comment).strip()
                for task_code, comment in comments.items()
                if task_code.strip() and str(comment).strip()
            }
            if normalized_comments:
                normalized_task_comments[normalized_student] = normalized_comments

        return {
            "exam_id": self.exam_id,
            "exam_name": self.exam_name,
            "folder_path": self.folder_path,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "standard_page_count": self.standard_page_count,
            "students": [student.to_dict() for student in self.students],
            "regions": [region.to_dict() for region in self.regions],
            "extra_page_assignments": [assignment.to_dict() for assignment in self.extra_page_assignments],
            "person_area_completions": [item.to_dict() for item in self.person_area_completions],
            "task_comments": normalized_task_comments,
            "is_reading_complete": self.is_reading_complete,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ExamProject":
        if "extra_page_assignments" not in raw:
            raise ValueError("Unsupported exam schema: missing 'extra_page_assignments'")

        standard_templates = [RegionAssignment.from_dict(item) for item in raw.get("regions", [])]
        for region in standard_templates:
            if region.is_extra_page:
                raise ValueError("Unsupported exam schema: standard templates must not set is_extra_page=true")
            if region.student_pdf:
                raise ValueError("Unsupported exam schema: standard templates must not carry student_pdf")

        extra_assignments = [ExtraPageAssignment.from_dict(item) for item in raw.get("extra_page_assignments", [])]
        completions = [PersonAreaCompletion.from_dict(item) for item in raw.get("person_area_completions", [])]
        task_comments_raw = raw.get("task_comments", {})
        task_comments: dict[str, dict[str, str]] = {}
        if isinstance(task_comments_raw, dict):
            for raw_student_id, raw_comments in task_comments_raw.items():
                student_id = str(raw_student_id).strip()
                if not student_id or not isinstance(raw_comments, dict):
                    continue
                normalized_comments: dict[str, str] = {}
                for raw_task_code, raw_comment in raw_comments.items():
                    task_code = str(raw_task_code).strip().upper()
                    comment = str(raw_comment).strip()
                    if not task_code or not comment:
                        continue
                    normalized_comments[task_code] = comment
                if normalized_comments:
                    task_comments[student_id] = normalized_comments

        return cls(
            exam_id=str(raw.get("exam_id", "")).strip(),
            exam_name=str(raw.get("exam_name", "")).strip(),
            folder_path=str(raw.get("folder_path", "")).strip(),
            created_at=str(raw.get("created_at", utc_now_iso())),
            updated_at=str(raw.get("updated_at", utc_now_iso())),
            standard_page_count=int(raw.get("standard_page_count", 0)),
            students=[StudentExam.from_dict(item) for item in raw.get("students", [])],
            regions=standard_templates,
            extra_page_assignments=extra_assignments,
            person_area_completions=completions,
            task_comments=task_comments,
            is_reading_complete=bool(raw.get("is_reading_complete", False)),
        )

    @property
    def folder(self) -> Path:
        return Path(self.folder_path)
