"""Overview progress (schema v2): Zuschnitt share of regions, correction progress = tasks finished by everybody."""

from app.core.domain.models import (
    ExamProject,
    PersonTaskCompletion,
    RegionAssignment,
    RegionBox,
    StudentExam,
    TaskDefinition,
    utc_now_iso,
)
from app.core.domain.progress import ProgressCalculator


def _exam(*, students, regions, tasks, completions=()) -> ExamProject:
    now = utc_now_iso()
    return ExamProject(
        exam_id="exam",
        exam_name="Mathe",
        folder_path="A:/tmp",
        created_at=now,
        updated_at=now,
        standard_page_count=2,
        students=students,
        regions=regions,
        tasks=tasks,
        person_task_completions=list(completions),
    )


def _student(sid: str, pages: int = 2) -> StudentExam:
    return StudentExam(student_id=sid, display_name=sid.title(), pdf_filename=f"{sid}.pdf", page_count=pages)


def _region(rid: str, page: int, codes: list[str], *, pdf: str = "", **kwargs) -> RegionAssignment:
    return RegionAssignment(region_id=rid, student_pdf=pdf, page_number=page, box=RegionBox(0, 0, 100, 100), task_codes=codes, assigned_area_codes=[rid.upper()], is_read_complete=True, **kwargs)


def test_progress_detects_open_einzelseiten_and_missing_standard_pages() -> None:
    """Only an Einzelseiten-Bereich on page 1: pages 2..5 are open, standard pages lack markings."""
    exam = _exam(students=[_student("alice", 5)], regions=[_region("r1", 1, ["1A"], pdf="alice.pdf")], tasks=[TaskDefinition("1A", "1A", 1)])

    progress = ProgressCalculator().compute(exam)

    assert progress.has_unassigned_extra_pages is True
    assert progress.has_missing_page_markings is True
    assert progress.reading_percent == 100.0 and progress.region_count == 1


def test_progress_counts_tasks_finished_for_all_students() -> None:
    exam = _exam(
        students=[_student("alice"), _student("bob")],
        regions=[_region("a", 1, ["1A", "1B"]), _region("b", 2, ["1B"])],  # 1B spans two regions, counts once
        tasks=[TaskDefinition("1A", "1A", 2), TaskDefinition("1B", "1B", 3)],
        completions=[
            PersonTaskCompletion("alice", "1A"),
            PersonTaskCompletion("bob", "1A"),
            PersonTaskCompletion("alice", "1B"),  # Bob not finished with 1B
        ],
    )

    progress = ProgressCalculator().compute(exam)

    assert (progress.corrected_task_count, progress.total_task_count) == (1, 2)
    assert progress.correction_percent == 50.0


def test_progress_correction_percent_ignores_dead_is_corrected_flag() -> None:
    exam = _exam(students=[_student("alice")], regions=[_region("a", 1, ["1A"], is_corrected=True)], tasks=[TaskDefinition("1A", "1A", 1)])

    progress = ProgressCalculator().compute(exam)

    assert progress.corrected_task_count == 0 and progress.correction_percent == 0.0


def test_progress_correction_percent_reaches_100_when_all_tasks_finished() -> None:
    exam = _exam(
        students=[_student("alice")],
        regions=[_region("a", 1, ["1A"])],
        tasks=[TaskDefinition("1A", "1A", 1)],
        completions=[PersonTaskCompletion("alice", "1A")],
    )

    progress = ProgressCalculator().compute(exam)

    assert progress.corrected_task_count == 1 and progress.correction_percent == 100.0
