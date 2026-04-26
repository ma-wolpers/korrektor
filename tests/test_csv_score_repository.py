from pathlib import Path

from app.core.domain.models import ExamProject, StudentExam, utc_now_iso
from app.infrastructure.repositories.csv_score_repository import CsvScoreRepository


def test_csv_is_stored_one_row_per_student(tmp_path: Path) -> None:
    now = utc_now_iso()
    exam_folder = tmp_path / "exam"
    exam_folder.mkdir(parents=True)

    exam = ExamProject(
        exam_id="exam-1",
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
            )
        ],
    )

    repo = CsvScoreRepository()
    repo.save_score(exam=exam, student_id="alice", task_code="A1", points=2.5, max_points=3.0)
    repo.save_score(exam=exam, student_id="alice", task_code="B1", points=1.0, max_points=2.0)

    csv_path = exam_folder / "korrektor_scores.csv"
    content = csv_path.read_text(encoding="utf-8")

    assert "student_id,student_name,A1_max,A1_points,B1_max,B1_points" in content
    assert content.count("alice") == 1
