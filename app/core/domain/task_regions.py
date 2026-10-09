"""Tasks and the regions that hold them (schema v2, pure functions).

Binding rules (see ARCHITEKTUR "Aufgaben und Bereiche"):

- `ExamProject.tasks` is the only source of task codes and points; regions
  reference codes via ``task_codes``. A task may sit in any number of
  regions (Superseiten and Einzelseiten).
- A Superseiten-Bereich may only lie on a page that **every** student has
  (``page_number <= shared_page_limit``); checked when a region is created
  or changed and before the Scan-Werkstatt applies edits. Existing data that
  violates it is reported, never fatal (`superseiten_page_violations`).
- Consistency cleanup after a region change (`cleanup_after_region_change`):
  marks whose region is gone, or whose non-empty ``task_code`` is no longer
  in their region, are removed; "Fertig" entries of tasks that no longer
  exist are removed. Marks with an empty ``region_id`` (legacy, resolved by
  position) and marks with an empty ``task_code`` (Supersymbol, grade
  superposition) are kept. Comments and CSV scores are never touched.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.domain.models import ExamProject, RegionAssignment, TaskDefinition
from app.core.domain.task_spec import TaskSpec, task_sort_key


def task_by_code(exam: ExamProject) -> dict[str, TaskDefinition]:
    """``{CODE: TaskDefinition}`` of the exam's tasks."""
    return {task.code: task for task in exam.tasks}


def tasks_of_region(exam: ExamProject, region: RegionAssignment) -> list[TaskDefinition]:
    """The region's tasks in natural order (unknown codes skipped)."""
    lookup = task_by_code(exam)
    return [lookup[code] for code in sorted(region.task_codes, key=task_sort_key) if code in lookup]


def superseiten_regions(exam: ExamProject) -> list[RegionAssignment]:
    """Regions shared by all students (Zuschnitt Schritt 1)."""
    return [region for region in exam.regions if not region.student_pdf]


def single_page_regions(exam: ExamProject, pdf_filename: str | None = None) -> list[RegionAssignment]:
    """Einzelseiten-Bereiche, optionally only those of one student's PDF."""
    return [region for region in exam.regions if region.student_pdf and (pdf_filename is None or region.student_pdf == pdf_filename)]


def regions_for_task(exam: ExamProject, code: str, pdf_filename: str, page_count: int | None = None) -> list[RegionAssignment]:
    """All regions of task ``code`` for one student: Superseiten + that student's Einzelseiten, by page and top edge.

    Superseiten regions on pages the student does not have (``page_count``)
    are skipped defensively (legacy data violating the shared-page rule).
    """
    code = code.strip().upper()
    found = [
        region
        for region in exam.regions
        if code in region.task_codes
        and (region.student_pdf == pdf_filename or (not region.student_pdf and (page_count is None or region.page_number <= page_count)))
    ]
    return sorted(found, key=lambda region: (region.page_number, region.box.y0, region.box.x0, region.region_id))


def shared_page_limit(exam: ExamProject) -> int:
    """Highest page number every student has (0 without students)."""
    return min((student.page_count for student in exam.students), default=0)


def superseiten_page_violations(exam: ExamProject) -> list[str]:
    """German descriptions of Superseiten-Bereiche on pages some student does not have."""
    problems = []
    for region in superseiten_regions(exam):
        missing = [student.display_name for student in exam.students if student.page_count < region.page_number]
        if missing:
            label = region.assigned_area_codes[0] if region.assigned_area_codes else region.region_id
            problems.append(f"Bereich {label} liegt auf Seite {region.page_number}, die {', '.join(missing)} nicht hat")
    return problems


def next_free_label(used: set[str]) -> str:
    """Next display label A, B, ..., Z, AA, AB, ... not in ``used`` (upper case)."""
    index = 0
    while True:
        label, value = "", index
        while True:
            value, remainder = divmod(value, 26)
            label = chr(ord("A") + remainder) + label
            if value == 0:
                break
            value -= 1
        if label not in used:
            return label
        index += 1


def sort_tasks(exam: ExamProject) -> None:
    """Keep ``exam.tasks`` in natural code order (in place)."""
    exam.tasks.sort(key=lambda task: task_sort_key(task.code))


def prune_orphan_tasks(exam: ExamProject) -> list[str]:
    """Remove tasks no region references any more (in place); return their codes."""
    referenced = {code for region in exam.regions for code in region.task_codes}
    removed = [task.code for task in exam.tasks if task.code not in referenced]
    exam.tasks = [task for task in exam.tasks if task.code in referenced]
    return removed


@dataclass(frozen=True)
class TaskChangePlan:
    """What saving a task input would do to `ExamProject.tasks`.

    ``new``: codes to create with points; ``changed``: ``(code, old, new)``
    points of existing tasks; ``unknown``: codes without points that do not
    exist yet (an error - points are needed to create a task).
    """

    new: tuple[tuple[str, float], ...]
    changed: tuple[tuple[str, float, float], ...]
    unknown: tuple[str, ...]


def plan_task_changes(exam: ExamProject, specs: list[TaskSpec]) -> TaskChangePlan:
    """Compare a parsed task input against the exam's tasks (nothing is changed)."""
    lookup = task_by_code(exam)
    new, changed, unknown = [], [], []
    for spec in specs:
        existing = lookup.get(spec.code)
        if existing is None and spec.points is None:
            unknown.append(spec.code)
        elif existing is None:
            new.append((spec.code, float(spec.points)))
        elif spec.points is not None and abs(existing.max_points - spec.points) > 1e-9:
            changed.append((spec.code, existing.max_points, float(spec.points)))
    return TaskChangePlan(tuple(new), tuple(changed), tuple(unknown))


def cleanup_after_region_change(exam: ExamProject) -> list[str]:
    """Remove marks and "Fertig" entries that a region/task change made invalid (in place); describe them."""
    regions = {region.region_id: region for region in exam.regions}
    names = {student.pdf_filename: student.display_name for student in exam.students}
    removed: list[str] = []
    kept = []
    for mark in exam.pdf_annotations:
        region = regions.get(mark.region_id) if mark.region_id else None
        invalid = bool(mark.region_id) and (region is None or (mark.task_code and mark.task_code not in region.task_codes))
        if invalid:
            removed.append(f"Symbol „{mark.content}“ bei {names.get(mark.student_pdf, mark.student_pdf)} (Seite {mark.page_number})")
        else:
            kept.append(mark)
    exam.pdf_annotations = kept
    codes = {task.code for task in exam.tasks}
    exam.person_task_completions = [item for item in exam.person_task_completions if item.task_code in codes]
    return removed


def annotation_problems(exam: ExamProject) -> list[str]:
    """Marks violating the reference invariants (for reports and tests; empty after a cleanup)."""
    probe = ExamProject.from_dict(exam.to_dict())
    return cleanup_after_region_change(probe)
