import json
import shutil
from pathlib import Path

from app.core.domain.progress import ProgressCalculator
from app.core.usecases.list_exams_usecase import ListExamsUseCase
from app.infrastructure.repositories.json_exam_repository import EXAM_DATA_FILENAME, JsonExamRepository


def _valid_raw_exam(exam_id: str, exam_name: str) -> dict[str, object]:
    return {
        "exam_id": exam_id,
        "exam_name": exam_name,
        "folder_path": "A:/tmp/exam",
        "created_at": "2025-01-01T00:00:00.000000Z",
        "updated_at": "2025-01-01T00:00:00.000000Z",
        "standard_page_count": 1,
        "students": [],
        "regions": [],
        "extra_page_assignments": [],
        "person_area_completions": [],
        "task_comments": {},
        "pdf_annotations": [],
        "is_reading_complete": False,
    }


def _register_folder(repo: JsonExamRepository, folder: Path, raw: dict[str, object]) -> Path:
    folder.mkdir(parents=True)
    exam_file = folder / EXAM_DATA_FILENAME
    exam_file.write_text(json.dumps(raw), encoding="utf-8")
    repo.registry.register(str(raw["exam_id"]), folder)
    return exam_file


def test_execute_skips_broken_or_missing_exams_but_still_lists_valid_ones(tmp_path: Path) -> None:
    repo = JsonExamRepository(index_root=tmp_path / "index")
    _register_folder(repo, tmp_path / "a", _valid_raw_exam("exam-a", "Anna"))
    _register_folder(repo, tmp_path / "c", _valid_raw_exam("exam-c", "Clara"))
    broken = _valid_raw_exam("exam-b", "Bruno")
    broken.pop("extra_page_assignments")  # unsupported legacy schema -> ValueError on load
    _register_folder(repo, tmp_path / "b", broken)
    _register_folder(repo, tmp_path / "gone", _valid_raw_exam("exam-g", "Gina"))
    shutil.rmtree(tmp_path / "gone")

    overviews, errors = ListExamsUseCase(exam_repo=repo, progress_calculator=ProgressCalculator()).execute()

    assert [item.exam_name for item in overviews] == ["Anna", "Clara"]
    assert sorted(error.exam_file.parent.name for error in errors) == ["b", "gone"]
    assert any("nicht gefunden" in error.message for error in errors)
