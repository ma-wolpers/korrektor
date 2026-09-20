from pathlib import Path

from app.adapters.bootstrap.wiring import build_gui_dependencies
from app.adapters.gui.ui_intent_controller import UiIntentController
from app.core.domain.models import ExamProject, RegionAssignment, RegionBox, StudentExam, TaskDefinition, utc_now_iso


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


def _setup(tmp_path: Path) -> tuple[UiIntentController, ExamProject]:
    exam_folder = tmp_path / "exam"
    exam_folder.mkdir()
    deps = build_gui_dependencies(tmp_path / "app_data")
    app = _FakeApp()
    controller = UiIntentController(app=app, deps=deps)
    now = utc_now_iso()
    exam = ExamProject(
        exam_id="exam-1",
        exam_name="Mathe",
        folder_path=str(exam_folder),
        created_at=now,
        updated_at=now,
        standard_page_count=1,
        students=[
            StudentExam(student_id="alice", display_name="Alice Mueller", pdf_filename="Alice.pdf", page_count=1),
            StudentExam(student_id="bob", display_name="Bob", pdf_filename="Bob.pdf", page_count=1),
        ],
        regions=[
            RegionAssignment(
                region_id="r-a",
                student_pdf="",
                page_number=1,
                box=RegionBox(0, 0, 100, 100),
                tasks=[TaskDefinition(code="1A", name="1A", max_points=5.0)],
                assigned_area_codes=["A"],
                is_read_complete=True,
            ),
        ],
    )
    controller._deps.exam_repository.save_exam(exam)
    return controller, exam


def test_export_student_results_writes_one_file_per_student(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)
    controller._deps.score_repository.save_score(exam=exam, student_id="alice", task_code="1A", points=4.0, max_points=5.0)
    controller._deps.score_repository.save_score(exam=exam, student_id="bob", task_code="1A", points=3.0, max_points=5.0)
    scores = controller.load_scores_for_exam(exam=exam)
    output_dir = tmp_path / "export"
    output_dir.mkdir()

    exported, failed = controller.export_student_results(
        exam=exam,
        student_ids=["alice", "bob"],
        scores=scores,
        chart_type="Spinnennetz",
        chart_scope="Pro Aufgabe",
        output_dir=output_dir,
        file_extension="png",
    )

    assert failed == []
    assert set(exported) == {"Alice Mueller", "Bob"}
    assert (output_dir / "Alice Mueller.png").exists()
    assert (output_dir / "Bob.png").exists()
    assert (output_dir / "Alice Mueller.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_export_student_results_supports_pdf_and_jpg(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)
    scores = controller.load_scores_for_exam(exam=exam)
    output_dir = tmp_path / "export"
    output_dir.mkdir()

    exported_pdf, _failed = controller.export_student_results(
        exam=exam, student_ids=["alice"], scores=scores, chart_type="Balken", chart_scope="Pro Aufgabe",
        output_dir=output_dir, file_extension="pdf",
    )
    exported_jpg, _failed = controller.export_student_results(
        exam=exam, student_ids=["alice"], scores=scores, chart_type="Balken", chart_scope="Pro Aufgabe",
        output_dir=output_dir, file_extension="jpg",
    )

    assert exported_pdf == ["Alice Mueller"]
    assert exported_jpg == ["Alice Mueller"]
    assert (output_dir / "Alice Mueller.pdf").read_bytes().startswith(b"%PDF")
    assert (output_dir / "Alice Mueller.jpg").read_bytes().startswith(b"\xff\xd8\xff")


def test_export_student_results_skips_unknown_student_ids(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)
    scores = controller.load_scores_for_exam(exam=exam)
    output_dir = tmp_path / "export"
    output_dir.mkdir()

    exported, failed = controller.export_student_results(
        exam=exam, student_ids=["missing"], scores=scores, chart_type="Spinnennetz", chart_scope="Pro Aufgabe",
        output_dir=output_dir, file_extension="png",
    )

    assert exported == []
    assert failed == []


def test_export_student_results_continues_after_one_failure(tmp_path: Path, monkeypatch) -> None:
    controller, exam = _setup(tmp_path)
    scores = controller.load_scores_for_exam(exam=exam)
    output_dir = tmp_path / "export"
    output_dir.mkdir()

    real_execute = controller._deps.export_student_result_usecase.execute
    calls = {"count": 0}

    def _flaky_execute(*, result, chart_type, chart_scope, output_path):
        calls["count"] += 1
        if result.display_name == "Alice Mueller":
            raise OSError("disk full")
        return real_execute(result=result, chart_type=chart_type, chart_scope=chart_scope, output_path=output_path)

    monkeypatch.setattr(controller._deps.export_student_result_usecase, "execute", _flaky_execute)

    exported, failed = controller.export_student_results(
        exam=exam, student_ids=["alice", "bob"], scores=scores, chart_type="Spinnennetz", chart_scope="Pro Aufgabe",
        output_dir=output_dir, file_extension="png",
    )

    assert failed == ["Alice Mueller"]
    assert exported == ["Bob"]
    assert calls["count"] == 2
