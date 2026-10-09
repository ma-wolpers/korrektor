from app.adapters.gui.main_window import MainWindow
from app.core.domain.models import ExamProject, RegionAssignment, RegionBox, StudentExam, TaskDefinition, utc_now_iso


def _template(page: int) -> RegionAssignment:
    return RegionAssignment(region_id=f"r{page}", student_pdf="", page_number=page, box=RegionBox(0, 0, 10, 10), task_codes=["1A"], assigned_area_codes=[f"L{page}"])


class _Toggle:
    """Stand-in for the BooleanVar of "Auch Seiten mit Superseiten-Bereich"."""

    def __init__(self, value: bool) -> None:
        self.value = value

    def get(self) -> bool:
        return self.value


class _Window:
    def __init__(self, all_pages: bool) -> None:
        self._extra_all_pages_var = _Toggle(all_pages)


def _exam() -> ExamProject:
    now = utc_now_iso()
    return ExamProject(
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
        tasks=[TaskDefinition("1A", "1A", 1.0)],
    )


def test_build_extra_sequence_walks_pages_without_superseiten_region_by_student_then_page() -> None:
    assert MainWindow._build_extra_sequence(_Window(False), _exam()) == [(0, 4), (0, 5), (1, 4)]


def test_build_extra_sequence_with_switch_walks_every_page() -> None:
    sequence = MainWindow._build_extra_sequence(_Window(True), _exam())

    assert sequence == [(0, 1), (0, 2), (0, 3), (0, 4), (0, 5), (1, 1), (1, 2), (1, 3), (1, 4)]
