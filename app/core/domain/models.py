from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.domain.grading_scale import GradingScaleSnapshot
from app.core.domain.model_regions import (  # noqa: F401 - re-exported, stable import path
    ExtraPageAssignment,
    RegionAssignment,
    RegionBox,
    TaskCategory,
    TaskDefinition,
    UnscoredPage,
)
from app.core.domain.model_students import PdfAnnotation, PersonAreaCompletion, StudentExam  # noqa: F401


ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime(ISO_FORMAT)


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
    # Seiten ohne Bereich, bewusst "ohne Bewertung" markiert (Zuschnitt Schritt 2).
    unscored_pages: list[UnscoredPage] = field(default_factory=list)
    # Korrekturabschluss je Person+Bereich.
    person_area_completions: list[PersonAreaCompletion] = field(default_factory=list)
    # Freitextkommentare je Person+Aufgabe (student_id -> task_code -> comment).
    task_comments: dict[str, dict[str, str]] = field(default_factory=dict)
    # Persistente Korrekturmarkierungen fuer PDF-Overlay und PDF-Writeback.
    pdf_annotations: list[PdfAnnotation] = field(default_factory=list)
    is_reading_complete: bool = False
    # Namensfeld-Bereich (Namenmodus): eine gemeinsame Position fuer alle Schueler:innen-PDFs.
    name_region: RegionBox | None = None
    name_region_page: int = 1
    # Eingefrorene Kopie des bei Zuordnung effektiven Notenschluessels (Variante B,
    # siehe ARCHITEKTUR.md "Notenschluessel") - nie eine live grading_scale_id-Referenz,
    # damit spaetere Aenderungen an der globalen Vorlage diese Klausur nie rueckwirkend treffen.
    grading_scale_snapshot: GradingScaleSnapshot | None = None
    # Kategorien-Anzeigereihenfolge (Meilenstein 4); Zuordnung task_code -> category_id,
    # ein Task hoechstens einer Kategorie, "kein Eintrag" = unkategorisiert.
    task_categories: list[TaskCategory] = field(default_factory=list)
    task_category_assignments: dict[str, str] = field(default_factory=dict)
    # Optionale Klausur-Metadaten fuer den zentralen Exportmodus (Namensschema-Platzhalter
    # {Klasse}/{Fach}) - einmalig bei der Klausur-Anlage eingetragen, leer erlaubt.
    school_class: str = ""
    subject: str = ""

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
            "pdf_annotations": [annotation.to_dict() for annotation in self.pdf_annotations],
            "is_reading_complete": self.is_reading_complete,
            "name_region": self.name_region.to_dict() if self.name_region is not None else None,
            "name_region_page": self.name_region_page,
            "grading_scale_snapshot": (
                self.grading_scale_snapshot.to_dict() if self.grading_scale_snapshot is not None else None
            ),
            "task_categories": [category.to_dict() for category in self.task_categories],
            "task_category_assignments": dict(self.task_category_assignments),
            "unscored_pages": [page.to_dict() for page in self.unscored_pages],
            "school_class": self.school_class,
            "subject": self.subject,
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
        annotations = [PdfAnnotation.from_dict(item) for item in raw.get("pdf_annotations", [])]
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

        task_categories = [TaskCategory.from_dict(item) for item in raw.get("task_categories", [])]
        known_category_ids = {category.category_id for category in task_categories}
        raw_assignments = raw.get("task_category_assignments", {})
        task_category_assignments: dict[str, str] = {}
        if isinstance(raw_assignments, dict):
            for raw_task_code, raw_category_id in raw_assignments.items():
                task_code = str(raw_task_code).strip().upper()
                category_id = str(raw_category_id).strip()
                if task_code and category_id in known_category_ids:
                    task_category_assignments[task_code] = category_id

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
            unscored_pages=[UnscoredPage.from_dict(item) for item in raw.get("unscored_pages", [])],
            person_area_completions=completions,
            task_comments=task_comments,
            pdf_annotations=annotations,
            is_reading_complete=bool(raw.get("is_reading_complete", False)),
            name_region=RegionBox.from_dict(raw["name_region"]) if raw.get("name_region") else None,
            name_region_page=int(raw.get("name_region_page", 1)),
            grading_scale_snapshot=(
                GradingScaleSnapshot.from_dict(raw["grading_scale_snapshot"])
                if raw.get("grading_scale_snapshot")
                else None
            ),
            task_categories=task_categories,
            task_category_assignments=task_category_assignments,
            school_class=str(raw.get("school_class", "")).strip(),
            subject=str(raw.get("subject", "")).strip(),
        )

    @property
    def folder(self) -> Path:
        return Path(self.folder_path)
