from pathlib import Path

import fitz
import pytest

from app.adapters.bootstrap.wiring import build_gui_dependencies
from app.adapters.gui import ui_intent_controller as uic_module
from app.adapters.gui import ui_intent_controller_batch_export as batch_export_module
from app.adapters.gui.ui_intent_controller import UiIntentController
from app.core.domain.models import ExamProject, RegionAssignment, RegionBox, StudentExam, TaskDefinition, utc_now_iso
from app.infrastructure.pdf import pdf_document_writer as pdf_writer_module


@pytest.fixture(autouse=True)
def _no_real_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(uic_module.messagebox, "showerror", lambda *args, **kwargs: None)
    monkeypatch.setattr(uic_module.messagebox, "showinfo", lambda *args, **kwargs: None)


class _FakeApp:
    def set_status(self, text: str) -> None:
        pass

    def invalidate_doc_cache(self, pdf_filenames) -> None:
        pass

    def render_overview_rows(self, rows) -> None:
        pass

    def sync_current_exam_from_repository(self) -> None:
        pass

    def refresh_exam_content_in_place(self) -> None:
        pass


def _build_student_pdf(path: Path) -> None:
    document = fitz.open()
    document.new_page(width=200, height=300)
    document.save(path)
    document.close()


def _build_exam(exam_folder: Path, *, student_names: tuple[str, ...] = ("Alice", "Bob")) -> ExamProject:
    now = utc_now_iso()
    students = []
    for name in student_names:
        pdf_filename = f"{name}.pdf"
        _build_student_pdf(exam_folder / pdf_filename)
        students.append(
            StudentExam(student_id=name.lower(), display_name=name, pdf_filename=pdf_filename, page_count=1)
        )
    return ExamProject(
        exam_id="exam-1",
        exam_name="Mathe",
        folder_path=str(exam_folder),
        created_at=now,
        updated_at=now,
        standard_page_count=1,
        students=students,
        regions=[
            RegionAssignment(
                region_id="r-a",
                student_pdf="",
                page_number=1,
                box=RegionBox(0, 0, 100, 100),
                task_codes=["1A"],
                assigned_area_codes=["A"],
                is_read_complete=True,
            ),
        ],
        tasks=[TaskDefinition(code="1A", name="1A", max_points=10.0)],
        school_class="10a",
        subject="Mathematik",
    )


def _setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **exam_kwargs) -> tuple[UiIntentController, ExamProject, Path]:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    exam_folder = tmp_path / "exam"
    exam_folder.mkdir()
    deps = build_gui_dependencies(tmp_path / "repo")
    controller = UiIntentController(app=_FakeApp(), deps=deps)
    exam = _build_exam(exam_folder, **exam_kwargs)
    controller._deps.exam_repository.save_exam(exam)
    return controller, exam, exam_folder


def _page_count(pdf_path: Path) -> int:
    document = fitz.open(pdf_path)
    try:
        return document.page_count
    finally:
        document.close()


def _default_scores(controller: UiIntentController, exam: ExamProject) -> dict[str, dict[str, float]]:
    for student in exam.students:
        controller._deps.score_repository.save_score(
            exam=exam, student_id=student.student_id, task_code="1A", points=8.0, max_points=10.0
        )
    return controller._deps.score_repository.load_scores(exam=exam)


_ALL_SECTIONS = frozenset({"summary", "tasks", "categories", "chart"})


