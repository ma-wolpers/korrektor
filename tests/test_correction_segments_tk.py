"""Task-centric correction: all regions of the current (sub)task stacked (synthetic data, shared `korrektor_window`)."""

from __future__ import annotations

import pytest
from tk_test_support import FOCUS_ONLY, build_pdf, settle

from app.adapters.gui import dialog_services
from app.core.domain.models import ExamProject, PdfAnnotation, RegionAssignment, RegionBox, StudentExam, TaskDefinition, utc_now_iso
from app.core.domain.task_regions import regions_for_task


def _exam(folder) -> ExamProject:
    """1A: Superseite p.1 + Anna's Einzelseite p.2; 1B: Superseite p.1; 2A: only Anna's Einzelseite p.2."""
    now = utc_now_iso()
    return ExamProject(
        exam_id="exam-segments",
        exam_name="Mathe",
        folder_path=str(folder),
        created_at=now,
        updated_at=now,
        standard_page_count=1,
        students=[
            StudentExam(student_id="anna", display_name="Anna", pdf_filename="Anna.pdf", page_count=2),
            StudentExam(student_id="ben", display_name="Ben", pdf_filename="Ben.pdf", page_count=1),
        ],
        regions=[
            RegionAssignment("sup", "", 1, RegionBox(40, 40, 400, 300), ["1A", "1B"], ["A"]),
            RegionAssignment("anna2", "Anna.pdf", 2, RegionBox(40, 400, 400, 600), ["1A"], ["B"]),
            RegionAssignment("anna2b", "Anna.pdf", 2, RegionBox(40, 40, 400, 200), ["2A"], ["C"]),
        ],
        tasks=[TaskDefinition("1A", "1A", 2.0), TaskDefinition("1B", "1B", 1.0), TaskDefinition("2A", "2A", 3.0)],
    )


def test_regions_for_task_sorts_by_page_and_skips_superseiten_pages_a_person_lacks(tmp_path):
    exam = _exam(tmp_path)
    exam.regions.append(RegionAssignment("sup3", "", 3, RegionBox(0, 0, 10, 10), ["1A"], ["D"]))

    assert [r.region_id for r in regions_for_task(exam, "1a", "Anna.pdf", 2)] == ["sup", "anna2"]
    assert [r.region_id for r in regions_for_task(exam, "1A", "Ben.pdf", 1)] == ["sup"]
    assert [r.region_id for r in regions_for_task(exam, "1A", "Ben.pdf")] == ["sup", "sup3"]


@pytest.fixture
def correction(korrektor_window, tmp_path, monkeypatch):
    window = korrektor_window
    monkeypatch.setattr(dialog_services.messagebox, "showinfo", lambda *a, **k: None)
    folder = tmp_path / "exam"
    folder.mkdir()
    build_pdf(folder / "Anna.pdf", 2, "Anna")
    build_pdf(folder / "Ben.pdf", 1, "Ben")
    exam_file = window.deps.exam_repository.save_exam(_exam(folder))
    window.open_exam_detail(window.deps.exam_repository.load_exam(exam_file), exam_file)
    window._start_correction_mode()
    settle(window, 150)
    yield window
    window._stop_correction_mode(silent=True)
    window._return_to_overview()
    window.update()


def test_task_with_two_regions_shows_two_segments_and_a_click_lands_in_the_clicked_one(correction):
    window = correction
    assert window._selected_correction_task()[0] == "1A"
    segments = window._correction_segments
    assert [(s.region_id, s.page_number) for s in segments] == [("sup", 1), ("anna2", 2)]
    assert segments[1].y_offset > segments[0].y_offset + segments[0].height
    assert "Seite 1, 2 | 2 Bereiche" in window._correction_info_var.get()

    second = segments[1]
    x, y = 30.0, second.y_offset + 25.0
    assert window._place_annotation_from_canvas(canvas_x=x, canvas_y=y, annotation_type="symbol", content="✓")
    mark = window._current_exam.pdf_annotations[-1]
    assert (mark.page_number, mark.region_id, mark.task_code) == (2, "anna2", "1A")
    assert window._pdf_to_canvas_coords(mark.x, mark.y, window._segment_for_annotation(mark)) == pytest.approx((x, y))

    window._change_correction_student(1)  # Ben: only the Superseiten-Bereich
    settle(window)
    assert [s.region_id for s in window._correction_segments] == ["sup"]


