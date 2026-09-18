from app.core.domain.annotation_sync import build_annotation_clones
from app.core.domain.models import PdfAnnotation, StudentExam


def _student(student_id: str, pdf_filename: str) -> StudentExam:
    return StudentExam(student_id=student_id, display_name=student_id, pdf_filename=pdf_filename, page_count=1)


def _base_annotation() -> PdfAnnotation:
    return PdfAnnotation(
        annotation_id="ann-original",
        student_pdf="Alice.pdf",
        page_number=1,
        annotation_type="symbol",
        content="✓",
        color_hex="#d62828",
        x=42.0,
        y=17.0,
        task_code="",
        region_id="r-a",
        font_size=20.0,
        rotation_deg=0.0,
    )


def test_build_annotation_clones_one_per_student() -> None:
    students = [_student("bob", "Bob.pdf"), _student("carla", "Carla.pdf")]
    clones = build_annotation_clones(_base_annotation(), students, "sg-123")

    assert len(clones) == 2
    assert {clone.student_pdf for clone in clones} == {"Bob.pdf", "Carla.pdf"}


def test_build_annotation_clones_copies_placement_and_appearance() -> None:
    base = _base_annotation()
    clones = build_annotation_clones(base, [_student("bob", "Bob.pdf")], "sg-123")

    clone = clones[0]
    assert clone.x == base.x
    assert clone.y == base.y
    assert clone.page_number == base.page_number
    assert clone.annotation_type == base.annotation_type
    assert clone.content == base.content
    assert clone.color_hex == base.color_hex
    assert clone.region_id == base.region_id
    assert clone.font_size == base.font_size


def test_build_annotation_clones_share_sync_group_id_with_unique_annotation_ids() -> None:
    students = [_student("bob", "Bob.pdf"), _student("carla", "Carla.pdf")]
    clones = build_annotation_clones(_base_annotation(), students, "sg-123")

    assert all(clone.sync_group_id == "sg-123" for clone in clones)
    assert len({clone.annotation_id for clone in clones}) == len(clones)
    assert all(not clone.position_detached for clone in clones)


def test_build_annotation_clones_does_not_mutate_base() -> None:
    base = _base_annotation()
    build_annotation_clones(base, [_student("bob", "Bob.pdf")], "sg-123")

    assert base.student_pdf == "Alice.pdf"
    assert base.sync_group_id == ""


def test_build_annotation_clones_empty_students_returns_empty_list() -> None:
    assert build_annotation_clones(_base_annotation(), [], "sg-123") == []
