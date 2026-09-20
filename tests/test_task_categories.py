from pathlib import Path

import pytest

from app.adapters.bootstrap.wiring import build_gui_dependencies
from app.adapters.gui.ui_intent_controller import UiIntentController
from app.core.domain.models import ExamProject, RegionAssignment, RegionBox, StudentExam, TaskCategory, TaskDefinition, utc_now_iso


def test_task_category_to_dict_from_dict_roundtrip() -> None:
    category = TaskCategory(category_id="cat-1", name="Geometrie")
    restored = TaskCategory.from_dict(category.to_dict())
    assert restored == category


def test_exam_project_roundtrip_preserves_categories_and_assignments() -> None:
    now = utc_now_iso()
    exam = ExamProject(
        exam_id="exam-1",
        exam_name="Mathe",
        folder_path="/exams/mathe",
        created_at=now,
        updated_at=now,
        standard_page_count=1,
        task_categories=[TaskCategory(category_id="cat-1", name="Geometrie"), TaskCategory(category_id="cat-2", name="Algebra")],
        task_category_assignments={"1A": "cat-1", "1B": "cat-2"},
    )

    restored = ExamProject.from_dict(exam.to_dict())

    assert [c.category_id for c in restored.task_categories] == ["cat-1", "cat-2"]
    assert restored.task_category_assignments == {"1A": "cat-1", "1B": "cat-2"}


def test_exam_project_from_dict_drops_assignment_to_unknown_category() -> None:
    now = utc_now_iso()
    raw = {
        "exam_id": "exam-1",
        "exam_name": "Mathe",
        "folder_path": "/exams/mathe",
        "created_at": now,
        "updated_at": now,
        "standard_page_count": 1,
        "extra_page_assignments": [],
        "task_categories": [{"category_id": "cat-1", "name": "Geometrie"}],
        "task_category_assignments": {"1A": "cat-1", "1B": "cat-missing"},
    }

    restored = ExamProject.from_dict(raw)

    assert restored.task_category_assignments == {"1A": "cat-1"}


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
        students=[StudentExam(student_id="alice", display_name="Alice", pdf_filename="Alice.pdf", page_count=1)],
        regions=[
            RegionAssignment(
                region_id="r-a",
                student_pdf="",
                page_number=1,
                box=RegionBox(0, 0, 100, 100),
                tasks=[TaskDefinition(code="1A", name="1A", max_points=5.0), TaskDefinition(code="1B", name="1B", max_points=3.0)],
                assigned_area_codes=["A"],
                is_read_complete=True,
            ),
        ],
    )
    controller._deps.exam_repository.save_exam(exam)
    return controller, exam


def _reload(controller: UiIntentController) -> ExamProject:
    return controller._deps.exam_repository.load_exam(controller._deps.exam_repository.index_root / "exam-1.json")


def test_save_task_category_immediate_creates_new_category(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)

    updated = controller.save_task_category_immediate(exam=exam, category_id=None, name="Geometrie")

    assert updated is not None
    assert len(updated.task_categories) == 1
    assert updated.task_categories[0].name == "Geometrie"


def test_save_task_category_immediate_renames_existing_by_id(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)
    created = controller.save_task_category_immediate(exam=exam, category_id=None, name="Geometrie")
    category_id = created.task_categories[0].category_id

    renamed = controller.save_task_category_immediate(exam=created, category_id=category_id, name="Geometrie (neu)")

    assert renamed is not None
    assert len(renamed.task_categories) == 1
    assert renamed.task_categories[0].category_id == category_id
    assert renamed.task_categories[0].name == "Geometrie (neu)"


def test_assign_task_to_category_immediate_is_single_valued(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)
    created = controller.save_task_category_immediate(exam=exam, category_id=None, name="Geometrie")
    other = controller.save_task_category_immediate(exam=created, category_id=None, name="Algebra")
    geometrie_id = other.task_categories[0].category_id
    algebra_id = other.task_categories[1].category_id

    step1 = controller.assign_task_to_category_immediate(exam=other, task_code="1A", category_id=geometrie_id)
    assert step1.task_category_assignments == {"1A": geometrie_id}

    step2 = controller.assign_task_to_category_immediate(exam=step1, task_code="1A", category_id=algebra_id)
    assert step2.task_category_assignments == {"1A": algebra_id}


def test_assign_task_to_category_immediate_unassigns_with_none(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)
    created = controller.save_task_category_immediate(exam=exam, category_id=None, name="Geometrie")
    category_id = created.task_categories[0].category_id
    assigned = controller.assign_task_to_category_immediate(exam=created, task_code="1A", category_id=category_id)

    unassigned = controller.assign_task_to_category_immediate(exam=assigned, task_code="1A", category_id=None)

    assert unassigned.task_category_assignments == {}


def test_delete_task_category_immediate_unassigns_its_tasks(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)
    created = controller.save_task_category_immediate(exam=exam, category_id=None, name="Geometrie")
    category_id = created.task_categories[0].category_id
    assigned = controller.assign_task_to_category_immediate(exam=created, task_code="1A", category_id=category_id)

    deleted = controller.delete_task_category_immediate(exam=assigned, category_id=category_id)

    assert deleted is not None
    assert deleted.task_categories == []
    assert deleted.task_category_assignments == {}


def test_reorder_task_categories_immediate(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)
    step1 = controller.save_task_category_immediate(exam=exam, category_id=None, name="Geometrie")
    step2 = controller.save_task_category_immediate(exam=step1, category_id=None, name="Algebra")
    ids = [c.category_id for c in step2.task_categories]

    reordered = controller.reorder_task_categories_immediate(exam=step2, ordered_category_ids=list(reversed(ids)))

    assert reordered is not None
    assert [c.category_id for c in reordered.task_categories] == list(reversed(ids))


def test_task_category_mutations_are_each_undoable(tmp_path: Path) -> None:
    controller, exam = _setup(tmp_path)
    controller.save_task_category_immediate(exam=exam, category_id=None, name="Geometrie")
    assert len(_reload(controller).task_categories) == 1

    assert controller.undo() is True
    assert len(_reload(controller).task_categories) == 0

    assert controller.redo() is True
    assert len(_reload(controller).task_categories) == 1
