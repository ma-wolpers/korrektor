"""Real-Tk checks of Zuschnitt Schritt 2 "Einzelseiten" (synthetic data, shared `korrektor_window`)."""

from __future__ import annotations

import pytest
from tk_test_support import build_pdf, settle

from app.core.domain.models import ExamProject, RegionAssignment, RegionBox, StudentExam, TaskDefinition, UnscoredPage, utc_now_iso


@pytest.fixture
def step2_window(korrektor_window, tmp_path):
    """Anna and Ben, 2 pages each; Superseiten-Bereich A on page 2 (task 1A), Ben has an Einzelseiten-Bereich on page 1."""
    window = korrektor_window
    folder = tmp_path / "exam"
    folder.mkdir()
    for name in ("Anna", "Ben"):
        build_pdf(folder / f"{name}.pdf", 2, name)
    now = utc_now_iso()
    exam = ExamProject(
        exam_id="exam-step2",
        exam_name="Mathe",
        folder_path=str(folder),
        created_at=now,
        updated_at=now,
        standard_page_count=2,
        students=[StudentExam(student_id=n.lower(), display_name=n, pdf_filename=f"{n}.pdf", page_count=2) for n in ("Anna", "Ben")],
        regions=[
            RegionAssignment(region_id="r2", student_pdf="", page_number=2, box=RegionBox(0, 0, 100, 100), task_codes=["1A"], assigned_area_codes=["A"]),
            RegionAssignment(region_id="x-ben", student_pdf="Ben.pdf", page_number=1, box=RegionBox(0, 0, 50, 50), task_codes=["1A"], assigned_area_codes=["B"]),
        ],
        tasks=[TaskDefinition(code="1A", name="1A", max_points=2.0), TaskDefinition(code="1B", name="1B", max_points=1.0)],
    )
    exam.regions[0].task_codes = ["1A", "1B"]
    exam_file = window.deps.exam_repository.save_exam(exam)
    window._extra_all_pages_var.set(False)
    window.open_exam_detail(window.deps.exam_repository.load_exam(exam_file), exam_file)
    window._start_reading_mode()
    settle(window)
    yield window
    window._draft_regions.clear()
    window._return_to_overview()
    window.update()


def _editor(window) -> str:
    return window._quick_tasks_var.get()


def test_step_titles_walk_and_for_all_switch_spares_pages_with_region(step2_window):
    window = step2_window
    assert window._reading_mode_title_var.get() == "Zuschnitt · Schritt 1: Superseiten"

    window._toggle_zuschnitt_step()
    settle(window)
    assert window._reading_mode_title_var.get() == "Zuschnitt · Schritt 2: Einzelseiten"
    assert window._extra_sequence == [(0, 1), (1, 1)]
    assert "Seite 1 bei allen ohne Bewertung (1 mit Bereich" in str(window._unscored_all_switch.cget("text"))

    window._unscored_all_switch.invoke()
    settle(window)
    assert window._current_exam.unscored_pages == [UnscoredPage("Anna.pdf", 1)]
    assert [r.region_id for r in window._current_exam.regions if r.student_pdf] == ["x-ben"]

    window._toggle_current_page_unscored()
    settle(window)
    assert window._current_exam.unscored_pages == []
    window._toggle_zuschnitt_step()
    settle(window)
    assert window._reading_mode_title_var.get().startswith("Zuschnitt · Schritt 1")


def test_draw_einzelseiten_region_and_tick_an_existing_task(step2_window):
    window = step2_window
    window._toggle_zuschnitt_step()
    settle(window, 150)
    canvas = window._reading_canvas
    canvas.event_generate("<ButtonPress-1>", x=20, y=20)
    canvas.event_generate("<B1-Motion>", x=120, y=90)
    canvas.event_generate("<ButtonRelease-1>", x=120, y=90)
    settle(window)
    assert window._selected_region_kind == "draft"

    window._task_check_boxes["1B"].invoke()
    settle(window)
    assert _editor(window) == "1B"
    window._commit_reading_fields_if_possible()
    settle(window)

    regions = [r for r in window._current_exam.regions if r.student_pdf == "Anna.pdf"]
    assert len(regions) == 1 and regions[0].page_number == 1 and regions[0].task_codes == ["1B"]
    assert regions[0].region_id == window._selected_region_id and not window._draft_regions
    assert window._task_check_vars["1B"].get() is True and window._task_check_vars["1A"].get() is False


def test_checklist_never_loses_typed_input(step2_window):
    """A1: ticking only adds/removes that one code; new codes with points and invalid text survive."""
    window = step2_window
    window._toggle_zuschnitt_step()
    settle(window, 150)
    window._draft_regions.clear()
    canvas = window._reading_canvas
    canvas.event_generate("<ButtonPress-1>", x=20, y=20)
    canvas.event_generate("<B1-Motion>", x=120, y=90)
    canvas.event_generate("<ButtonRelease-1>", x=120, y=90)
    settle(window)

    window._quick_tasks_var.set("7a:2")
    window._task_check_boxes["1A"].invoke()  # new code 7A stays
    assert _editor(window) == "1A; 7A:2"
    window._quick_tasks_var.set("1A:2; 7A:2")
    window._task_check_boxes["1B"].invoke()  # points of an existing code stay too
    assert _editor(window) == "1A:2; 1B; 7A:2"
    window._task_check_boxes["1A"].invoke()  # untick 1A
    assert "7A:2" in _editor(window) and "1A" not in _editor(window)

    window._quick_tasks_var.set("4a-")  # invalid: ticking is rejected, text untouched
    before = window._task_check_vars["1A"].get()
    window._task_check_boxes["1A"].invoke()
    settle(window)
    assert _editor(window) == "4a-" and window._task_check_vars["1A"].get() is before
    assert "korrigieren" in window._task_checklist_hint_var.get()


def test_all_pages_switch_walks_superseiten_pages_and_shows_them_grey(step2_window):
    window = step2_window
    window._toggle_zuschnitt_step()
    settle(window, 150)

    window._on_extra_all_pages_switch(True)
    settle(window, 150)
    assert window._extra_sequence == [(0, 1), (0, 2), (1, 1), (1, 2)]
    window._change_extra_page(1)  # Anna, page 2 (Superseiten-Bereich A)
    settle(window, 150)
    assert window._reading_canvas.find_withtag("superseite")
    assert "Superseite" in window._reading_info_var.get()
    assert str(window._unscored_switch.cget("state")) == "disabled"
    window._on_extra_all_pages_switch(False)
