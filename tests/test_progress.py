from app.core.domain.models import ExamProject, PersonAreaCompletion, RegionAssignment, RegionBox, StudentExam, utc_now_iso
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


def test_progress_counts_fully_finished_areas_for_all_students() -> None:
    now = utc_now_iso()
    exam = ExamProject(
        exam_id="exam-2",
        exam_name="Informatik",
        folder_path="A:/tmp",
        created_at=now,
        updated_at=now,
        standard_page_count=2,
        students=[
            StudentExam(
                student_id="alice",
                display_name="Alice",
                pdf_filename="Alice.pdf",
                page_count=2,
                extra_pages=[],
            ),
            StudentExam(
                student_id="bob",
                display_name="Bob",
                pdf_filename="Bob.pdf",
                page_count=2,
                extra_pages=[],
            ),
        ],
        regions=[
            RegionAssignment(
                region_id="r-a",
                student_pdf="",
                page_number=1,
                box=RegionBox(0, 0, 100, 100),
                assigned_area_codes=["A"],
                is_read_complete=True,
            ),
            RegionAssignment(
                region_id="r-b",
                student_pdf="",
                page_number=2,
                box=RegionBox(0, 0, 100, 100),
                assigned_area_codes=["B"],
                is_read_complete=True,
            ),
        ],
        person_area_completions=[
            # Area A is fully finished for all students.
            PersonAreaCompletion(
                student_id="alice",
                area_code="A",
                is_finished=True,
            ),
            PersonAreaCompletion(
                student_id="bob",
                area_code="A",
                is_finished=True,
            ),
            # Area B is unfinished for Bob.
            PersonAreaCompletion(
                student_id="alice",
                area_code="B",
                is_finished=True,
            ),
        ],
        is_reading_complete=True,
    )

    progress = ProgressCalculator().compute(exam)

    assert progress.total_area_count == 2
    assert progress.fully_finished_area_count == 1