def test_navigation_subtask_main_task_and_person_without_region(correction):
    window = correction
    window._cycle_correction_task(1)
    assert window._selected_correction_task()[0] == "1B"
    window._cycle_correction_main_task(1)
    assert window._selected_correction_task()[0] == "2A"
    assert [s.region_id for s in window._correction_segments] == ["anna2b"]
    assert window._current_correction_template() is None  # no Superseiten-Bereich: no Supersymbol

    window._change_correction_student(1)  # Ben has no region for 2A
    settle(window)
    assert window._correction_segments == [] and "kein Bereich" in window._correction_info_var.get()
    window._cycle_correction_main_task(-1)
    assert window._selected_correction_task()[0] == "1A"


def test_finished_applies_to_the_current_task_only(correction, monkeypatch):
    window = correction
    controller = window._controller
    student = window._current_correction_student()
    monkeypatch.setattr(window, "_all_tasks_scored_for_current_area", lambda: True)

    window._on_correction_finished_toggled(True)

    exam = window._current_exam
    assert controller.is_person_task_finished(exam=exam, student_id=student.student_id, task_code="1A")
    assert not controller.is_person_task_finished(exam=exam, student_id=student.student_id, task_code="1B")


def test_durchdruecken_is_refused_for_marks_in_an_einzelseiten_region(correction, monkeypatch):
    window = correction
    shown = []
    monkeypatch.setattr(dialog_services.messagebox, "showinfo", lambda title, text, **_: shown.append(text))
    exam = window._current_exam
    mark = PdfAnnotation("m-single", "Anna.pdf", 2, "symbol", "✓", "#ff0000", 60, 450, task_code="1A", region_id="anna2")
    exam.pdf_annotations.append(mark)

    result = window._controller.enable_annotation_sync_immediate(exam=exam, annotation_id="m-single", other_student_pdfs=["Ben.pdf"])

    assert result is None and "Einzelseiten-Bereich" in shown[-1]
    assert [item.annotation_id for item in exam.pdf_annotations].count("m-single") == 1



class _Pointer:
    """Stand-in for a Tk mouse event: widget coordinates ``x``/``y``."""

    def __init__(self, x: float, y: float) -> None:
        self.x, self.y = x, y


def _drag_mark(window, annotation_id: str, to_canvas: tuple[float, float]) -> None:
    """Grab the mark at its own point, drag it to canvas ``to_canvas`` and release (one gesture)."""
    canvas = window._correction_canvas
    mark = window._annotation_by_id(annotation_id)
    start = window._pdf_to_canvas_coords(mark.x, mark.y, window._segment_for_annotation(mark))
    window._begin_correction_annotation_drag(annotation_id, *start, alt_override=False)
    pointer = _Pointer(to_canvas[0] - canvas.canvasx(0), to_canvas[1] - canvas.canvasy(0))
    window._on_correction_canvas_drag(pointer)
    window._on_correction_canvas_release(pointer)


def _add_marks(window, *marks: PdfAnnotation) -> None:
    window._current_exam.pdf_annotations.extend(marks)
    window._render_correction_annotations()


def _saved_mark(window, annotation_id: str) -> PdfAnnotation:
    repository = window.deps.exam_repository
    exam = repository.load_exam(repository.exam_file_for_id("exam-segments"))
    return next(item for item in exam.pdf_annotations if item.annotation_id == annotation_id)


def test_dragging_a_mark_onto_another_crop_moves_it_into_that_region_persistently_and_undoably(correction):
    window = correction
    _add_marks(window, PdfAnnotation("m-text", "Anna.pdf", 1, "text", "Gut", "#ff0000", 100, 100, task_code="1A", region_id="sup"))
    target = window._correction_segments[1]

    _drag_mark(window, "m-text", (60.0, target.y_offset + target.height / 2))

    saved = _saved_mark(window, "m-text")
    assert (saved.region_id, saved.page_number) == ("anna2", 2)
    assert 40 <= saved.x <= 400 and 400 <= saved.y <= 600
    assert window._segment_for_annotation(window._annotation_by_id("m-text")).region_id == "anna2"
    assert window._controller.undo()
    assert _saved_mark(window, "m-text").region_id == "sup"


def test_dragging_past_every_crop_keeps_the_mark_inside_its_own_region(correction):
    window = correction
    _add_marks(window, PdfAnnotation("m-sym", "Anna.pdf", 1, "symbol", "✓", "#ff0000", 100, 100, task_code="1A", region_id="sup"))
    last = window._correction_segments[-1]

    _drag_mark(window, "m-sym", (5000.0, last.y_offset + last.height + 500.0))

    saved = _saved_mark(window, "m-sym")
    assert (saved.region_id, saved.x, saved.y) == ("sup", 400.0, 300.0)


