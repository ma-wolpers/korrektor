import json
import shutil
from pathlib import Path

import pytest

from app.core.domain.models import ExamProject, StudentExam, utc_now_iso
from app.core.domain.validation import ExamConflictError, ExamStructureError
from app.infrastructure.repositories import json_exam_repository as repo_module
from app.infrastructure.repositories.json_exam_repository import (
    EXAM_DATA_FILENAME,
    ExamFolderMissingError,
    JsonExamRepository,
)


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


def test_save_exam_writes_into_the_exam_folder_and_registers_it(tmp_path: Path) -> None:
    exam_folder = tmp_path / "exam"
    exam_folder.mkdir()
    repo = JsonExamRepository(index_root=tmp_path / "index")

    exam_file = repo.save_exam(_build_exam(exam_folder))

    assert exam_file == (exam_folder / EXAM_DATA_FILENAME).resolve()
    assert repo.list_exam_files() == [exam_file]
    assert repo.exam_file_for_id("exam-1") == exam_file
    assert list((tmp_path / "index").glob("*.json")) == [repo.registry.file]


def test_folder_path_is_derived_from_the_file_location_after_moving_the_folder(tmp_path: Path) -> None:
    """Portability: copying/moving the folder carries everything; the stored path is never trusted."""
    exam_folder = tmp_path / "pc1" / "exam"
    exam_folder.mkdir(parents=True)
    repo = JsonExamRepository(index_root=tmp_path / "index")
    repo.save_exam(_build_exam(exam_folder))

    moved = tmp_path / "pc2" / "Mathe 10a"
    shutil.copytree(exam_folder, moved)
    exam = repo.load_exam(moved / EXAM_DATA_FILENAME)

    assert Path(exam.folder_path) == moved.resolve()
    repo.save_exam(exam)
    on_disk = json.loads((moved / EXAM_DATA_FILENAME).read_text(encoding="utf-8"))
    assert Path(on_disk["folder_path"]) == moved.resolve()


def test_failed_write_keeps_previous_file_byte_identical(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    exam_folder = tmp_path / "exam"
    exam_folder.mkdir()
    repo = JsonExamRepository(index_root=tmp_path / "index")
    exam = _build_exam(exam_folder)
    exam_file = repo.save_exam(exam)
    before = exam_file.read_bytes()
    updated_at = exam.updated_at

    def _broken_write(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(repo_module, "atomic_write_json", _broken_write)
    exam.exam_name = "Mathe (nicht gespeichert)"
    with pytest.raises(OSError):
        repo.save_exam(exam)

    assert exam_file.read_bytes() == before
    assert exam.updated_at == updated_at  # a retry is not blocked by the conflict check


def test_missing_folder_is_a_value_error_for_the_overview(tmp_path: Path) -> None:
    exam_folder = tmp_path / "exam"
    exam_folder.mkdir()
    repo = JsonExamRepository(index_root=tmp_path / "index")
    exam_file = repo.save_exam(_build_exam(exam_folder))
    shutil.rmtree(exam_folder)

    with pytest.raises(ExamFolderMissingError, match="nicht gefunden"):
        repo.load_exam(exam_file)


def test_delete_exam_removes_folder_file_and_registry_entry_but_keeps_pdfs(tmp_path: Path) -> None:
    exam_folder = tmp_path / "exam"
    exam_folder.mkdir()
    (exam_folder / "Alice.pdf").write_bytes(b"%PDF")
    repo = JsonExamRepository(index_root=tmp_path / "index")
    exam_file = repo.save_exam(_build_exam(exam_folder))

    repo.delete_exam(exam_file)

    assert not exam_file.exists()
    assert repo.list_exam_files() == []
    assert (exam_folder / "Alice.pdf").exists()


def test_delete_exam_rejects_files_that_are_no_exam_data_file(tmp_path: Path) -> None:
    repo = JsonExamRepository(index_root=tmp_path / "index")
    other = tmp_path / "other.json"
    other.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError):
        repo.delete_exam(other)


def test_write_exam_payload_restores_and_re_registers(tmp_path: Path) -> None:
    exam_folder = tmp_path / "exam"
    exam_folder.mkdir()
    repo = JsonExamRepository(index_root=tmp_path / "index")
    exam_file = repo.save_exam(_build_exam(exam_folder))
    payload = json.loads(exam_file.read_text(encoding="utf-8"))
    repo.delete_exam(exam_file)

    repo.write_exam_payload(exam_file, payload)

    assert repo.list_exam_files() == [exam_file]
    assert repo.load_exam(exam_file).exam_name == "Mathe"


def test_set_index_root_switches_the_registry_but_not_the_data(tmp_path: Path) -> None:
    exam_folder = tmp_path / "exam"
    exam_folder.mkdir()
    repo = JsonExamRepository(index_root=tmp_path / "index-a")
    exam_file = repo.save_exam(_build_exam(exam_folder))

    repo.set_index_root(tmp_path / "index-b")

    assert repo.list_exam_files() == []
    assert exam_file.exists()


def test_save_exam_rejects_stale_write_after_concurrent_change(tmp_path: Path) -> None:
    """Two in-memory copies of the same exam (e.g. two PCs sharing the synced exam folder)
    must not silently clobber each other's save."""
    exam_folder = tmp_path / "exam"
    exam_folder.mkdir()
    repo = JsonExamRepository(index_root=tmp_path / "index")
    exam_file = repo.save_exam(_build_exam(exam_folder))

    stale_copy = repo.load_exam(exam_file)
    fresh_copy = repo.load_exam(exam_file)

    fresh_copy.exam_name = "Mathe (bearbeitet auf PC 2)"
    repo.save_exam(fresh_copy)

    stale_copy.exam_name = "Mathe (bearbeitet auf PC 1)"
    with pytest.raises(ExamConflictError, match="Mathe"):
        repo.save_exam(stale_copy)

    assert repo.load_exam(exam_file).exam_name == "Mathe (bearbeitet auf PC 2)"


def test_save_exam_allows_sequential_saves_from_the_same_session(tmp_path: Path) -> None:
    exam_folder = tmp_path / "exam"
    exam_folder.mkdir()
    repo = JsonExamRepository(index_root=tmp_path / "index")
    exam = _build_exam(exam_folder)
    exam_file = repo.save_exam(exam)

    exam.exam_name = "Mathe (Runde 2)"
    repo.save_exam(exam)
    exam.exam_name = "Mathe (Runde 3)"
    repo.save_exam(exam)

    assert repo.load_exam(exam_file).exam_name == "Mathe (Runde 3)"


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
