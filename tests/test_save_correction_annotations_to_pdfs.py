"""Real-file regression test for `_save_correction_annotations_to_pdfs`.

No test previously exercised the actual PDF-write path of this method
(only `_estimate_annotation_rect`'s pure geometry was covered) - this
verifies the behavior end-to-end through a real `MainWindow` against a
real PDF file, both to guard the existing feature and to confirm its
recent refactor onto `rewrite_pdf_atomically` preserves exact behavior
(burns in annotations, re-running replaces old KORREKTOR_MARKER
annotations instead of duplicating them, and the file is genuinely
writable a second time right afterwards - no stale open handle left).

One `MainWindow` (and therefore one real `tk.Tk()` root) for the whole
module: `MainWindow` has no way to adopt an externally-supplied root (the
underlying `TkRootHost` supports it, but `MainWindow`'s own constructor
does not forward it - out of scope to change here), and creating/
destroying several real `Tk()` interpreters in one process was observed
to be intermittently flaky on this Windows setup (same root cause as the
bw-gui `ScrollableFrame` test suite's session-scoped-root fix). All three
checks therefore live in one test function against one shared setup.
"""

from __future__ import annotations

import os
from pathlib import Path

import fitz
import pytest

from app.adapters.bootstrap.wiring import build_gui_dependencies
from app.adapters.gui import ui_intent_controller as uic_module
from app.adapters.gui.main_window import MainWindow
from app.adapters.gui.ui_intent_controller import UiIntentController
from app.core.domain.models import (
    ExamProject,
    PdfAnnotation,
    RegionAssignment,
    RegionBox,
    StudentExam,
    TaskDefinition,
    utc_now_iso,
)


@pytest.fixture(autouse=True)
def _no_real_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(uic_module.messagebox, "showerror", lambda *args, **kwargs: None)
    monkeypatch.setattr(uic_module.messagebox, "showinfo", lambda *args, **kwargs: None)


def _build_student_pdf(path: Path) -> None:
    document = fitz.open()
    document.new_page(width=200, height=300)
    document.save(path)
    document.close()


def test_save_correction_annotations_to_pdfs_real_file_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    exam_folder = tmp_path / "exam"
    exam_folder.mkdir()
    pdf_path = exam_folder / "Alice.pdf"
    _build_student_pdf(pdf_path)

    deps = build_gui_dependencies(tmp_path / "repo")
    window = MainWindow(deps=deps)
    controller = UiIntentController(app=window, deps=deps)
    window.set_controller(controller)

    now = utc_now_iso()
    exam = ExamProject(
        exam_id="exam-1",
        exam_name="Mathe",
        folder_path=str(exam_folder),
        created_at=now,
        updated_at=now,
        standard_page_count=1,
        students=[StudentExam(student_id="alice", display_name="Alice", pdf_filename="Alice.pdf", page_count=1)],
        regions=[
            RegionAssignment(
                region_id="r-a",
                student_pdf="",
                page_number=1,
                box=RegionBox(0, 0, 100, 100),
                tasks=[TaskDefinition(code="1A", name="1A", max_points=10.0)],
                assigned_area_codes=["A"],
                is_read_complete=True,
            ),
        ],
        pdf_annotations=[
            PdfAnnotation(
                annotation_id="anno-1",
                student_pdf="Alice.pdf",
                page_number=1,
                annotation_type="text",
                content="8",
                color_hex="#d62828",
                x=10.0,
                y=10.0,
                task_code="1A",
                region_id="r-a",
                font_size=14.0,
                rotation_deg=0.0,
            ),
        ],
    )
    deps.exam_repository.save_exam(exam)
    window._current_exam = exam

    # --- 1. Burns in the marker annotation. ---
    window._save_correction_annotations_to_pdfs()

    document = fitz.open(pdf_path)
    try:
        page = document.load_page(0)
        subjects = [str((annot.info or {}).get("subject", "")) for annot in (page.annots() or [])]
    finally:
        document.close()
    assert any(subject == "KORREKTOR_MARKER:anno-1" for subject in subjects)

    # --- 2. Re-running replaces the marker annotation instead of duplicating it. ---
    window._save_correction_annotations_to_pdfs()

    document = fitz.open(pdf_path)
    try:
        page = document.load_page(0)
        marker_annots = [
            annot for annot in (page.annots() or []) if str((annot.info or {}).get("subject", "")).startswith("KORREKTOR_MARKER:")
        ]
    finally:
        document.close()
    assert len(marker_annots) == 1

    # --- 3. Windows-relevant: no stale open fitz.Document handle remains afterwards -
    #        a plain os.replace-based rewrite of the same path must succeed right away.
    temp_path = pdf_path.with_suffix(".check.pdf")
    check_document = fitz.open()
    check_document.new_page(width=200, height=300)
    check_document.save(temp_path)
    check_document.close()
    os.replace(temp_path, pdf_path)

    assert pdf_path.exists()
