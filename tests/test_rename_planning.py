from app.core.domain.models import StudentExam
from app.core.domain.rename_planning import (
    find_external_conflicts,
    plan_target_filenames,
    validate_rename_set,
)


def _student(student_id: str, pdf_filename: str, display_name: str | None = None) -> StudentExam:
    return StudentExam(
        student_id=student_id,
        display_name=display_name or student_id,
        pdf_filename=pdf_filename,
        page_count=1,
    )


def test_validate_rename_set_accepts_exact_bijection() -> None:
    students = [_student("alice", "Alice.pdf"), _student("bob", "Bob.pdf")]
    errors = validate_rename_set(students, {"Alice.pdf", "Bob.pdf"})
    assert errors == []


def test_validate_rename_set_rejects_duplicate_pdf_filename_reference() -> None:
    # Two students referencing the same physical file - a pure set comparison
    # of {folder files} vs {referenced files} would miss this.
    students = [_student("alice", "A.pdf", "Anna"), _student("bob", "A.pdf", "Bob")]
    errors = validate_rename_set(students, {"A.pdf"})
    assert any("Doppelte pdf_filename-Referenz" in error and "A.pdf" in error for error in errors)


def test_validate_rename_set_rejects_missing_referenced_file() -> None:
    students = [_student("alice", "Alice.pdf")]
    errors = validate_rename_set(students, set())
    assert any("Referenzierte Datei fehlt" in error for error in errors)


def test_validate_rename_set_rejects_unassigned_extra_pdf() -> None:
    students = [_student("alice", "Alice.pdf")]
    errors = validate_rename_set(students, {"Alice.pdf", "Leftover.pdf"})
    assert any("Zusaetzliche PDF ohne Zuordnung" in error and "Leftover.pdf" in error for error in errors)


def test_validate_rename_set_rejects_empty_pdf_filename() -> None:
    students = [_student("alice", "")]
    errors = validate_rename_set(students, set())
    assert any("Leeres pdf_filename" in error for error in errors)


def test_plan_target_filenames_resolves_internal_collision_with_suffix() -> None:
    students = [_student("alice", "Alice.pdf"), _student("bob", "Bob.pdf")]
    plan = plan_target_filenames(students, {"alice": "Max Mustermann", "bob": "Max Mustermann"})

    assert plan.errors == []
    assert plan.target_filename_by_student_id["alice"] == "Max_Mustermann.pdf"
    assert plan.target_filename_by_student_id["bob"] == "Max_Mustermann_2.pdf"


def test_plan_target_filenames_handles_a_b_swap_without_reporting_a_collision() -> None:
    students = [_student("alice", "A.pdf"), _student("bob", "B.pdf")]
    plan = plan_target_filenames(students, {"alice": "B", "bob": "A"})

    assert plan.errors == []
    assert plan.target_filename_by_student_id == {"alice": "B.pdf", "bob": "A.pdf"}


def test_plan_target_filenames_reports_missing_name() -> None:
    students = [_student("alice", "Alice.pdf")]
    plan = plan_target_filenames(students, {})

    assert plan.target_filename_by_student_id == {}
    assert any("Kein Name eingegeben" in error for error in plan.errors)


def test_plan_target_filenames_reports_name_invalid_after_sanitizing() -> None:
    students = [_student("alice", "Alice.pdf")]
    plan = plan_target_filenames(students, {"alice": '???"""'})

    assert plan.target_filename_by_student_id == {}
    assert any("Ungueltiger Name" in error for error in plan.errors)


def test_find_external_conflicts_ignores_targets_within_the_rename_set() -> None:
    conflicts = find_external_conflicts(
        target_filename_by_student_id={"alice": "B.pdf", "bob": "A.pdf"},
        actual_pdf_filenames={"A.pdf", "B.pdf"},
        rename_set_filenames={"A.pdf", "B.pdf"},
    )
    assert conflicts == []


def test_find_external_conflicts_reports_collision_outside_the_rename_set() -> None:
    conflicts = find_external_conflicts(
        target_filename_by_student_id={"alice": "Leftover.pdf"},
        actual_pdf_filenames={"Alice.pdf", "Leftover.pdf"},
        rename_set_filenames={"Alice.pdf"},
    )
    assert len(conflicts) == 1
    assert "Leftover.pdf" in conflicts[0]
