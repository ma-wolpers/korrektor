"""Zuschnitt Schritt 2 domain rules: pages without a template region, open pages, "für alle"."""

from app.core.domain.models import (
    ExamProject,
    ExtraPageAssignment,
    RegionAssignment,
    RegionBox,
    StudentExam,
    UnscoredPage,
    utc_now_iso,
)
from app.core.domain.page_coverage import (
    compute_uncovered_pages,
    gradable_extra_pages,
    open_pages,
    pages_missing_markings,
    plan_page_for_all,
    uncovered_for_all,
    unscored_state_for_all,
)
from app.core.domain.progress import ProgressCalculator


def _exam(**kwargs) -> ExamProject:
    now = utc_now_iso()
    base = dict(
        exam_id="exam-1",
        exam_name="Mathe",
        folder_path="A:/tmp",
        created_at=now,
        updated_at=now,
        standard_page_count=3,
        students=[
            StudentExam(student_id="anna", display_name="Anna", pdf_filename="Anna.pdf", page_count=4),
            StudentExam(student_id="ben", display_name="Ben", pdf_filename="Ben.pdf", page_count=3),
            StudentExam(student_id="cem", display_name="Cem", pdf_filename="Cem.pdf", page_count=3),
        ],
        # page 1 = Deckblatt without region; pages 2 and 3 have template regions
        regions=[
            RegionAssignment(region_id="r2", student_pdf="", page_number=2, box=RegionBox(0, 0, 10, 10)),
            RegionAssignment(region_id="r3", student_pdf="", page_number=3, box=RegionBox(0, 0, 10, 10)),
        ],
        extra_page_assignments=[],
    )
    base.update(kwargs)
    return ExamProject(**base)


def _assignment(pdf: str, page: int) -> ExtraPageAssignment:
    return ExtraPageAssignment(assignment_id=f"x-{pdf}-{page}", student_pdf=pdf, page_number=page, box=RegionBox(0, 0, 1, 1), assigned_area_codes=["A"])


def test_uncovered_pages_are_all_pages_without_template_region_not_only_beyond_the_minimum():
    exam = _exam()

    assert compute_uncovered_pages(exam) == {"Anna.pdf": [1, 4], "Ben.pdf": [1], "Cem.pdf": [1]}
    assert uncovered_for_all(exam) == [1]


def test_student_specific_regions_do_not_cover_pages():
    exam = _exam(regions=[RegionAssignment(region_id="r", student_pdf="Anna.pdf", page_number=2, box=RegionBox(0, 0, 1, 1))])

    assert 2 in compute_uncovered_pages(exam)["Anna.pdf"]


def test_open_pages_exclude_assigned_and_unscored():
    exam = _exam(
        extra_page_assignments=[_assignment("Anna.pdf", 4)],
        unscored_pages=[UnscoredPage("Anna.pdf", 1), UnscoredPage("Ben.pdf", 1)],
    )

    assert open_pages(exam) == [("Cem.pdf", 1)]
    assert gradable_extra_pages(exam, "Anna.pdf") == [4]
    assert pages_missing_markings(exam) == [1]


def test_deckblatt_unscored_for_everybody_is_complete_in_progress():
    exam = _exam(
        students=[StudentExam(student_id="ben", display_name="Ben", pdf_filename="Ben.pdf", page_count=3)],
        unscored_pages=[UnscoredPage("Ben.pdf", 1)],
    )

    progress = ProgressCalculator().compute(exam)

    assert progress.has_unassigned_extra_pages is False
    assert progress.has_missing_page_markings is False


def test_for_all_unscore_never_touches_assigned_pages():
    exam = _exam(extra_page_assignments=[_assignment("Ben.pdf", 1)], unscored_pages=[UnscoredPage("Cem.pdf", 1)])

    plan = plan_page_for_all(exam, 1, "unscore")

    assert plan.affected == ("Anna.pdf",)
    assert plan.excluded == ("Ben.pdf",)
    assert plan.unchanged == ("Cem.pdf",)
    assert unscored_state_for_all(exam, 1) == "mixed"


def test_for_all_assign_respects_conscious_unscored_decisions():
    exam = _exam(extra_page_assignments=[_assignment("Ben.pdf", 1)], unscored_pages=[UnscoredPage("Cem.pdf", 1)])

    plan = plan_page_for_all(exam, 1, "assign")

    assert plan.affected == ("Anna.pdf",)
    assert set(plan.excluded) == {"Ben.pdf", "Cem.pdf"}


def test_for_all_switch_state_on_off_and_pages_not_uncovered_for_all():
    exam = _exam()
    assert unscored_state_for_all(exam, 1) == "off"
    all_marked = _exam(unscored_pages=[UnscoredPage(pdf, 1) for pdf in ("Anna.pdf", "Ben.pdf", "Cem.pdf")])
    assert unscored_state_for_all(all_marked, 1) == "on"
    assert plan_page_for_all(exam, 4, "unscore").affected == ()


def test_unscored_pages_roundtrip_and_legacy_extra_pages_key_is_ignored():
    exam = _exam(unscored_pages=[UnscoredPage("Anna.pdf", 1)])
    raw = exam.to_dict()
    raw["students"][0]["extra_pages"] = [99]

    restored = ExamProject.from_dict(raw)

    assert restored.unscored_pages == [UnscoredPage("Anna.pdf", 1)]
    assert "extra_pages" not in restored.to_dict()["students"][0]
    assert not hasattr(restored.students[0], "extra_pages")
