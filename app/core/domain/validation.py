from __future__ import annotations

from app.core.domain.models import ExamProject


class ExamStructureError(Exception):
    """A loaded `ExamProject` violates a structural identity invariant.

    Distinct from the forward-only-schema rejection raised by
    `ExamProject.from_dict` (a `ValueError` for missing/unsupported fields):
    this covers exams that parse successfully but contain duplicate or
    empty identifiers that would make region lookups ambiguous (silently
    dropping regions in Korrekturmodus, or misattributing scores/annotations).
    Raised by `validate_regions`, which callers run after `from_dict`.
    """


def validate_regions(exam: ExamProject) -> None:
    """Enforce the region identity invariants Korrekturmodus depends on.

    Checks, in order, that every region has a non-empty `region_id`, that no
    two regions share a `region_id`, that no two regions share a primary
    `assigned_area_codes[0]` label, and that no `TaskDefinition.code` is used
    by more than one region (required because `korrektor_scores.csv` keys
    columns by `task_code` alone, exam-wide). Raises `ExamStructureError`
    naming the exam and the conflicting identifiers on the first violated
    invariant found.
    """
    empty_region_ids = sum(1 for region in exam.regions if not region.region_id.strip())
    if empty_region_ids:
        raise ExamStructureError(
            f"Klausur '{exam.exam_name}' ({exam.exam_id}): {empty_region_ids} Region(en) ohne region_id."
        )

    region_id_counts: dict[str, int] = {}
    for region in exam.regions:
        region_id_counts[region.region_id] = region_id_counts.get(region.region_id, 0) + 1
    duplicate_region_ids = sorted(region_id for region_id, count in region_id_counts.items() if count > 1)
    if duplicate_region_ids:
        raise ExamStructureError(
            f"Klausur '{exam.exam_name}' ({exam.exam_id}): doppelte region_id(s): {', '.join(duplicate_region_ids)}."
        )

    label_counts: dict[str, int] = {}
    for region in exam.regions:
        if not region.assigned_area_codes:
            continue
        label = region.assigned_area_codes[0].strip().upper()
        if not label:
            continue
        label_counts[label] = label_counts.get(label, 0) + 1
    duplicate_labels = sorted(label for label, count in label_counts.items() if count > 1)
    if duplicate_labels:
        raise ExamStructureError(
            f"Klausur '{exam.exam_name}' ({exam.exam_id}): mehrere Bereiche mit demselben Bereichs-Label: "
            f"{', '.join(duplicate_labels)}."
        )

    task_code_counts: dict[str, int] = {}
    for region in exam.regions:
        for task in region.tasks:
            code = task.code.strip().upper()
            if not code:
                continue
            task_code_counts[code] = task_code_counts.get(code, 0) + 1
    duplicate_task_codes = sorted(code for code, count in task_code_counts.items() if count > 1)
    if duplicate_task_codes:
        raise ExamStructureError(
            f"Klausur '{exam.exam_name}' ({exam.exam_id}): Aufgaben-Code(s) in mehreren Bereichen vergeben "
            f"(muss klausurweit eindeutig sein): {', '.join(duplicate_task_codes)}."
        )
