from pathlib import Path

import pytest

from app.adapters.bootstrap.wiring import build_gui_dependencies
from app.adapters.gui import ui_intent_controller as uic_module
from app.adapters.gui.ui_intent_controller import UiIntentController
from app.core.domain.grading_scale import SCALE_TYPE_SCHOOL_1_6, GradeThreshold, GradingScale
from app.core.domain.models import ExamProject, RegionAssignment, RegionBox, StudentExam, TaskDefinition, utc_now_iso


@pytest.fixture(autouse=True)
def _no_real_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent showerror/showinfo from opening a real (blocking) Tk dialog."""
    monkeypatch.setattr(uic_module.messagebox, "showerror", lambda *args, **kwargs: None)
    monkeypatch.setattr(uic_module.messagebox, "showinfo", lambda *args, **kwargs: None)


class _FakeApp:
    def __init__(self) -> None:
        self.status_messages: list[str] = []

    def set_status(self, text: str) -> None:
        self.status_messages.append(text)

    def render_overview_rows(self, rows) -> None:
        pass

    def sync_current_exam_from_repository(self) -> None:
        pass

    def refresh_exam_content_in_place(self) -> None:
        pass


def _build_exam(exam_folder: Path) -> ExamProject:
    now = utc_now_iso()
    return ExamProject(
        exam_id="exam-1",
        exam_name="Mathe",
        folder_path=str(exam_folder),
        created_at=now,
        updated_at=now,
        standard_page_count=1,
        students=[
            StudentExam(student_id="alice", display_name="Alice", pdf_filename="Alice.pdf", page_count=1),
            StudentExam(student_id="bob", display_name="Bob", pdf_filename="Bob.pdf", page_count=1),
        ],
        regions=[
            RegionAssignment(
                region_id="r-a",
                student_pdf="",
                page_number=1,
                box=RegionBox(0, 0, 100, 100),
                task_codes=["1A"],
                assigned_area_codes=["A"],
                is_read_complete=True,
            ),
        ],
        tasks=[TaskDefinition(code="1A", name="1A", max_points=10.0)],
    )


def _setup(tmp_path: Path) -> tuple[UiIntentController, ExamProject]:
    exam_folder = tmp_path / "exam"
    exam_folder.mkdir()
    deps = build_gui_dependencies(tmp_path / "repo")
    app = _FakeApp()
    controller = UiIntentController(app=app, deps=deps)
    exam = _build_exam(exam_folder)
    controller._deps.exam_repository.save_exam(exam)
    return controller, exam


def _reload(controller: UiIntentController) -> ExamProject:
    return controller._deps.exam_repository.load_exam(controller._deps.exam_repository.exam_file_for_id("exam-1"))


def test_apply_scored_superposition_creates_personalized_content_per_student(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)
    controller._deps.score_repository.save_score(exam=exam, student_id="alice", task_code="1A", points=8.0, max_points=10.0)
    controller._deps.score_repository.save_score(exam=exam, student_id="bob", task_code="1A", points=5.0, max_points=10.0)

    updated = controller.apply_scored_superposition_immediate(
        exam=exam,
        region_id="r-a",
        page_number=1,
        task_codes=["1A"],
        student_ids=["alice", "bob"],
        annotation_type="text",
        color_hex="#d62828",
        font_size=14.0,
        x=10.0,
        y=10.0,
    )

    assert updated is not None
    by_pdf = {a.student_pdf: a for a in updated.pdf_annotations}
    assert by_pdf["Alice.pdf"].content == "8"
    assert by_pdf["Bob.pdf"].content == "5"
    assert by_pdf["Alice.pdf"].sync_group_id == by_pdf["Bob.pdf"].sync_group_id
    assert by_pdf["Alice.pdf"].x == by_pdf["Bob.pdf"].x == 10.0


def test_apply_scored_superposition_is_one_undoable_action(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)
    controller._deps.score_repository.save_score(exam=exam, student_id="alice", task_code="1A", points=8.0, max_points=10.0)
    controller._deps.score_repository.save_score(exam=exam, student_id="bob", task_code="1A", points=5.0, max_points=10.0)

    controller.apply_scored_superposition_immediate(
        exam=exam, region_id="r-a", page_number=1, task_codes=["1A"], student_ids=["alice", "bob"],
        annotation_type="text", color_hex="#d62828", font_size=14.0, x=10.0, y=10.0,
    )
    assert len(_reload(controller).pdf_annotations) == 2

    assert controller.undo() is True
    assert len(_reload(controller).pdf_annotations) == 0

    assert controller.redo() is True
    assert len(_reload(controller).pdf_annotations) == 2


def test_apply_scored_superposition_rejects_entirely_when_one_student_missing_points(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)
    controller._deps.score_repository.save_score(exam=exam, student_id="alice", task_code="1A", points=8.0, max_points=10.0)
    # Bob has no recorded points for 1A.

    updated = controller.apply_scored_superposition_immediate(
        exam=exam, region_id="r-a", page_number=1, task_codes=["1A"], student_ids=["alice", "bob"],
        annotation_type="text", color_hex="#d62828", font_size=14.0, x=10.0, y=10.0,
    )

    assert updated is None
    assert len(_reload(controller).pdf_annotations) == 0


def test_scored_superposition_style_change_never_touches_personalized_content(tmp_path: Path) -> None:
    """Meilenstein 3 invariant: sync-group style propagation must never overwrite personalized content."""
    controller, exam = _setup(tmp_path)
    controller._deps.score_repository.save_score(exam=exam, student_id="alice", task_code="1A", points=8.0, max_points=10.0)
    controller._deps.score_repository.save_score(exam=exam, student_id="bob", task_code="1A", points=5.0, max_points=10.0)

    updated = controller.apply_scored_superposition_immediate(
        exam=exam, region_id="r-a", page_number=1, task_codes=["1A"], student_ids=["alice", "bob"],
        annotation_type="text", color_hex="#d62828", font_size=14.0, x=10.0, y=10.0,
    )
    assert updated is not None
    alice_annotation_id = next(a.annotation_id for a in updated.pdf_annotations if a.student_pdf == "Alice.pdf")

    resized = controller.resize_annotation_immediate(exam=updated, annotation_id=alice_annotation_id, delta=4.0)
    assert resized is not None
    resized = controller.set_annotation_orientation_immediate(
        exam=resized, annotation_id=alice_annotation_id, rotation_deg=90.0, mirrored=True
    )
    by_pdf = {a.student_pdf: a for a in resized.pdf_annotations}
    assert {(a.rotation_deg, a.mirrored) for a in by_pdf.values()} == {(90.0, True)}
    assert by_pdf["Alice.pdf"].font_size == 18.0
    assert by_pdf["Bob.pdf"].font_size == 18.0
    # content stayed personalized despite the shared style change
    assert by_pdf["Alice.pdf"].content == "8"
    assert by_pdf["Bob.pdf"].content == "5"


def _assign_scale(controller: UiIntentController, exam: ExamProject) -> None:
    scale = GradingScale(
        scale_id="",
        name="Mathe 8",
        subject="Mathe",
        year="8",
        school="Musterschule",
        scale_type=SCALE_TYPE_SCHOOL_1_6,
        thresholds=[GradeThreshold(min_percent=80.0, grade_label="1"), GradeThreshold(min_percent=50.0, grade_label="2")],
    )
    saved = controller.save_grading_scale_immediate(scale=scale)
    controller.assign_grading_scale_immediate(exam=exam, scale_id=saved.scale_id)


def test_apply_grade_superposition_requires_assigned_scale(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)
    controller._deps.score_repository.save_score(exam=exam, student_id="alice", task_code="1A", points=8.0, max_points=10.0)

    updated = controller.apply_grade_superposition_immediate(
        exam=exam, region_id="r-a", page_number=1, task_codes=["1A"], student_ids=["alice"],
        annotation_type="text", color_hex="#d62828", font_size=14.0, x=10.0, y=10.0,
    )

    assert updated is None


def test_apply_grade_superposition_computes_personalized_grades(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)
    _assign_scale(controller, exam)
    controller._deps.score_repository.save_score(exam=exam, student_id="alice", task_code="1A", points=9.0, max_points=10.0)
    controller._deps.score_repository.save_score(exam=exam, student_id="bob", task_code="1A", points=6.0, max_points=10.0)

    updated = controller.apply_grade_superposition_immediate(
        exam=exam, region_id="r-a", page_number=1, task_codes=["1A"], student_ids=["alice", "bob"],
        annotation_type="text", color_hex="#d62828", font_size=14.0, x=10.0, y=10.0,
    )

    assert updated is not None
    by_pdf = {a.student_pdf: a for a in updated.pdf_annotations}
    assert by_pdf["Alice.pdf"].content == "1"
    assert by_pdf["Bob.pdf"].content == "2"


def test_apply_grade_superposition_rejects_entirely_when_one_student_below_lowest_threshold(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)
    _assign_scale(controller, exam)
    controller._deps.score_repository.save_score(exam=exam, student_id="alice", task_code="1A", points=9.0, max_points=10.0)
    controller._deps.score_repository.save_score(exam=exam, student_id="bob", task_code="1A", points=1.0, max_points=10.0)

    updated = controller.apply_grade_superposition_immediate(
        exam=exam, region_id="r-a", page_number=1, task_codes=["1A"], student_ids=["alice", "bob"],
        annotation_type="text", color_hex="#d62828", font_size=14.0, x=10.0, y=10.0,
    )

    assert updated is None
    assert len(_reload(controller).pdf_annotations) == 0


def _build_two_region_exam(exam_folder: Path) -> ExamProject:
    """Second Bereich, so a Bereich-scoped grade would diverge from the exam-wide Auswertung grade."""
    now = utc_now_iso()
    return ExamProject(
        exam_id="exam-1",
        exam_name="Mathe",
        folder_path=str(exam_folder),
        created_at=now,
        updated_at=now,
        standard_page_count=1,
        students=[
            StudentExam(student_id="alice", display_name="Alice", pdf_filename="Alice.pdf", page_count=1),
        ],
        regions=[
            RegionAssignment(
                region_id="r-a",
                student_pdf="",
                page_number=1,
                box=RegionBox(0, 0, 100, 100),
                task_codes=["1A"],
                assigned_area_codes=["A"],
                is_read_complete=True,
            ),
            RegionAssignment(
                region_id="r-b",
                student_pdf="",
                page_number=1,
                box=RegionBox(0, 100, 100, 200),
                task_codes=["2A"],
                assigned_area_codes=["B"],
                is_read_complete=True,
            ),
        ],
        tasks=[TaskDefinition(code="1A", name="1A", max_points=10.0), TaskDefinition(code="2A", name="2A", max_points=10.0)],
    )


def test_apply_grade_superposition_uses_exam_wide_grade_not_just_the_active_bereich(tmp_path: Path) -> None:
    """Regression test: the placed grade must equal the Auswertung's exam-wide grade, not a Bereich-only one.

    Alice scores full points (10/10) in Bereich r-a alone - a Bereich-scoped
    grade computed only from r-a would place a "1". Her second Bereich (r-b)
    drags the exam-wide total down to 12/20 (60%), which this Notenschluessel
    resolves to "2" - exactly the grade the Auswertung shows. Before the fix,
    this test would have observed content == "1" (the old, wrong, Bereich-
    scoped behavior) instead of "2".
    """
    controller, exam = _setup(tmp_path)
    # Replacing the whole exam under the same exam_id right after _setup's own
    # save - carry over its updated_at so this is recognized as building on
    # that save, not as an unrelated stale write (see ExamConflictError).
    current_updated_at = exam.updated_at
    exam = _build_two_region_exam(Path(exam.folder_path))
    exam.updated_at = current_updated_at
    controller._deps.exam_repository.save_exam(exam)
    _assign_scale(controller, exam)
    controller._deps.score_repository.save_score(exam=exam, student_id="alice", task_code="1A", points=10.0, max_points=10.0)
    controller._deps.score_repository.save_score(exam=exam, student_id="alice", task_code="2A", points=2.0, max_points=10.0)

    updated = controller.apply_grade_superposition_immediate(
        exam=exam, region_id="r-a", page_number=1, task_codes=["1A"], student_ids=["alice"],
        annotation_type="text", color_hex="#d62828", font_size=14.0, x=10.0, y=10.0,
    )

    assert updated is not None
    placed = next(a for a in updated.pdf_annotations if a.student_pdf == "Alice.pdf")
    assert placed.content == "2"

    result = controller.compute_student_result_for_exam(
        exam=updated, student_id="alice", scores=controller._deps.score_repository.load_scores(exam=updated)
    )
    assert result is not None
    assert placed.content == result.grade_label


def test_apply_scored_superposition_shows_achieved_only_by_default(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)
    controller._deps.score_repository.save_score(exam=exam, student_id="alice", task_code="1A", points=8.0, max_points=10.0)

    updated = controller.apply_scored_superposition_immediate(
        exam=exam, region_id="r-a", page_number=1, task_codes=["1A"], student_ids=["alice"],
        annotation_type="text", color_hex="#d62828", font_size=14.0, x=10.0, y=10.0,
    )

    assert updated is not None
    placed = next(a for a in updated.pdf_annotations if a.student_pdf == "Alice.pdf")
    assert placed.content == "8"


def test_apply_scored_superposition_shows_achieved_over_max_when_requested(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)
    controller._deps.score_repository.save_score(exam=exam, student_id="alice", task_code="1A", points=8.0, max_points=10.0)

    updated = controller.apply_scored_superposition_immediate(
        exam=exam, region_id="r-a", page_number=1, task_codes=["1A"], student_ids=["alice"],
        annotation_type="text", color_hex="#d62828", font_size=14.0, x=10.0, y=10.0,
        show_max_points=True,
    )

    assert updated is not None
    placed = next(a for a in updated.pdf_annotations if a.student_pdf == "Alice.pdf")
    assert placed.content == "8/10"


def test_apply_grade_superposition_rejects_entirely_when_page_missing_for_one_student(tmp_path: Path) -> None:
    """Regression: a page navigated to independent of the Bereich must exist for every target student."""
    controller, exam = _setup(tmp_path)
    _assign_scale(controller, exam)
    exam.students[0].page_count = 2  # Alice has 2 pages
    # Bob keeps page_count=1 from _build_exam - does not have page 2
    controller._deps.exam_repository.save_exam(exam)
    controller._deps.score_repository.save_score(exam=exam, student_id="alice", task_code="1A", points=9.0, max_points=10.0)
    controller._deps.score_repository.save_score(exam=exam, student_id="bob", task_code="1A", points=9.0, max_points=10.0)

    updated = controller.apply_grade_superposition_immediate(
        exam=exam, region_id="r-a", page_number=2, task_codes=["1A"], student_ids=["alice", "bob"],
        annotation_type="text", color_hex="#d62828", font_size=14.0, x=10.0, y=10.0,
    )

    assert updated is None
    assert len(_reload(controller).pdf_annotations) == 0


def test_apply_grade_superposition_places_when_page_exists_for_all(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)
    _assign_scale(controller, exam)
    exam.students[0].page_count = 2
    exam.students[1].page_count = 2
    controller._deps.exam_repository.save_exam(exam)
    controller._deps.score_repository.save_score(exam=exam, student_id="alice", task_code="1A", points=9.0, max_points=10.0)
    controller._deps.score_repository.save_score(exam=exam, student_id="bob", task_code="1A", points=9.0, max_points=10.0)

    updated = controller.apply_grade_superposition_immediate(
        exam=exam, region_id="r-a", page_number=2, task_codes=["1A"], student_ids=["alice", "bob"],
        annotation_type="text", color_hex="#d62828", font_size=14.0, x=10.0, y=10.0,
    )

    assert updated is not None
    assert len(updated.pdf_annotations) == 2


def _whole_task_exam(controller: UiIntentController, exam: ExamProject) -> ExamProject:
    """Task 1 = 1A (10 P.) + 1B (4 P., Bonus) + 1C (6 P.); 1A in Bereich r-a, 1B and 1C in r-b."""
    exam.tasks += [TaskDefinition(code="1B", name="1B", max_points=4.0, is_bonus=True), TaskDefinition(code="1C", name="1C", max_points=6.0)]
    exam.regions.append(RegionAssignment(region_id="r-b", student_pdf="", page_number=1, box=RegionBox(0, 100, 100, 200), task_codes=["1B", "1C"], assigned_area_codes=["B"]))
    controller._deps.exam_repository.save_exam(exam)
    exam = _reload(controller)
    for code, points in (("1A", 8.0), ("1B", 2.0), ("1C", 5.0)):
        controller._deps.score_repository.save_score(exam=exam, student_id="alice", task_code=code, points=points, max_points=10.0)
    return exam


def _place(controller, exam, method, task_codes, **extra):
    return getattr(controller, method)(
        exam=exam, region_id="r-a", page_number=1, task_codes=task_codes, student_ids=["alice"],
        annotation_type="text", color_hex="#d62828", font_size=14.0, x=10.0, y=10.0, **extra,
    )


def test_scored_superposition_of_a_whole_task_sums_all_subtasks_and_their_maximum(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)
    exam = _whole_task_exam(controller, exam)

    updated = _place(controller, exam, "apply_scored_superposition_immediate", ["1A", "1B", "1C"], show_max_points=True)

    placed = next(a for a in updated.pdf_annotations if a.student_pdf == "Alice.pdf")
    assert placed.content == "15/16"  # bonus 1B counts to the points, not to the maximum
    assert placed.live_value.kind == "points" and placed.live_value.task_codes == ("1A", "1B", "1C")


def test_percent_superposition_of_a_task_and_of_the_whole_exam(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)
    exam = _whole_task_exam(controller, exam)

    task = _place(controller, exam, "apply_percent_superposition_immediate", ["1C"])
    whole = _place(controller, task, "apply_percent_superposition_immediate", [])

    contents = [a.content for a in whole.pdf_annotations]
    assert contents == ["83 %", "94 %"]  # 5/6; (8+2+5)/16 = 93.75 %


def test_refresh_brings_every_live_text_to_the_current_points_and_keeps_the_rest(tmp_path: Path) -> None:
    """Points changed after placing: "Alle PDFs überschreiben" must write the new value, a missing one keeps the old."""
    controller, exam = _setup(tmp_path)
    _assign_scale(controller, exam)
    exam = _reload(controller)
    controller._deps.score_repository.save_score(exam=exam, student_id="alice", task_code="1A", points=9.0, max_points=10.0)
    controller._deps.score_repository.save_score(exam=exam, student_id="bob", task_code="1A", points=9.0, max_points=10.0)
    exam = _place(controller, exam, "apply_scored_superposition_immediate", ["1A"])
    exam = controller.apply_grade_superposition_immediate(
        exam=exam, region_id="r-a", page_number=1, task_codes=["1A"], student_ids=["alice", "bob"],
        annotation_type="text", color_hex="#d62828", font_size=14.0, x=20.0, y=20.0,
    )
    controller._deps.score_repository.save_score(exam=exam, student_id="alice", task_code="1A", points=6.0, max_points=10.0)
    controller._deps.score_repository.delete_score(exam=exam, student_id="bob", task_code="1A")

    refreshed, problems = controller.refresh_live_contents(exam=exam)

    alice = sorted(a.content for a in refreshed.pdf_annotations if a.student_pdf == "Alice.pdf")
    assert alice == ["2", "6"]  # points 9 -> 6, grade 1 -> 2
    assert [(a.student_pdf, a.content) for a in _reload(controller).pdf_annotations if a.student_pdf == "Bob.pdf"] == [("Bob.pdf", "1")]
    assert [(a.student_pdf, problem) for a, problem in problems] == [("Bob.pdf", "es fehlt die Bewertung von Aufgabe 1A")]
    assert sorted(a.content for a in _reload(controller).pdf_annotations if a.student_pdf == "Alice.pdf") == ["2", "6"]


def test_marks_without_a_live_source_load_from_old_files_unchanged(tmp_path: Path) -> None:
    from app.core.domain.models import PdfAnnotation

    raw = {"annotation_id": "a", "student_pdf": "Alice.pdf", "page_number": 1, "annotation_type": "text", "content": "7", "color_hex": "#000000", "x": 1, "y": 2}
    annotation = PdfAnnotation.from_dict(raw)
    assert annotation.live_value is None and PdfAnnotation.from_dict(annotation.to_dict()) == annotation
