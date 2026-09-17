import json
from pathlib import Path

import pytest

from app.core.domain.models import ExamProject, StudentExam, utc_now_iso
from app.core.domain.validation import ExamStructureError
from app.infrastructure.repositories.json_exam_repository import JsonExamRepository


def _build_exam(folder: Path) -> ExamProject:
    now = utc_now_iso()
    return ExamProject(
        exam_id="exam-1",
        exam_name="Mathe",
        folder_path=str(folder),
        created_at=now,
        updated_at=now,
        standard_page_count=2,
        students=[
            StudentExam(
                student_id="alice",
                display_name="Alice",
                pdf_filename="Alice.pdf",
                page_count=2,
            )
        ],
    )


def test_delete_exam_removes_saved_json(tmp_path: Path) -> None:
    index_root = tmp_path / "index"
    exam_folder = tmp_path / "exam"
    exam_folder.mkdir(parents=True)

    repo = JsonExamRepository(index_root=index_root)
    exam = _build_exam(exam_folder)

    exam_file = repo.save_exam(exam)
    assert exam_file.exists()

    repo.delete_exam(exam_file)

    assert not exam_file.exists()
    assert repo.list_exam_files() == []


def test_delete_exam_rejects_paths_outside_index_root(tmp_path: Path) -> None:
    repo = JsonExamRepository(index_root=tmp_path / "index")
    outside_file = tmp_path / "outside.json"
    outside_file.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError):
        repo.delete_exam(outside_file)


def test_set_index_root_switches_storage_location(tmp_path: Path) -> None:
    first_index = tmp_path / "index-a"
    second_index = tmp_path / "index-b"
    exam_folder = tmp_path / "exam"
    exam_folder.mkdir(parents=True)

    repo = JsonExamRepository(index_root=first_index)
    exam = _build_exam(exam_folder)

    first_file = repo.save_exam(exam)
    assert first_file.parent == first_index.resolve()

    repo.set_index_root(second_index)
    second_file = repo.save_exam(exam)

    assert second_file.parent == second_index.resolve()
    assert second_file.exists()


def test_load_exam_rejects_legacy_schema_without_extra_assignments(tmp_path: Path) -> None:
    index_root = tmp_path / "index"
    index_root.mkdir(parents=True)

    exam_file = index_root / "legacy.exam.json"
    exam_file.write_text(
        """
{
  "exam_id": "exam-legacy",
  "exam_name": "Mathe",
  "folder_path": "A:/tmp/exam",
  "created_at": "2025-01-01T00:00:00.000000Z",
  "updated_at": "2025-01-01T00:00:00.000000Z",
  "standard_page_count": 2,
  "students": [],
  "regions": [],
  "is_reading_complete": false
}
""".strip(),
        encoding="utf-8",
    )

    repo = JsonExamRepository(index_root=index_root)

    with pytest.raises(ValueError, match="legacy\\.exam\\.json"):
        repo.load_exam(exam_file)


def _base_two_region_raw_exam() -> dict[str, object]:
    """A minimal but schema-complete raw exam with two distinct regions."""
    return {
        "exam_id": "exam-two-regions",
        "exam_name": "Mathe",
        "folder_path": "A:/tmp/exam",
        "created_at": "2025-01-01T00:00:00.000000Z",
        "updated_at": "2025-01-01T00:00:00.000000Z",
        "standard_page_count": 2,
        "students": [
            {"student_id": "alice", "display_name": "Alice", "pdf_filename": "Alice.pdf", "page_count": 2}
        ],
        "regions": [
            {
                "region_id": "r-a",
                "student_pdf": "",
                "page_number": 1,
                "box": {"x0": 0, "y0": 0, "x1": 100, "y1": 100},
                "tasks": [{"code": "1a", "name": "1a", "max_points": 3.0}],
                "assigned_area_codes": ["A"],
                "is_read_complete": True,
                "is_corrected": False,
                "is_extra_page": False,
            },
            {
                "region_id": "r-b",
                "student_pdf": "",
                "page_number": 2,
                "box": {"x0": 0, "y0": 0, "x1": 100, "y1": 100},
                "tasks": [{"code": "2a", "name": "2a", "max_points": 2.0}],
                "assigned_area_codes": ["B"],
                "is_read_complete": True,
                "is_corrected": False,
                "is_extra_page": False,
            },
        ],
        "extra_page_assignments": [],
        "person_area_completions": [],
        "task_comments": {},
        "pdf_annotations": [],
        "is_reading_complete": False,
    }


