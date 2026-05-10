from pathlib import Path

import pytest

from app.core.domain.models import ExamProject, StudentExam, utc_now_iso
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
