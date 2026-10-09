import copy

import pytest

from app.core.domain.models import ExamProject
from app.core.domain.schema_migration import migrate_v1_tasks
from app.core.domain.task_regions import superseiten_page_violations


def _base_raw_exam() -> dict[str, object]:
    return {
        "exam_id": "exam-1",
        "exam_name": "Mathe",
        "folder_path": "A:/tmp/exam",
        "created_at": "2025-01-01T00:00:00.000000Z",
        "updated_at": "2025-01-01T00:00:00.000000Z",
        "standard_page_count": 2,
        "students": [
            {
                "student_id": "alice",
                "display_name": "Alice",
                "pdf_filename": "Alice.pdf",
                "page_count": 3,
                "extra_pages": [3],
            }
        ],
        "regions": [
            {
                "region_id": "tpl-1",
                "student_pdf": "",
                "page_number": 1,
                "box": {"x0": 10, "y0": 20, "x1": 120, "y1": 180},
                "tasks": [
                    {"code": "A1", "name": "Aufgabe 1", "max_points": 4.0},
                ],
                "assigned_area_codes": ["A"],
                "is_read_complete": True,
                "is_corrected": False,
                "is_extra_page": False,
            }
        ],
        "extra_page_assignments": [
            {
                "assignment_id": "ex-1",
                "student_pdf": "Alice.pdf",
                "page_number": 3,
                "box": {"x0": 5, "y0": 5, "x1": 100, "y1": 100},
                "assigned_area_codes": ["A"],
                "is_read_complete": True,
                "is_corrected": False,
            }
        ],
        "person_area_completions": [
            {
                "student_id": "alice",
                "region_id": "tpl-1",
                "is_finished": True,
            }
        ],
        "task_comments": {
            "alice": {
                "A1": "Sauber gerechnet.",
            }
        },
        "pdf_annotations": [
            {
                "annotation_id": "ann-1",
                "student_pdf": "Alice.pdf",
                "page_number": 1,
                "annotation_type": "symbol",
                "content": "✓",
                "color_hex": "#d62828",
                "x": 33.5,
                "y": 72.25,
                "task_code": "A1",
                "region_id": "tpl-1",
                "font_size": 26.0,
                "rotation_deg": 15.0,
                "sync_group_id": "sg-demo",
                "position_detached": True,
            }
        ],
        "is_reading_complete": False,
    }


def _v2(raw):
    """Schema v1 fixture -> migrated -> parsed (the repository's load pipeline without the file)."""
    return ExamProject.from_dict(migrate_v1_tasks(raw))


def test_v1_migrates_into_exam_wide_tasks_regions_and_task_completions() -> None:
    exam = _v2(_base_raw_exam())

    assert [(r.region_id, r.student_pdf, r.page_number, r.task_codes) for r in exam.regions] == [
        ("tpl-1", "", 1, ["A1"]),
        ("ex-1", "Alice.pdf", 3, ["A1"]),  # extra-page assignment -> Einzelseiten-Bereich, same id
    ]
    assert exam.regions[1].assigned_area_codes == ["B"]
    assert [(t.code, t.max_points) for t in exam.tasks] == [("A1", 4.0)]
    assert [(c.student_id, c.task_code, c.is_finished) for c in exam.person_task_completions] == [("alice", "A1", True)]
    assert exam.task_comments == {"alice": {"A1": "Sauber gerechnet."}}
    assert len(exam.pdf_annotations) == 1
    assert exam.pdf_annotations[0].region_id == "tpl-1"
    assert exam.pdf_annotations[0].font_size == 26.0
    assert exam.pdf_annotations[0].rotation_deg == 15.0
    assert exam.pdf_annotations[0].sync_group_id == "sg-demo"
    assert exam.pdf_annotations[0].position_detached is True


