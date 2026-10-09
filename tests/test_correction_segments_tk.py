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
    # The shared window's PDF cache is keyed by file name only (see the open
    # follow-up); keep later tests with an "Anna.pdf" from seeing this one.
    window.invalidate_doc_cache(["Anna.pdf", "Ben.pdf"])
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
