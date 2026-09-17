import json
from pathlib import Path

from app.core.domain.progress import ProgressCalculator
from app.core.usecases.list_exams_usecase import ListExamsUseCase
from app.infrastructure.repositories.json_exam_repository import JsonExamRepository


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


def test_execute_skips_broken_exam_but_still_lists_valid_ones(tmp_path: Path) -> None:
    index_root = tmp_path / "index"
    index_root.mkdir(parents=True)

    (index_root / "valid-a.json").write_text(json.dumps(_valid_raw_exam("exam-a", "Anna")), encoding="utf-8")
    (index_root / "valid-c.json").write_text(json.dumps(_valid_raw_exam("exam-c", "Clara")), encoding="utf-8")
    broken = _valid_raw_exam("exam-b", "Bruno")
    broken.pop("extra_page_assignments")  # unsupported legacy schema -> ValueError on load
    (index_root / "broken-b.json").write_text(json.dumps(broken), encoding="utf-8")

    usecase = ListExamsUseCase(
        exam_repo=JsonExamRepository(index_root=index_root),
        progress_calculator=ProgressCalculator(),
    )

    overviews, errors = usecase.execute()

    assert [item.exam_name for item in overviews] == ["Anna", "Clara"]
    assert len(errors) == 1
    assert errors[0].exam_file.name == "broken-b.json"
