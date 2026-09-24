from pathlib import Path

import pytest

from app.core.usecases.create_exam_usecase import CreateExamUseCase
from app.infrastructure.repositories.json_exam_repository import JsonExamRepository


class _FakePdfScanRepository:
    """Fixed scan result - no real PDFs needed for exercising `CreateExamUseCase` logic."""

    def scan_exam_folder(self, folder_path: Path) -> list[tuple[str, int]]:
        return [("Alice.pdf", 2), ("Bob.pdf", 2)]


def test_execute_rejects_a_second_exam_for_an_already_indexed_folder(tmp_path: Path) -> None:
    """Re-running "Neue Klausur" on a folder already indexed must not silently
    create an empty duplicate that shadows the existing (worked-on) exam."""
    index_root = tmp_path / "index"
    exam_folder = tmp_path / "exam"
    exam_folder.mkdir(parents=True)

    usecase = CreateExamUseCase(
        exam_repo=JsonExamRepository(index_root=index_root),
        pdf_scan_repo=_FakePdfScanRepository(),
    )

    first = usecase.execute(folder_path=exam_folder, exam_name="Mathe 10a")

    with pytest.raises(ValueError, match="Mathe 10a"):
        usecase.execute(folder_path=exam_folder, exam_name="Mathe 10a (erneut eingelesen)")

    # the original exam must be untouched
    assert JsonExamRepository(index_root=index_root).load_exam(first.exam_file).exam_name == "Mathe 10a"


def test_execute_allows_a_second_exam_for_a_different_folder(tmp_path: Path) -> None:
    index_root = tmp_path / "index"
    folder_a = tmp_path / "exam-a"
    folder_b = tmp_path / "exam-b"
    folder_a.mkdir(parents=True)
    folder_b.mkdir(parents=True)

    usecase = CreateExamUseCase(
        exam_repo=JsonExamRepository(index_root=index_root),
        pdf_scan_repo=_FakePdfScanRepository(),
    )

    usecase.execute(folder_path=folder_a, exam_name="Mathe 10a")
    result_b = usecase.execute(folder_path=folder_b, exam_name="Mathe 10b")

    assert result_b.exam.exam_name == "Mathe 10b"
