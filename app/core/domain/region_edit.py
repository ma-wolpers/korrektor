"""Create/change/delete a region with its tasks - pure, on a copy of the exam.

One authoritative path for every region edit (Superseiten and Einzelseiten):

1. Copy the exam (the caller's object is never mutated, so a rejected edit
   leaves the state unchanged).
2. Tasks: codes with points create the task or set its points (the caller
   has already confirmed point changes and checked scored tasks); codes
   without points must exist (`plan_task_changes` reports them as unknown).
3. Region: replaced by ``region_id`` or appended with the next free label.
4. Tasks no region references any more are removed (`prune_orphan_tasks`);
   tasks are kept in natural order.
5. Marks and "Fertig" entries made invalid are removed
   (`cleanup_after_region_change`) and described, so the caller can ask.
6. `validate_regions` - an `ExamStructureError` means "reject the edit".

The caller saves ``result.exam`` as one history action (full payload
snapshot before/after), so the cleanup is undone together with the edit.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from app.core.domain.models import ExamProject, RegionAssignment, RegionBox, TaskDefinition
from app.core.domain.task_regions import (
    cleanup_after_region_change,
    next_free_label,
    prune_orphan_tasks,
    shared_page_limit,
    sort_tasks,
)
from app.core.domain.task_spec import TaskSpec
from app.core.domain.validation import validate_regions


@dataclass(frozen=True)
class RegionEditResult:
    """The edited exam copy, the region it is about, and what the edit removed."""

    exam: ExamProject
    region_id: str
    removed_marks: tuple[str, ...]
    pruned_tasks: tuple[str, ...]


def region_placement_error(exam: ExamProject, student_pdf: str, page_number: int) -> str | None:
    """German reason why a region may not lie on ``page_number`` (rule A4), or ``None``."""
    if student_pdf:
        student = next((item for item in exam.students if item.pdf_filename == student_pdf), None)
        if student is None:
            return f"Unbekannte PDF: {student_pdf}"
        if not 1 <= page_number <= student.page_count:
            return f"{student.display_name} hat keine Seite {page_number}."
        return None
    limit = shared_page_limit(exam)
    if not 1 <= page_number <= limit:
        return (
            f"Superseiten-Bereiche nur auf Seiten, die alle Personen haben (Seite 1–{limit}). "
            "Für einzelne Personen den Bereich in Schritt 2 (Einzelseiten) markieren."
        )
    return None


def apply_region_upsert(
    exam: ExamProject,
    *,
    region_id: str | None,
    student_pdf: str,
    page_number: int,
    box: tuple[float, float, float, float],
    specs: list[TaskSpec],
    label: str | None = None,
) -> RegionEditResult:
    """Steps 1-6 for creating or changing one region; raises `ExamStructureError` if the result is invalid."""
    result = ExamProject.from_dict(exam.to_dict())
    lookup = {task.code: task for task in result.tasks}
    for spec in specs:
        if spec.points is None:
            continue
        if spec.code in lookup:
            lookup[spec.code].max_points = float(spec.points)
        else:
            task = TaskDefinition(code=spec.code, name=spec.code, max_points=float(spec.points))
            result.tasks.append(task)
            lookup[spec.code] = task
    codes = [spec.code for spec in specs]
    existing = next((region for region in result.regions if region.region_id == region_id), None) if region_id else None
    region_box = RegionBox(x0=box[0], y0=box[1], x1=box[2], y1=box[3])
    if existing is not None:
        existing.student_pdf, existing.page_number, existing.box, existing.task_codes = student_pdf, page_number, region_box, codes
        target_id = existing.region_id
    else:
        used = {region.assigned_area_codes[0].strip().upper() for region in result.regions if region.assigned_area_codes}
        chosen = label.strip().upper() if label and label.strip().upper() not in used else next_free_label(used)
        target_id = region_id or f"r-{uuid4().hex[:12]}"
        result.regions.append(
            RegionAssignment(
                region_id=target_id,
                student_pdf=student_pdf,
                page_number=page_number,
                box=region_box,
                task_codes=codes,
                assigned_area_codes=[chosen],
                is_read_complete=True,
            )
        )
    return _finish(result, target_id)


def apply_region_delete(exam: ExamProject, region_id: str) -> RegionEditResult:
    """Steps 1 and 4-6 for deleting one region."""
    result = ExamProject.from_dict(exam.to_dict())
    result.regions = [region for region in result.regions if region.region_id != region_id]
    return _finish(result, region_id)


def _finish(result: ExamProject, region_id: str) -> RegionEditResult:
    """Steps 4-6 on the edited copy: prune orphan tasks, sort, clean up marks/completions, validate."""
    pruned = prune_orphan_tasks(result)
    sort_tasks(result)
    removed = cleanup_after_region_change(result)
    validate_regions(result)
    return RegionEditResult(exam=result, region_id=region_id, removed_marks=tuple(removed), pruned_tasks=tuple(pruned))
