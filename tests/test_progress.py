from app.core.domain.models import ExamProject, RegionAssignment, RegionBox, StudentExam, utc_now_iso
from app.core.domain.progress import ProgressCalculator


def test_progress_detects_unassigned_extra_pages_and_missing_standard_pages() -> None:
    now = utc_now_iso()
    exam = ExamProject(
        exam_id="exam-1",
        exam_name="Mathe",
        folder_path="A:/tmp",
        created_at=now,
        updated_at=now,
        standard_page_count=3,
        students=[
            StudentExam(
                student_id="alice",
                display_name="Alice",
                pdf_filename="Alice.pdf",
                page_count=5,
                extra_pages=[4, 5],
            )
        ],
        regions=[
            RegionAssignment(
                region_id="r1",
                student_pdf="Alice.pdf",
                page_number=1,
                box=RegionBox(0, 0, 100, 100),
                is_read_complete=True,
                is_corrected=False,
            )
        ],
        is_reading_complete=False,
    )

    progress = ProgressCalculator().compute(exam)

    assert progress.has_unassigned_extra_pages is True
    assert progress.has_missing_page_markings is True