def test_export_batch_succeeds_from_scratch(tmp_path: Path, monkeypatch) -> None:
    controller, exam, folder = _setup(tmp_path, monkeypatch)
    scores = _default_scores(controller, exam)
    output_dir = tmp_path / "export"

    result = controller.export_students_batch(
        exam=exam,
        student_ids=["alice", "bob"],
        scores=scores,
        sections=_ALL_SECTIONS,
        chart_type="Spinnennetz",
        chart_scope="Pro Aufgabe",
        output_dir=output_dir,
        per_student_folders=False,
        filename_template="{Name}_{Klasse}_{Fach}_{Nr}",
    )

    assert result is not None
    exported, failed = result
    assert set(exported) == {"Alice", "Bob"}
    assert failed == []
    alice_path = output_dir / "Alice_10a_Mathematik_01.pdf"
    bob_path = output_dir / "Bob_10a_Mathematik_02.pdf"
    assert alice_path.exists()
    assert bob_path.exists()
    assert _page_count(alice_path) == 2
    assert pdf_writer_module.read_trailing_page_marker(alice_path) == pdf_writer_module.KORREKTOR_STATS_PAGE_MARKER
    # source PDFs must stay untouched by the export
    assert _page_count(folder / "Alice.pdf") == 1


def test_export_batch_rejects_empty_sections(tmp_path: Path, monkeypatch) -> None:
    controller, exam, _folder = _setup(tmp_path, monkeypatch)
    scores = _default_scores(controller, exam)

    result = controller.export_students_batch(
        exam=exam,
        student_ids=["alice"],
        scores=scores,
        sections=frozenset(),
        chart_type="Spinnennetz",
        chart_scope="Pro Aufgabe",
        output_dir=tmp_path / "export",
        per_student_folders=False,
        filename_template="{Name}",
    )

    assert result is None


def test_export_batch_sanitizes_unsafe_display_name_into_folder_name(tmp_path: Path, monkeypatch) -> None:
    controller, exam, _folder = _setup(tmp_path, monkeypatch, student_names=("Anna",))
    exam.students[0].display_name = "Müller / Anna"
    controller._deps.exam_repository.save_exam(exam)
    scores = _default_scores(controller, exam)
    output_dir = tmp_path / "export"

    result = controller.export_students_batch(
        exam=exam,
        student_ids=["anna"],
        scores=scores,
        sections=_ALL_SECTIONS,
        chart_type="Spinnennetz",
        chart_scope="Pro Aufgabe",
        output_dir=output_dir,
        per_student_folders=True,
        filename_template="{Name}",
    )

    assert result is not None
    exported, failed = result
    assert failed == []
    assert exported == ["Müller / Anna"]
    created_dirs = [entry.name for entry in output_dir.iterdir() if entry.is_dir()]
    assert len(created_dirs) == 1
    assert "/" not in created_dirs[0]


def test_export_batch_aborts_entirely_on_existing_destination_file(tmp_path: Path, monkeypatch) -> None:
    controller, exam, _folder = _setup(tmp_path, monkeypatch)
    scores = _default_scores(controller, exam)
    output_dir = tmp_path / "export"
    output_dir.mkdir()
    (output_dir / "Alice.pdf").write_bytes(b"already here")

    result = controller.export_students_batch(
        exam=exam,
        student_ids=["alice", "bob"],
        scores=scores,
        sections=_ALL_SECTIONS,
        chart_type="Spinnennetz",
        chart_scope="Pro Aufgabe",
        output_dir=output_dir,
        per_student_folders=False,
        filename_template="{Name}",
    )

    assert result is None
    assert not (output_dir / "Bob.pdf").exists()
    assert (output_dir / "Alice.pdf").read_bytes() == b"already here"


def test_export_batch_aborts_entirely_on_within_batch_collision(tmp_path: Path, monkeypatch) -> None:
    controller, exam, _folder = _setup(tmp_path, monkeypatch)
    scores = _default_scores(controller, exam)
    output_dir = tmp_path / "export"

    result = controller.export_students_batch(
        exam=exam,
        student_ids=["alice", "bob"],
        scores=scores,
        sections=_ALL_SECTIONS,
        chart_type="Spinnennetz",
        chart_scope="Pro Aufgabe",
        output_dir=output_dir,
        per_student_folders=False,
        filename_template="Abgabe",  # no placeholder distinguishing the two students
    )

    assert result is None
    assert not output_dir.exists() or list(output_dir.iterdir()) == []