def test_migration_is_idempotent_and_detects_v2() -> None:
    once = migrate_v1_tasks(_base_raw_exam())
    snapshot = copy.deepcopy(once)

    assert migrate_v1_tasks(once) == snapshot
    assert ExamProject.from_dict(snapshot).to_dict()["schema_version"] == 2
    assert migrate_v1_tasks(_v2(_base_raw_exam()).to_dict()) == _v2(_base_raw_exam()).to_dict()


def test_migration_canonicalises_codes_before_comparing() -> None:
    raw = _base_raw_exam()
    raw["regions"][0]["tasks"] = [{"code": " a1 ", "name": "a1", "max_points": 4.0}, {"code": "A1", "name": "A1", "max_points": 9.0}]

    exam = _v2(raw)

    assert [(t.code, t.max_points) for t in exam.tasks] == [("A1", 4.0)]  # first definition wins
    assert exam.regions[0].task_codes == ["A1"]


def test_migration_drops_extra_assignment_without_resolvable_tasks() -> None:
    raw = _base_raw_exam()
    raw["extra_page_assignments"][0]["assigned_area_codes"] = ["Z"]

    assert [region.region_id for region in _v2(raw).regions] == ["tpl-1"]


def test_migration_resolves_marks_without_region_by_position() -> None:
    raw = _base_raw_exam()
    raw["pdf_annotations"][0].pop("region_id")

    assert _v2(raw).pdf_annotations[0].region_id == "tpl-1"
    raw = _base_raw_exam()
    raw["pdf_annotations"][0].pop("region_id")
    raw["pdf_annotations"][0]["x"] = 500.0  # outside every region: stays unresolved
    assert _v2(raw).pdf_annotations[0].region_id == ""


def test_migration_keeps_superseiten_region_beyond_the_shortest_pdf_and_reports_it() -> None:
    """Rule A4 for legacy data: not fatal on load, but reported."""
    raw = _base_raw_exam()
    raw["students"].append({"student_id": "bob", "display_name": "Bob", "pdf_filename": "Bob.pdf", "page_count": 1})
    raw["regions"][0]["page_number"] = 2

    exam = _v2(raw)

    assert exam.regions[0].page_number == 2
    assert superseiten_page_violations(exam) == ["Bereich A liegt auf Seite 2, die Bob nicht hat"]


def test_from_dict_defaults_task_comments_when_missing() -> None:
    raw = _base_raw_exam()
    raw.pop("task_comments")

    assert _v2(raw).task_comments == {}


def test_from_dict_defaults_pdf_annotations_when_missing() -> None:
    raw = _base_raw_exam()
    raw.pop("pdf_annotations")

    assert _v2(raw).pdf_annotations == []


def test_from_dict_defaults_annotation_size_and_rotation_when_missing() -> None:
    raw = _base_raw_exam()
    raw["pdf_annotations"][0].pop("font_size")
    raw["pdf_annotations"][0].pop("rotation_deg")

    exam = _v2(raw)

    assert exam.pdf_annotations[0].font_size == 20.0
    assert exam.pdf_annotations[0].rotation_deg == 0.0


def test_from_dict_defaults_annotation_sync_fields_when_missing() -> None:
    raw = _base_raw_exam()
    raw["pdf_annotations"][0].pop("sync_group_id")
    raw["pdf_annotations"][0].pop("position_detached")

    exam = _v2(raw)

    assert exam.pdf_annotations[0].sync_group_id == ""
    assert exam.pdf_annotations[0].position_detached is False


def test_from_dict_rejects_unmigrated_v1_data() -> None:
    with pytest.raises(ValueError, match="schema_version"):
        ExamProject.from_dict(_base_raw_exam())


def test_saved_v2_has_no_extra_page_assignments_so_old_versions_reject_it() -> None:
    payload = _v2(_base_raw_exam()).to_dict()

    assert "extra_page_assignments" not in payload and "person_area_completions" not in payload
    assert all("tasks" not in region for region in payload["regions"])
