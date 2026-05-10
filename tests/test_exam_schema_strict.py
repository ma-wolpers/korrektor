import pytest

from app.core.domain.models import ExamProject


def _base_raw_exam() -> dict[str, object]:
    return {
        "exam_id": "exam-1",
        "exam_name": "Mathe",
        "folder_path": "A:/tmp/exam",
        "created_at": "2025-01-01T00:00:00.000000Z",
        "updated_at": "2025-01-01T00:00:00.000000Z",
        "standard_page_count": 2,
        "students": [
            {
                "student_id": "alice",
                "display_name": "Alice",
                "pdf_filename": "Alice.pdf",
                "page_count": 3,
                "extra_pages": [3],
            }
        ],
        "regions": [
            {
                "region_id": "tpl-1",
                "student_pdf": "",
                "page_number": 1,
                "box": {"x0": 10, "y0": 20, "x1": 120, "y1": 180},
                "tasks": [
                    {"code": "A1", "name": "Aufgabe 1", "max_points": 4.0},
                ],
                "assigned_area_codes": ["A"],
                "is_read_complete": True,
                "is_corrected": False,
                "is_extra_page": False,
            }
        ],
        "extra_page_assignments": [
            {
                "assignment_id": "ex-1",
                "student_pdf": "Alice.pdf",
                "page_number": 3,
                "box": {"x0": 5, "y0": 5, "x1": 100, "y1": 100},
                "assigned_area_codes": ["A"],
                "is_read_complete": True,
                "is_corrected": False,
            }
        ],
        "is_reading_complete": False,
    }


def test_from_dict_accepts_forward_only_schema() -> None:
    exam = ExamProject.from_dict(_base_raw_exam())

    assert len(exam.regions) == 1
    assert len(exam.extra_page_assignments) == 1


def test_from_dict_rejects_missing_extra_assignment_field() -> None:
    raw = _base_raw_exam()
    raw.pop("extra_page_assignments")

    with pytest.raises(ValueError, match="missing 'extra_page_assignments'"):
        ExamProject.from_dict(raw)


def test_from_dict_rejects_student_bound_standard_template() -> None:
    raw = _base_raw_exam()
    raw["regions"][0]["student_pdf"] = "Alice.pdf"

    with pytest.raises(ValueError, match="must not carry student_pdf"):
        ExamProject.from_dict(raw)


def test_from_dict_rejects_extra_flag_on_standard_template() -> None:
    raw = _base_raw_exam()
    raw["regions"][0]["is_extra_page"] = True

    with pytest.raises(ValueError, match="must not set is_extra_page=true"):
        ExamProject.from_dict(raw)
