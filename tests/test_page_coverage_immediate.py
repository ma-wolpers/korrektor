"""Controller actions of Zuschnitt Schritt 2 ("ohne Bewertung", also "bei allen") with undo."""

from pathlib import Path

import pytest

from app.adapters.bootstrap.wiring import build_gui_dependencies
from app.adapters.gui import ui_intent_controller as uic_module
from app.adapters.gui.ui_intent_controller import UiIntentController
from app.core.domain.models import ExamProject, RegionAssignment, RegionBox, StudentExam, TaskDefinition, UnscoredPage, utc_now_iso
from app.core.domain.page_coverage import plan_page_for_all


class _FakeApp:
    def set_status(self, text: str) -> None:
        pass

    def render_overview_rows(self, rows) -> None:
        pass

    def sync_current_exam_from_repository(self) -> None:
        pass

    def refresh_exam_content_in_place(self) -> None:
        pass


@pytest.fixture
def controller_and_exam(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(uic_module.messagebox, "showerror", lambda *args, **kwargs: None)
    monkeypatch.setattr(uic_module.messagebox, "showinfo", lambda *args, **kwargs: None)
    folder = tmp_path / "exam"
    folder.mkdir()
    now = utc_now_iso()
    exam = ExamProject(
        exam_id="exam-1",
        exam_name="Mathe",
        folder_path=str(folder),
        created_at=now,
        updated_at=now,
        standard_page_count=2,
        students=[
            StudentExam(student_id=name.lower(), display_name=name, pdf_filename=f"{name}.pdf", page_count=2)
            for name in ("Anna", "Ben", "Cem")
        ],
        regions=[
            RegionAssignment(
                region_id="r2", student_pdf="", page_number=2, box=RegionBox(0, 0, 10, 10),
                task_codes=["1A"], assigned_area_codes=["A"],
            ),
            RegionAssignment(
                region_id="x-ben", student_pdf="Ben.pdf", page_number=1, box=RegionBox(0, 0, 1, 1),
                task_codes=["1A"], assigned_area_codes=["B"],
            ),
        ],
        tasks=[TaskDefinition(code="1A", name="1A", max_points=2.0)],
    )
    controller = UiIntentController(app=_FakeApp(), deps=build_gui_dependencies(tmp_path / "repo"))
    exam_file = controller._deps.exam_repository.save_exam(exam)
    return controller, controller._deps.exam_repository.load_exam(exam_file)


def test_unscored_for_all_is_one_undo_step_and_skips_pages_with_einzelseiten_region(controller_and_exam):
    controller, exam = controller_and_exam
    plan = plan_page_for_all(exam, 1)
    assert plan.excluded == ("Ben.pdf",)

    updated = controller.set_pages_unscored_immediate(exam=exam, student_pdfs=list(plan.affected), page_number=1, unscored=True)

    assert set(updated.unscored_pages) == {UnscoredPage("Anna.pdf", 1), UnscoredPage("Cem.pdf", 1)}
    assert [r.student_pdf for r in updated.regions if r.student_pdf] == ["Ben.pdf"]
    controller.undo()
    reloaded = controller._deps.exam_repository.load_exam(controller._deps.exam_repository.exam_file_for_id("exam-1"))
    assert reloaded.unscored_pages == []


def test_unmarking_removes_only_marks(controller_and_exam):
    controller, exam = controller_and_exam
    exam = controller.set_pages_unscored_immediate(exam=exam, student_pdfs=["Anna.pdf", "Cem.pdf"], page_number=1, unscored=True)

    updated = controller.set_pages_unscored_immediate(exam=exam, student_pdfs=["Cem.pdf"], page_number=1, unscored=False)

    assert updated.unscored_pages == [UnscoredPage("Anna.pdf", 1)]
    assert len(updated.regions) == 2


def test_page_with_einzelseiten_region_is_never_marked_unscored(controller_and_exam, monkeypatch):
    controller, exam = controller_and_exam
    shown = []
    monkeypatch.setattr(uic_module.messagebox, "showinfo", lambda title, text, **_: shown.append(text))

    assert controller.set_pages_unscored_immediate(exam=exam, student_pdfs=["Ben.pdf"], page_number=1, unscored=True) is None
    assert "Einzelseiten-Bereich" in shown[0]
