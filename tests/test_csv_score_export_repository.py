from pathlib import Path

from app.core.domain.models import ExamProject, RegionAssignment, RegionBox, StudentExam, TaskDefinition, utc_now_iso
from app.infrastructure.repositories.csv_score_export_repository import CsvScoreExportRepository
from app.infrastructure.repositories.csv_score_repository import CsvScoreRepository


def _build_exam(exam_folder: Path) -> ExamProject:
    now = utc_now_iso()
    return ExamProject(
        exam_id="exam-export-1",
        exam_name="Mathe",
        folder_path=str(exam_folder),
        created_at=now,
        updated_at=now,
        standard_page_count=2,
        students=[
            StudentExam(
                student_id="alice",
                display_name="Alice",
                pdf_filename="Alice.pdf",
                page_count=2,
            ),
            StudentExam(
                student_id="bob",
                display_name="Bob",
                pdf_filename="Bob.pdf",
                page_count=2,
            ),
        ],
        regions=[
            RegionAssignment(
                region_id="r-a",
                student_pdf="",
                page_number=1,
                box=RegionBox(0, 0, 100, 100),
                assigned_area_codes=["A"],
                tasks=[TaskDefinition(code="A1", name="A1", max_points=3.0)],
                is_read_complete=True,
            ),
            RegionAssignment(
                region_id="r-b",
                student_pdf="",
                page_number=2,
                box=RegionBox(0, 0, 100, 100),
                assigned_area_codes=["B"],
                tasks=[TaskDefinition(code="B1", name="B1", max_points=2.0)],
                is_read_complete=True,
            ),
        ],
    )


def test_export_scores_writes_max_row_and_keeps_unscored_tasks_empty(tmp_path: Path) -> None:
    exam_folder = tmp_path / "exam"
    exam_folder.mkdir(parents=True)
    exam = _build_exam(exam_folder)

    score_repo = CsvScoreRepository()
    score_repo.save_score(exam=exam, student_id="alice", task_code="A1", points=2.5, max_points=3.0)

    output_path = tmp_path / "export.csv"
    export_repo = CsvScoreExportRepository()
    export_repo.export_scores(exam=exam, output_csv=output_path)

    rows = output_path.read_text(encoding="utf-8").splitlines()

    assert rows[0] == "student_id,student_name,A1,B1"
    assert rows[1] == ",MAX,3,2"
    assert rows[2] == "alice,Alice,2.50,"
    assert rows[3] == "bob,Bob,,"