def test_export_batch_mid_write_failure_leaves_source_untouched_and_no_broken_file(tmp_path: Path, monkeypatch) -> None:
    controller, exam, folder = _setup(tmp_path, monkeypatch)
    scores = _default_scores(controller, exam)
    output_dir = tmp_path / "export"
    source_bytes_before = (folder / "Bob.pdf").read_bytes()

    real_write = pdf_writer_module.write_pdf_copy_atomically
    call_count = {"n": 0}

    def _flaky_write(source_path, destination_path, mutate=None):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("simulated failure")
        return real_write(source_path, destination_path, mutate=mutate)

    monkeypatch.setattr(batch_export_module, "write_pdf_copy_atomically", _flaky_write)

    result = controller.export_students_batch(
        exam=exam,
        student_ids=["alice", "bob"],
        scores=scores,
        sections=_ALL_SECTIONS,
        chart_type="Spinnennetz",
        chart_scope="Pro Aufgabe",
        output_dir=output_dir,
        per_student_folders=False,
        filename_template="{Name}",
    )

    assert result is not None
    exported, failed = result
    assert exported == ["Alice"]
    assert len(failed) == 1
    assert "Bob" in failed[0]
    assert not (output_dir / "Bob.pdf").exists()
    assert not (output_dir / "Bob.korrektor.tmp.pdf").exists()
    assert (folder / "Bob.pdf").read_bytes() == source_bytes_before


def test_export_batch_replaces_existing_marked_stats_page_instead_of_duplicating(tmp_path: Path, monkeypatch) -> None:
    controller, exam, folder = _setup(tmp_path, monkeypatch, student_names=("Alice",))
    scores = _default_scores(controller, exam)
    source_path = folder / "Alice.pdf"
    pdf_writer_module.append_marked_stats_page(source_path, _one_page_pdf_bytes(), replace_existing=False)
    exam.students[0].stats_report_appended = True
    controller._deps.exam_repository.save_exam(exam)
    assert _page_count(source_path) == 2
    output_dir = tmp_path / "export"

    result = controller.export_students_batch(
        exam=exam,
        student_ids=["alice"],
        scores=scores,
        sections=_ALL_SECTIONS,
        chart_type="Spinnennetz",
        chart_scope="Pro Aufgabe",
        output_dir=output_dir,
        per_student_folders=False,
        filename_template="{Name}",
    )

    assert result is not None
    exported, failed = result
    assert exported == ["Alice"]
    assert failed == []
    destination = output_dir / "Alice.pdf"
    assert _page_count(destination) == 2  # replaced, not accumulated
    assert pdf_writer_module.read_trailing_page_marker(destination) == pdf_writer_module.KORREKTOR_STATS_PAGE_MARKER


def test_export_batch_flags_inconsistent_state_as_per_student_failure_not_whole_batch(tmp_path: Path, monkeypatch) -> None:
    controller, exam, folder = _setup(tmp_path, monkeypatch)
    scores = _default_scores(controller, exam)
    alice = next(s for s in exam.students if s.student_id == "alice")
    alice.stats_report_appended = True  # no marker was ever actually written to Alice.pdf
    controller._deps.exam_repository.save_exam(exam)
    output_dir = tmp_path / "export"

    result = controller.export_students_batch(
        exam=exam,
        student_ids=["alice", "bob"],
        scores=scores,
        sections=_ALL_SECTIONS,
        chart_type="Spinnennetz",
        chart_scope="Pro Aufgabe",
        output_dir=output_dir,
        per_student_folders=False,
        filename_template="{Name}",
    )

    assert result is not None
    exported, failed = result
    assert exported == ["Bob"]
    assert len(failed) == 1
    assert "Alice" in failed[0]
    assert not (output_dir / "Alice.pdf").exists()
    assert _page_count(folder / "Alice.pdf") == 1  # source untouched


def _one_page_pdf_bytes(text: str = "stats") -> bytes:
    document = fitz.open()
    page = document.new_page(width=200, height=300)
    page.insert_text((20, 20), text)
    data = document.tobytes()
    document.close()
    return data
