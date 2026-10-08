"""Controller actions of Zuschnitt Schritt 2 ("ohne Bewertung", "für alle zuordnen") with undo."""

from pathlib import Path

import pytest

from app.adapters.bootstrap.wiring import build_gui_dependencies
from app.adapters.gui import ui_intent_controller as uic_module
from app.adapters.gui.ui_intent_controller import UiIntentController
from app.core.domain.models import ExamProject, ExtraPageAssignment, RegionAssignment, RegionBox, StudentExam, TaskDefinition, UnscoredPage, utc_now_iso
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
                tasks=[TaskDefinition(code="1A", name="1A", max_points=2.0)], assigned_area_codes=["A"],
            )
        ],
        extra_page_assignments=[
            ExtraPageAssignment(assignment_id="x-ben", student_pdf="Ben.pdf", page_number=1, box=RegionBox(0, 0, 1, 1), assigned_area_codes=["A"])
        ],
    )
    controller = UiIntentController(app=_FakeApp(), deps=build_gui_dependencies(tmp_path / "repo"))
    exam_file = controller._deps.exam_repository.save_exam(exam)
    return controller, controller._deps.exam_repository.load_exam(exam_file)


def test_unscored_for_all_is_one_undo_step_and_skips_assigned_pages(controller_and_exam):
    controller, exam = controller_and_exam
    plan = plan_page_for_all(exam, 1, "unscore")
    assert plan.excluded == ("Ben.pdf",)

    updated = controller.set_pages_unscored_immediate(exam=exam, student_pdfs=list(plan.affected), page_number=1, unscored=True)

    assert set(updated.unscored_pages) == {UnscoredPage("Anna.pdf", 1), UnscoredPage("Cem.pdf", 1)}
    assert [a.student_pdf for a in updated.extra_page_assignments] == ["Ben.pdf"]
    controller.undo()
    reloaded = controller._deps.exam_repository.load_exam(controller._deps.exam_repository.exam_file_for_id("exam-1"))
    assert reloaded.unscored_pages == []


def test_unmarking_removes_only_marks(controller_and_exam):
    controller, exam = controller_and_exam
    exam = controller.set_pages_unscored_immediate(exam=exam, student_pdfs=["Anna.pdf", "Cem.pdf"], page_number=1, unscored=True)

    updated = controller.set_pages_unscored_immediate(exam=exam, student_pdfs=["Cem.pdf"], page_number=1, unscored=False)

    assert updated.unscored_pages == [UnscoredPage("Anna.pdf", 1)]
    assert len(updated.extra_page_assignments) == 1


def test_assign_for_all_only_for_planned_students(controller_and_exam):
    controller, exam = controller_and_exam
    exam = controller.set_pages_unscored_immediate(exam=exam, student_pdfs=["Cem.pdf"], page_number=1, unscored=True)
    plan = plan_page_for_all(exam, 1, "assign")
    assert plan.affected == ("Anna.pdf",)

    updated = controller.assign_extra_pages_for_all_immediate(
        exam=exam, page_number=1, box_by_pdf={pdf: (0, 0, 595, 842) for pdf in plan.affected}, area_codes=["a"]
    )

    by_pdf = {a.student_pdf: a for a in updated.extra_page_assignments}
    assert set(by_pdf) == {"Anna.pdf", "Ben.pdf"}
    assert by_pdf["Anna.pdf"].assigned_area_codes == ["A"]
    assert updated.unscored_pages == [UnscoredPage("Cem.pdf", 1)]


def test_assign_for_all_rejects_unknown_area(controller_and_exam):
    controller, exam = controller_and_exam

    assert controller.assign_extra_pages_for_all_immediate(exam=exam, page_number=1, box_by_pdf={"Anna.pdf": (0, 0, 1, 1)}, area_codes=["Z"]) is None
