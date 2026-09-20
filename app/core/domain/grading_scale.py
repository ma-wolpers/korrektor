from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SCALE_TYPE_POINTS_1_15 = "punktnoten_1_15"
SCALE_TYPE_SCHOOL_1_6 = "schulnoten_1_6"

STATUS_ACTIVE = "active"
STATUS_ARCHIVED = "archived"


@dataclass(slots=True)
class GradeThreshold:
    """One grade boundary: `grade_label` applies once `percentage >= min_percent`.

    `min_percent` is a percentage of the maximum achievable points (0-100),
    never a raw point value - see `resolve_grade` in `grading.py` for why
    the scale is percentage-based rather than points-based (comparability
    across Bereiche/Klausuren with different `max_points`).
    """

    min_percent: float
    grade_label: str

    def to_dict(self) -> dict[str, Any]:
        return {"min_percent": self.min_percent, "grade_label": self.grade_label}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "GradeThreshold":
        return cls(
            min_percent=float(raw.get("min_percent", 0.0)),
            grade_label=str(raw.get("grade_label", "")).strip(),
        )


@dataclass(slots=True)
class GradingScale:
    """A reusable, globally stored grading-scale template.

    Lives independently of any exam (`json_grading_scale_repository.py`,
    global `%APPDATA%` store) - assigning it to an exam takes a
    `GradingScaleSnapshot` copy (see below) instead of a live reference, so
    editing or archiving this template afterwards never changes an already
    graded exam's result. `status` distinguishes templates that have never
    been used (freely deletable) from ones with at least one recorded usage
    (`grading_scale_usage.json` - archivable only, never hard-deleted, so a
    past usage's origin stays traceable). This class itself does not know
    which exams used it; that is the usage registry's job, kept separate so
    this template can be edited/archived without touching exam data.
    """

    scale_id: str
    name: str
    subject: str
    year: str
    school: str
    scale_type: str
    thresholds: list[GradeThreshold] = field(default_factory=list)
    status: str = STATUS_ACTIVE

    def to_dict(self) -> dict[str, Any]:
        return {
            "scale_id": self.scale_id,
            "name": self.name,
            "subject": self.subject,
            "year": self.year,
            "school": self.school,
            "scale_type": self.scale_type,
            "thresholds": [threshold.to_dict() for threshold in self.thresholds],
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "GradingScale":
        return cls(
            scale_id=str(raw.get("scale_id", "")).strip(),
            name=str(raw.get("name", "")).strip(),
            subject=str(raw.get("subject", "")).strip(),
            year=str(raw.get("year", "")).strip(),
            school=str(raw.get("school", "")).strip(),
            scale_type=str(raw.get("scale_type", "")).strip(),
            thresholds=[GradeThreshold.from_dict(item) for item in raw.get("thresholds", [])],
            status=str(raw.get("status", STATUS_ACTIVE)).strip() or STATUS_ACTIVE,
        )

    def to_snapshot(self, *, assigned_at: str) -> "GradingScaleSnapshot":
        """Freeze this template's current, effective grading data into an exam-embeddable snapshot.

        `source_scale_id` is kept purely for traceability (Verwaltungs-UI
        "wo verwendet") - `resolve_grade` never reads the global template
        back through it, only the snapshot's own copied fields.
        """
        return GradingScaleSnapshot(
            source_scale_id=self.scale_id,
            name=self.name,
            subject=self.subject,
            year=self.year,
            school=self.school,
            scale_type=self.scale_type,
            thresholds=[GradeThreshold(min_percent=t.min_percent, grade_label=t.grade_label) for t in self.thresholds],
            assigned_at=assigned_at,
        )


@dataclass(slots=True)
class GradingScaleUsageEntry:
    """One append-only record: "this global scale was assigned to this exam, at this time."

    Written whenever a `GradingScale` is assigned to an exam (creating a
    `GradingScaleSnapshot` on that exam) and never mutated or removed
    afterwards - not even when the exam itself is later deleted, since this
    entry already holds its own frozen `exam_name`/`exam_folder_path`
    copies rather than a live reference. Purely a usage log for the
    Notenschluessel-Verwaltung's "wo verwendet"-Uebersicht and for deciding
    whether a template may still be hard-deleted (`GradingScale.status`) -
    grading itself never reads this, only `GradingScaleSnapshot`.
    """

    source_scale_id: str
    exam_id: str
    exam_name: str
    exam_folder_path: str
    assigned_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_scale_id": self.source_scale_id,
            "exam_id": self.exam_id,
            "exam_name": self.exam_name,
            "exam_folder_path": self.exam_folder_path,
            "assigned_at": self.assigned_at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "GradingScaleUsageEntry":
        return cls(
            source_scale_id=str(raw.get("source_scale_id", "")).strip(),
            exam_id=str(raw.get("exam_id", "")).strip(),
            exam_name=str(raw.get("exam_name", "")).strip(),
            exam_folder_path=str(raw.get("exam_folder_path", "")).strip(),
            assigned_at=str(raw.get("assigned_at", "")).strip(),
        )


@dataclass(slots=True)
class GradingScaleSnapshot:
    """The effective grading scale actually used by one exam, frozen at assignment time.

    Copied field-for-field from a `GradingScale` via `to_snapshot()` -
    deliberately not a reference (no `scale_id` lookup at grading time), so
    later edits/archiving of the global template can never retroactively
    change an exam's already-computed grades. `source_scale_id` documents
    where it came from without being load-bearing for grading itself.
    """

    source_scale_id: str
    name: str
    subject: str
    year: str
    school: str
    scale_type: str
    thresholds: list[GradeThreshold] = field(default_factory=list)
    assigned_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_scale_id": self.source_scale_id,
            "name": self.name,
            "subject": self.subject,
            "year": self.year,
            "school": self.school,
            "scale_type": self.scale_type,
            "thresholds": [threshold.to_dict() for threshold in self.thresholds],
            "assigned_at": self.assigned_at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "GradingScaleSnapshot":
        return cls(
            source_scale_id=str(raw.get("source_scale_id", "")).strip(),
            name=str(raw.get("name", "")).strip(),
            subject=str(raw.get("subject", "")).strip(),
            year=str(raw.get("year", "")).strip(),
            school=str(raw.get("school", "")).strip(),
            scale_type=str(raw.get("scale_type", "")).strip(),
            thresholds=[GradeThreshold.from_dict(item) for item in raw.get("thresholds", [])],
            assigned_at=str(raw.get("assigned_at", "")).strip(),
        )
