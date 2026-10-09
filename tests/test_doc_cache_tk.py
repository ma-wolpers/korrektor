"""PDF cache vs. exam switch: same file names in two exams must never mix (synthetic data, shared window)."""

from __future__ import annotations

from tk_test_support import build_pdf

from app.core.domain.models import ExamProject, StudentExam, utc_now_iso


def _exam_with_abgabe(window, folder, exam_id: str, tag: str):
    folder.mkdir()
    build_pdf(folder / "Abgabe_01.pdf", 1, tag)
    now = utc_now_iso()
    exam = ExamProject(
        exam_id=exam_id, exam_name=exam_id, folder_path=str(folder), created_at=now, updated_at=now, standard_page_count=1,
        students=[StudentExam(student_id="s1", display_name="Abgabe_01", pdf_filename="Abgabe_01.pdf", page_count=1)],
    )
    exam_file = window.deps.exam_repository.save_exam(exam)
    return window.deps.exam_repository.load_exam(exam_file), exam_file


def test_opening_another_exam_never_shows_the_previous_exams_pdf(korrektor_window, tmp_path):
    window = korrektor_window
    first, first_file = _exam_with_abgabe(window, tmp_path / "a", "exam-cache-a", "Erste")
    second, second_file = _exam_with_abgabe(window, tmp_path / "b", "exam-cache-b", "Zweite")
    try:
        window.open_exam_detail(first, first_file)
        assert window._correction_document("Abgabe_01.pdf").load_page(0).get_text().strip() == "Erste 1"

        window.open_exam_detail(second, second_file)
        assert window._correction_document("Abgabe_01.pdf").load_page(0).get_text().strip() == "Zweite 1"

        window._return_to_overview()
        assert window._doc_cache == {}
    finally:
        window._return_to_overview()
        window.update()