def test_a_synced_group_never_enters_an_einzelseiten_region(correction):
    window = correction
    _add_marks(
        window,
        PdfAnnotation("m-anna", "Anna.pdf", 1, "symbol", "✓", "#ff0000", 100, 100, task_code="1A", region_id="sup", sync_group_id="sg-1"),
        PdfAnnotation("m-ben", "Ben.pdf", 1, "symbol", "✓", "#ff0000", 100, 100, task_code="1A", region_id="sup", sync_group_id="sg-1"),
    )
    target = window._correction_segments[1]
    assert target.is_single_page

    _drag_mark(window, "m-anna", (60.0, target.y_offset + target.height / 2))

    anna, ben = _saved_mark(window, "m-anna"), _saved_mark(window, "m-ben")
    assert anna.region_id == ben.region_id == "sup"
    assert (anna.x, anna.y) == (ben.x, ben.y) and anna.y == 300.0


def test_comment_inserted_while_the_preview_centre_is_on_a_gap_goes_into_the_nearest_crop(correction, monkeypatch):
    window = correction
    canvas = window._correction_canvas
    first = window._correction_segments[0]
    gap_y = first.y_offset + first.height + 4.0  # 4 px below the first crop, far from the second one
    monkeypatch.setattr(canvas, "winfo_height", lambda: int(round(2 * (gap_y - canvas.canvasy(0)))))
    window._correction_comment_var.set("Gut gemacht")

    window._insert_current_comment_into_preview_center()

    mark = window._current_exam.pdf_annotations[-1]
    assert (mark.annotation_type, mark.content, mark.region_id) == ("text", "Gut gemacht", "sup")
    assert mark.y == pytest.approx(first.clip_box[3])


def test_a_click_beside_a_narrow_crop_places_the_mark_on_its_edge(correction):
    window = correction
    first = window._correction_segments[0]

    assert window._place_annotation_from_canvas(canvas_x=5000.0, canvas_y=first.y_offset + 10.0, annotation_type="symbol", content="✓")

    mark = window._current_exam.pdf_annotations[-1]
    assert (mark.region_id, mark.x) == ("sup", first.clip_box[2])


def test_after_a_failed_move_save_the_mark_is_drawn_at_its_start_again(correction, monkeypatch):
    window = correction
    errors = []
    monkeypatch.setattr(dialog_services.messagebox, "showerror", lambda title, text, **_: errors.append(text))
    _add_marks(window, PdfAnnotation("m-fail", "Anna.pdf", 1, "symbol", "✓", "#ff0000", 100, 100, task_code="1A", region_id="sup"))
    start = window._pdf_to_canvas_coords(100, 100, window._correction_segments[0])

    def _boom(*_args, **_kwargs):
        raise OSError("Datei gesperrt")

    monkeypatch.setattr(window.deps.exam_repository, "save_exam", _boom)
    _drag_mark(window, "m-fail", (start[0] + 80.0, start[1] + 40.0))

    assert errors and "Datei gesperrt" in errors[-1]
    drawn = window._correction_canvas.coords(window._correction_annotation_items["m-fail"])
    assert drawn == pytest.approx(list(start))

@FOCUS_ONLY
def test_keys_switch_subtask_and_main_task(correction):
    window = correction
    canvas = window._correction_canvas
    canvas.focus_force()
    settle(window)
    canvas.event_generate("<Down>")
    settle(window)
    assert window._selected_correction_task()[0] == "1B"
    canvas.event_generate("<Control-Down>")
    settle(window)
    assert window._selected_correction_task()[0] == "2A"


def test_supersymbol_offers_the_subtask_and_the_whole_task(correction):
    window = correction
    assert tuple(window._supersymbol_scope_combo["values"]) == ("1A", "Aufgabe 1 gesamt (1A-B)")
    template = window._current_correction_template()

    window._supersymbol_scope_var.set("Aufgabe 1 gesamt (1A-B)")
    window._on_supersymbol_scope_changed(None)
    assert window._resolve_supersymbol_task_codes(template) == ["1A", "1B"]
    assert window._supersymbol_value_var.get() == "3"  # 2 + 1 P.

    window._supersymbol_scope_var.set("1A")
    window._on_supersymbol_scope_changed(None)
    assert window._resolve_supersymbol_task_codes(template) == ["1A"] and window._supersymbol_value_var.get() == "2"

    window._cycle_correction_task(1)  # 1B: same whole task offered again, selection falls back to the subtask
    settle(window)
    assert tuple(window._supersymbol_scope_combo["values"]) == ("1B", "Aufgabe 1 gesamt (1A-B)")
