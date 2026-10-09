from __future__ import annotations

from app.core.domain.models import ExamProject


class ExamConflictError(Exception):
    """Raised by `ExamRepository.save_exam` when the on-disk file changed since `exam` was loaded.

    Protects against silently losing edits made elsewhere (e.g. the same
    Exam-Indexordner opened on a second computer via cloud sync, or a second
    process) between this `exam`'s load/last save and now: without this
    check, `save_exam` would just overwrite the newer on-disk version with
    this stale in-memory one, discarding the other change with no warning.
    Callers show `str(exc)` to the user and must not retry the same write -
    the exam has to be reloaded first to pick up the newer version.
    """


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
    """Enforce the region/task invariants of schema v2 (on load and before every region save).

    In order: every region has a non-empty, unique ``region_id`` and a unique
    display label; every Einzelseiten-Bereich belongs to a known student PDF;
    every region has at least one task code, none twice, each defined in
    ``exam.tasks``; task codes in ``exam.tasks`` are non-empty and unique
    (``korrektor_scores.csv`` keys columns by code alone); every task is
    referenced by at least one region. Raises `ExamStructureError` naming
    the exam and the first violated invariant. Not checked here (reported,
    never fatal for existing data): the shared-page rule for Superseiten
    and the mark references (see `task_regions`).
    """
    prefix = f"Klausur '{exam.exam_name}' ({exam.exam_id})"
    empty_region_ids = sum(1 for region in exam.regions if not region.region_id.strip())
    if empty_region_ids:
        raise ExamStructureError(f"{prefix}: {empty_region_ids} Region(en) ohne region_id.")
    _reject_duplicates(prefix, "doppelte region_id(s)", [region.region_id for region in exam.regions])
    labels = [region.assigned_area_codes[0].strip().upper() for region in exam.regions if region.assigned_area_codes and region.assigned_area_codes[0].strip()]
    _reject_duplicates(prefix, "mehrere Bereiche mit demselben Bereichs-Label", labels)

    known_pdfs = {student.pdf_filename for student in exam.students}
    foreign = sorted({region.student_pdf for region in exam.regions if region.student_pdf and region.student_pdf not in known_pdfs})
    if foreign:
        raise ExamStructureError(f"{prefix}: Einzelseiten-Bereich(e) zu unbekannter PDF: {', '.join(foreign)}.")

    task_codes = [task.code.strip().upper() for task in exam.tasks]
    if any(not code for code in task_codes):
        raise ExamStructureError(f"{prefix}: Aufgabe ohne Code.")
    _reject_duplicates(prefix, "Aufgaben-Code(s) mehrfach definiert", task_codes)
    defined = set(task_codes)
    for region in exam.regions:
        label = region.assigned_area_codes[0] if region.assigned_area_codes else region.region_id
        if not region.task_codes:
            raise ExamStructureError(f"{prefix}: Bereich {label} hat keine Aufgabe.")
        _reject_duplicates(prefix, f"Bereich {label} nennt Aufgabe(n) mehrfach", region.task_codes)
        undefined = sorted(set(region.task_codes) - defined)
        if undefined:
            raise ExamStructureError(f"{prefix}: Bereich {label} verweist auf unbekannte Aufgabe(n): {', '.join(undefined)}.")
    referenced = {code for region in exam.regions for code in region.task_codes}
    orphans = sorted(defined - referenced)
    if orphans:
        raise ExamStructureError(f"{prefix}: Aufgabe(n) ohne Bereich: {', '.join(orphans)}.")


def _reject_duplicates(prefix: str, what: str, values: list[str]) -> None:
    """Raise `ExamStructureError` if ``values`` contains duplicates."""
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    duplicates = sorted(value for value, count in counts.items() if count > 1)
    if duplicates:
        raise ExamStructureError(f"{prefix}: {what}: {', '.join(duplicates)}.")
