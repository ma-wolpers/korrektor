from app.adapters.gui.main_window import MainWindow
from app.core.domain.models import ExamProject, RegionAssignment, RegionBox, StudentExam, utc_now_iso


def _template(page: int) -> RegionAssignment:
    return RegionAssignment(region_id=f"r{page}", student_pdf="", page_number=page, box=RegionBox(0, 0, 10, 10))


def test_build_extra_sequence_walks_pages_without_template_region_by_student_then_page() -> None:
    now = utc_now_iso()
    exam = ExamProject(
        exam_id="exam-1",
        exam_name="Mathe",
        folder_path="A:/tmp",
        created_at=now,
        updated_at=now,
        standard_page_count=3,
        students=[
            StudentExam(student_id="anna", display_name="Anna", pdf_filename="Anna.pdf", page_count=5),
            StudentExam(student_id="ben", display_name="Ben", pdf_filename="Ben.pdf", page_count=4),
        ],
        regions=[_template(1), _template(2), _template(3)],
        extra_page_assignments=[],
    )

    sequence = MainWindow._build_extra_sequence(exam)

    assert sequence == [(0, 4), (0, 5), (1, 4)]
