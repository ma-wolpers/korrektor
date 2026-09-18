from __future__ import annotations

from dataclasses import dataclass, field

from app.core.domain.models import StudentExam
from app.infrastructure.repositories.file_utils import build_pdf_filename_from_name


def validate_rename_set(students: list[StudentExam], actual_pdf_filenames: set[str]) -> list[str]:
    """Check the 1:1 invariant a batch rename requires before touching any file.

    Every student must have a non-empty, unique `pdf_filename`; every
    referenced file must exist in the folder; and every `.pdf` file in the
    folder must belong to exactly one student. A plain set-equality check
    would miss a duplicate reference (two students pointing at the same
    file) as long as the file counts happened to match, so this checks the
    stronger, explicit 1:1 mapping instead. Returns a list of human-readable
    problems (empty means the rename set is valid); the caller must abort
    the whole rename and touch no file if this is non-empty.
    """
    errors: list[str] = []
    owners_by_filename: dict[str, list[str]] = {}
    for student in students:
        filename = student.pdf_filename.strip()
        label = student.display_name.strip() or student.student_id
        if not filename:
            errors.append(f"Leeres pdf_filename: {label}.")
            continue
        owners_by_filename.setdefault(filename, []).append(label)

    for filename, owners in owners_by_filename.items():
        if len(owners) > 1:
            errors.append(f"Doppelte pdf_filename-Referenz: {filename} ({', '.join(owners)}).")

    referenced = set(owners_by_filename.keys())
    for filename in sorted(referenced - actual_pdf_filenames):
        owners = ", ".join(owners_by_filename[filename])
        errors.append(f"Referenzierte Datei fehlt: {filename} ({owners}).")

    for filename in sorted(actual_pdf_filenames - referenced):
        errors.append(f"Zusaetzliche PDF ohne Zuordnung: {filename}.")

    return errors


@dataclass(slots=True)
class RenamePlan:
    """Result of resolving pending names to unique target filenames.

    `errors` is non-empty only when a name failed to normalize into any
    valid filename (`build_pdf_filename_from_name` returned `None`) or was
    missing outright; in that case `target_filename_by_student_id` is empty
    and the caller must not proceed. Internal collisions (two students
    landing on the same target) are already resolved here with `_2`, `_3`,
    ... suffixes — that is not an error, since all names in this batch
    belong to the same closed rename set (see `validate_rename_set`).
    """

    target_filename_by_student_id: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def plan_target_filenames(students: list[StudentExam], name_by_student_id: dict[str, str]) -> RenamePlan:
    """Resolve one target filename per student from their pending entered name.

    Every student must have a pending name in `name_by_student_id` (checked
    by the caller before invoking a rename; this function still reports a
    missing/invalid one as an error rather than assuming). Order of
    `students` decides which student keeps an unsuffixed name on collision.
    """
    errors: list[str] = []
    raw_targets: dict[str, str] = {}
    for student in students:
        name = name_by_student_id.get(student.student_id, "").strip()
        label = student.display_name.strip() or student.student_id
        if not name:
            errors.append(f"Kein Name eingegeben fuer {label}.")
            continue
        target = build_pdf_filename_from_name(name)
        if target is None:
            errors.append(f"Ungueltiger Name (nach Bereinigung leer): '{name}' fuer {label}.")
            continue
        raw_targets[student.student_id] = target

    if errors:
        return RenamePlan(errors=errors)

    resolved: dict[str, str] = {}
    used: set[str] = set()
    for student in students:
        target = raw_targets[student.student_id]
        if target not in used:
            resolved[student.student_id] = target
            used.add(target)
            continue
        stem, _, ext = target.rpartition(".")
        suffix = 2
        candidate = f"{stem}_{suffix}.{ext}"
        while candidate in used:
            suffix += 1
            candidate = f"{stem}_{suffix}.{ext}"
        resolved[student.student_id] = candidate
        used.add(candidate)

    return RenamePlan(target_filename_by_student_id=resolved)


def find_external_conflicts(
    target_filename_by_student_id: dict[str, str],
    actual_pdf_filenames: set[str],
    rename_set_filenames: set[str],
) -> list[str]:
    """Report target filenames that collide with a file outside the rename set.

    A target matching a file that already belongs to a student in the same
    rename set is not a conflict (the staged rename in
    `UiIntentController.rename_students_immediate` handles that, including
    A<->B swaps); only a match against a file the rename set does not own is.
    """
    outside = actual_pdf_filenames - rename_set_filenames
    conflicting = sorted(set(target_filename_by_student_id.values()) & outside)
    return [f"Zielname kollidiert mit vorhandener Datei ausserhalb der Umbenennung: {name}" for name in conflicting]
