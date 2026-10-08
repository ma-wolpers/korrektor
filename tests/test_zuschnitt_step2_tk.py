"""Real-Tk check of Zuschnitt Schritt 2 (synthetic data, shared `korrektor_window`)."""

from __future__ import annotations

from tk_test_support import build_pdf, settle

from app.core.domain.models import ExamProject, ExtraPageAssignment, RegionAssignment, RegionBox, StudentExam, TaskDefinition, UnscoredPage, utc_now_iso


def test_step2_walks_pages_without_region_and_for_all_switch_spares_assigned(korrektor_window, tmp_path):
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
            RegionAssignment(
                region_id="r2", student_pdf="", page_number=2, box=RegionBox(0, 0, 100, 100),
                tasks=[TaskDefinition(code="1A", name="1A", max_points=2.0)], assigned_area_codes=["A"],
            )
        ],
        extra_page_assignments=[
            ExtraPageAssignment(assignment_id="x-ben", student_pdf="Ben.pdf", page_number=1, box=RegionBox(0, 0, 1, 1), assigned_area_codes=["A"])
        ],
    )
    exam_file = window.deps.exam_repository.save_exam(exam)
    try:
        window.open_exam_detail(window.deps.exam_repository.load_exam(exam_file), exam_file)
        window._start_reading_mode()
        settle(window)
        assert window._reading_mode_title_var.get().startswith("Zuschnitt · Schritt 1")

        window._toggle_zuschnitt_step()
        settle(window)
        assert window._reading_mode_title_var.get().startswith("Zuschnitt · Schritt 2")
        assert window._extra_sequence == [(0, 1), (1, 1)]
        assert "Seite 1 bei allen ohne Bewertung (1 zugeordnet" in str(window._unscored_all_switch.cget("text"))

        window._unscored_all_switch.invoke()
        settle(window)
        assert window._current_exam.unscored_pages == [UnscoredPage("Anna.pdf", 1)]
        assert len(window._current_exam.extra_page_assignments) == 1

        window._toggle_current_page_unscored()
        settle(window)
        assert window._current_exam.unscored_pages == []

        window._toggle_zuschnitt_step()
        settle(window)
        assert window._reading_mode_title_var.get().startswith("Zuschnitt · Schritt 1")
    finally:
        window._return_to_overview()
        window.update()