def _write_raw_exam(index_root: Path, filename: str, raw: dict[str, object]) -> Path:
    index_root.mkdir(parents=True, exist_ok=True)
    exam_file = index_root / filename
    exam_file.write_text(json.dumps(raw), encoding="utf-8")
    return exam_file


def test_load_exam_rejects_duplicate_area_code_labels(tmp_path: Path) -> None:
    raw = _base_two_region_raw_exam()
    raw["regions"][1]["assigned_area_codes"] = ["A"]  # collides with region r-a's label

    index_root = tmp_path / "index"
    exam_file = _write_raw_exam(index_root, "duplicate_label.exam.json", raw)
    repo = JsonExamRepository(index_root=index_root)

    with pytest.raises(ExamStructureError, match="Bereichs-Label"):
        repo.load_exam(exam_file)


def test_load_exam_rejects_duplicate_task_codes_across_regions(tmp_path: Path) -> None:
    raw = _base_two_region_raw_exam()
    raw["regions"][1]["tasks"] = [{"code": "1a", "name": "1a", "max_points": 2.0}]  # collides with region r-a

    index_root = tmp_path / "index"
    exam_file = _write_raw_exam(index_root, "duplicate_task.exam.json", raw)
    repo = JsonExamRepository(index_root=index_root)

    with pytest.raises(ExamStructureError, match="Aufgaben-Code"):
        repo.load_exam(exam_file)


def test_load_exam_backfills_missing_region_id(tmp_path: Path) -> None:
    raw = _base_two_region_raw_exam()
    raw["regions"][0]["region_id"] = ""

    index_root = tmp_path / "index"
    exam_file = _write_raw_exam(index_root, "missing_region_id.exam.json", raw)
    repo = JsonExamRepository(index_root=index_root)

    exam = repo.load_exam(exam_file)

    assert exam.regions[0].region_id
    assert exam.regions[0].region_id != exam.regions[1].region_id


def test_load_exam_migrates_unambiguous_legacy_area_code_reference(tmp_path: Path) -> None:
    raw = _base_two_region_raw_exam()
    raw["person_area_completions"] = [{"student_id": "alice", "area_code": "A", "is_finished": True}]
    raw["pdf_annotations"] = [
        {
            "annotation_id": "ann-1",
            "student_pdf": "Alice.pdf",
            "page_number": 1,
            "annotation_type": "symbol",
            "content": "check",
            "color_hex": "#d62828",
            "x": 1.0,
            "y": 1.0,
            "area_code": "A",
        }
    ]

    index_root = tmp_path / "index"
    exam_file = _write_raw_exam(index_root, "legacy_reference.exam.json", raw)
    repo = JsonExamRepository(index_root=index_root)

    exam = repo.load_exam(exam_file)

    assert exam.person_area_completions[0].region_id == "r-a"
    assert exam.pdf_annotations[0].region_id == "r-a"


def test_load_exam_leaves_ambiguous_legacy_area_code_reference_unmigrated(tmp_path: Path) -> None:
    raw = _base_two_region_raw_exam()
    raw["regions"][1]["assigned_area_codes"] = ["A"]  # ambiguous: two regions now share label "A"
    raw["person_area_completions"] = [{"student_id": "alice", "area_code": "A", "is_finished": True}]

    index_root = tmp_path / "index"
    exam_file = _write_raw_exam(index_root, "ambiguous_reference.exam.json", raw)
    repo = JsonExamRepository(index_root=index_root)

    # The duplicate label itself is rejected by validate_regions - migrating
    # the ambiguous reference must not mask that with a guessed region_id.
    with pytest.raises(ExamStructureError, match="Bereichs-Label"):
        repo.load_exam(exam_file)
