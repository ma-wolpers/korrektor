"""Zuschnitt dropdowns "Abgabe"/"Seite" in Schritt 1 and 2 (synthetic data, shared `korrektor_window`)."""

from __future__ import annotations

import pytest
from tk_test_support import build_pdf, settle

from app.adapters.gui.main_window_zuschnitt_navigation import cursor_after_resequence
from app.core.domain.models import ExamProject, RegionAssignment, RegionBox, StudentExam, TaskDefinition, utc_now_iso
from bw_gui.runtime import combobox_selection


def _pick(dropdown, key) -> None:
    """Pick ``key`` like a user would (the bw-gui pick handler runs synchronously)."""
    combobox_selection.set_index(dropdown.widget, dropdown.keys.index(key), notify=True)


def _open(window, folder, pages: dict[str, int]):
    """Exam with one PDF per name (``pages`` = page counts) and a Superseiten-Bereich on page 1."""
    folder.mkdir()
    for name, count in pages.items():
        build_pdf(folder / f"{name}.pdf", count, name)
    now = utc_now_iso()
    exam = ExamProject(
        exam_id="exam-zuschnitt-nav",
        exam_name="Mathe",
        folder_path=str(folder),
        created_at=now,
        updated_at=now,
        standard_page_count=1,
        students=[StudentExam(student_id=n.lower(), display_name=n, pdf_filename=f"{n}.pdf", page_count=c) for n, c in pages.items()],
        regions=[RegionAssignment("sup", "", 1, RegionBox(0, 0, 100, 100), ["1A"], ["A"])],
        tasks=[TaskDefinition("1A", "1A", 2.0)],
    )
    exam_file = window.deps.exam_repository.save_exam(exam)
    window._extra_all_pages_var.set(False)
    window._superpage_var.set(False)
    window.open_exam_detail(window.deps.exam_repository.load_exam(exam_file), exam_file)
    window._start_reading_mode()
    settle(window)


@pytest.fixture
def zuschnitt(korrektor_window, tmp_path):
    """Opens an exam via ``zuschnitt(pages)``; leaves Zuschnitt and the Superseite switch clean afterwards."""
    window = korrektor_window
    yield lambda pages: (_open(window, tmp_path / "exam", pages), window)[1]
    window._superpage_var.set(False)
    window._extra_all_pages_var.set(False)
    window._return_to_overview()
    window.update()


def test_cursor_after_resequence_rules():
    walk = [(0, 2), (1, 1), (1, 3)]
    assert cursor_after_resequence(walk, (1, 1)) == 1  # still there
    assert cursor_after_resequence(walk, (1, 2)) == 2  # gone -> next after it
    assert cursor_after_resequence(walk, (1, 5)) == 0  # nothing after -> first
    assert cursor_after_resequence(walk, None) == 0


def test_step1_person_and_page_dropdowns_move_the_view(zuschnitt):
    window = zuschnitt({"Anna": 3, "Ben": 1})
    assert window._reading_student_dropdown.keys == ("anna", "ben")
    assert window._reading_page_dropdown.keys == (1, 2, 3)

    _pick(window._reading_page_dropdown, 3)
    assert window._reading_page == 3
    assert "Seite 3/3" in window._reading_info_var.get()

    _pick(window._reading_student_dropdown, "ben")  # Ben has 1 page: page clamped
    assert window._reading_student_cursor == 1
    assert window._reading_page == 1
    assert window._reading_page_dropdown.keys == (1,)
    assert window._reading_page_dropdown.selected_key == 1


def test_step1_superseite_locks_person_list_and_offers_all_pages(zuschnitt):
    window = zuschnitt({"Anna": 3, "Ben": 1})
    _pick(window._reading_student_dropdown, "ben")
    window._superpage_var.set(True)
    window._on_superpage_toggle()
    assert str(window._reading_student_dropdown.widget.cget("state")) == "disabled"
    assert window._reading_page_dropdown.keys == (1, 2, 3)

    _pick(window._reading_page_dropdown, 3)
    window._superpage_var.set(False)
    window._on_superpage_toggle()  # back to Ben (1 page): page 3 is clamped
    assert window._reading_page == 1
    assert window._reading_page_dropdown.selected_key == 1
    assert str(window._reading_student_dropdown.widget.cget("state")) == "readonly"


def test_step2_dropdowns_follow_walk_and_keep_position_when_walk_changes(zuschnitt):
    window = zuschnitt({"Anna": 2, "Ben": 2})
    window._toggle_zuschnitt_step()
    settle(window)
    assert window._extra_sequence == [(0, 2), (1, 2)]
    assert window._extra_student_dropdown.keys == ("anna", "ben")
    assert window._extra_page_dropdown.keys == (("anna", 2),)

    window._on_extra_all_pages_switch(True)
    _pick(window._extra_page_dropdown, ("anna", 1))
    assert window._current_extra_target()[1] == 1

    window._on_extra_all_pages_switch(False)  # (anna, 1) leaves the walk -> next entry (anna, 2)
    assert window._extra_sequence[window._extra_cursor] == (0, 2)
    assert window._extra_page_dropdown.selected_key == ("anna", 2)

    _pick(window._extra_student_dropdown, "ben")
    assert window._extra_sequence[window._extra_cursor] == (1, 2)
    assert window._extra_page_dropdown.keys == (("ben", 2),)


def test_single_entry_and_empty_walk(zuschnitt):
    window = zuschnitt({"Anna": 2})
    window._toggle_zuschnitt_step()
    settle(window)
    assert window._extra_student_dropdown.keys == ("anna",)
    assert str(window._extra_student_dropdown.widget.cget("state")) == "readonly"

    window._extra_sequence = []
    window._sync_extra_nav_dropdowns()
    assert window._extra_student_dropdown.selected_key is None
    assert str(window._extra_page_dropdown.widget.cget("state")) == "disabled"
