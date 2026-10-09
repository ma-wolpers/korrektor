"""Scan-Werkstatt core: page model (order/rotation/deletion), geometry and PDF output."""

from pathlib import Path

import fitz
import pytest

from app.adapters.gui.scan_workshop_session import PdfEditState, ScanWorkshopSession
from app.core.domain.models import StudentExam
from app.core.domain.page_geometry import PageTransform, normalize_rotation, quarter_turns
from app.infrastructure.pdf.page_editing import PageEdit, render_edited_page, source_transform, write_edited_pdf


def _student(pdf: str, pages: int, *, stats: bool = False) -> StudentExam:
    return StudentExam(student_id=pdf, display_name=pdf, pdf_filename=pdf, page_count=pages, stats_report_appended=stats)


def _pdf(path: Path, pages: int) -> Path:
    document = fitz.open()
    for index in range(pages):
        document.new_page(width=595, height=842).insert_text((100, 100), f"P{index + 1}", fontsize=20)
    document.save(path)
    document.close()
    return path


def _texts(path: Path) -> list[str]:
    document = fitz.open(path)
    try:
        return [page.get_text().strip() for page in document]
    finally:
        document.close()


def _word_center(page, word):
    for x0, y0, x1, y1, text, *_ in page.get_text("words"):
        if text == word:
            return (x0 + x1) / 2, (y0 + y1) / 2
    return None


def test_reorder_only_maps_positions():
    session = ScanWorkshopSession([_student("a.pdf", 3)])
    session.go_page(2)  # position 3 (page 3)
    session.move_page(-1)  # page 3 -> position 2

    state = session.current_state
    assert state.order == [1, 3, 2] and session.position == 2 and session.current_original_page == 3
    assert state.page_mapping() == {1: 1, 2: 3, 3: 2}
    assert session.changed_pdfs() == ["a.pdf"]


def test_reorder_plus_delete_and_rotation_stay_with_the_original_page():
    session = ScanWorkshopSession([_student("a.pdf", 3)])
    session.go_page(2)
    session.rotate_by(2.0)
    session.move_page(-2)  # page 3 now first, still rotated
    session.go_page(2)  # position 3 = page 2
    session.toggle_delete()

    state = session.current_state
    assert state.order == [3, 1, 2]
    assert state.edit_for(3) == PageEdit(rotation_deg=2.0)
    assert state.edit_for(2).deleted
    assert state.page_mapping() == {1: 2, 2: None, 3: 1}
    assert state.kept_order() == [3, 1]


def test_rotation_normalization_and_quarter_turns():
    assert normalize_rotation(270) == -90 and normalize_rotation(-180) == 180 and normalize_rotation(360) == 0
    assert quarter_turns(92) == 1 and quarter_turns(-90) == 3 and quarter_turns(3.5) == 0
    session = ScanWorkshopSession([_student("a.pdf", 1)])
    session.rotate_quarter(1)
    session.rotate_by(-90)
    assert session.current_state.edits == {}  # back to unchanged


def test_locked_student_cannot_be_edited_and_crosshair_persists():
    session = ScanWorkshopSession([_student("a.pdf", 2), _student("b.pdf", 2, stats=True)])
    session.set_crosshair(0.2, 1.4)
    session.go_student(1)

    assert session.is_current_locked()
    assert not session.rotate_by(2) and not session.toggle_delete() and not session.move_page(1)
    assert session.crosshair == (0.2, 1.0)
    session.go_student(-1)
    assert session.crosshair == (0.2, 1.0)


def test_navigation_keeps_position_where_possible():
    session = ScanWorkshopSession([_student("a.pdf", 4), _student("b.pdf", 2)])
    session.go_page(3)
    session.go_student(1)
    assert session.position == 2
    assert not session.go_student(1) and not session.go_page(1)


def test_transform_rotates_clockwise_around_center_and_swaps_size_on_quarter_turns():
    transform = PageTransform(100.0, 200.0, 90.0)
    assert transform.target_size == (200.0, 100.0)
    assert transform.map_point(50.0, 0.0) == pytest.approx((200.0, 50.0))  # top edge -> right edge
    assert PageTransform(100.0, 200.0, 10.0).map_point(50.0, 100.0) == pytest.approx((50.0, 100.0))


def test_written_pdf_follows_order_and_deletion(tmp_path):
    source = _pdf(tmp_path / "a.pdf", 3)
    target = tmp_path / "out.pdf"

    count = write_edited_pdf(source, [3, 1, 2], {2: PageEdit(deleted=True)}, target)

    assert count == 2 and _texts(target) == ["P3", "P1"]


def test_fine_rotation_keeps_size_scale_and_matches_transform(tmp_path):
    source_path = _pdf(tmp_path / "a.pdf", 1)
    target = tmp_path / "out.pdf"
    write_edited_pdf(source_path, [1], {1: PageEdit(rotation_deg=10.0)}, target)

    source = fitz.open(source_path)
    edited = fitz.open(target)
    try:
        expected = source_transform(source, 1, PageEdit(rotation_deg=10.0)).map_point(*_word_center(source[0], "P1"))
        assert edited[0].rect.width == pytest.approx(595) and edited[0].rect.height == pytest.approx(842)
        assert _word_center(edited[0], "P1") == pytest.approx(expected, abs=1.5)
    finally:
        source.close()
        edited.close()


def test_quarter_turn_swaps_page_size_and_preview_equals_result(tmp_path):
    source_path = _pdf(tmp_path / "a.pdf", 1)
    target = tmp_path / "out.pdf"
    write_edited_pdf(source_path, [1], {1: PageEdit(rotation_deg=90.0)}, target)
    source = fitz.open(source_path)
    edited = fitz.open(target)
    try:
        assert (edited[0].rect.width, edited[0].rect.height) == pytest.approx((842, 595))
        preview = render_edited_page(source, 1, PageEdit(rotation_deg=90.0), zoom=0.5)
        result = edited[0].get_pixmap(matrix=fitz.Matrix(0.5, 0.5), alpha=False)
        assert (preview.width, preview.height) == (result.width, result.height)
        assert preview.samples == result.samples
    finally:
        source.close()
        edited.close()


def test_existing_rotate_flag_is_respected_as_visible_orientation(tmp_path):
    path = tmp_path / "rot.pdf"
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    page.insert_text((100, 100), "R", fontsize=20)
    page.set_rotation(90)
    document.save(path)
    document.close()
    source = fitz.open(path)
    try:
        transform = source_transform(source, 1, PageEdit(rotation_deg=2.0))
        assert (transform.source_width, transform.source_height) == pytest.approx((842, 595))
    finally:
        source.close()


def test_deleting_every_page_is_rejected(tmp_path):
    source = _pdf(tmp_path / "a.pdf", 1)
    with pytest.raises(ValueError, match="alle Seiten"):
        write_edited_pdf(source, [1], {1: PageEdit(deleted=True)}, tmp_path / "out.pdf")


def test_fresh_state_is_unchanged():
    assert not PdfEditState.fresh(3).is_changed()


_CM = 72.0 / 2.54


def test_shift_is_applied_after_rotation_in_edited_page_coordinates():
    transform = PageTransform(100.0, 200.0, 90.0, offset_x=10.0, offset_y=-5.0)
    assert transform.target_size == (200.0, 100.0)  # a shift never changes the page size
    assert transform.map_point(50.0, 0.0) == pytest.approx((210.0, 45.0))
    assert PageTransform(100.0, 200.0, 0.0, 3.0, 4.0).map_point(1.0, 2.0) == pytest.approx((4.0, 6.0))


@pytest.mark.parametrize("edit", [PageEdit(offset_x_pt=0.5 * _CM), PageEdit(rotation_deg=2.0, offset_y_pt=-_CM), PageEdit(rotation_deg=90.0, offset_x_pt=_CM)])
def test_shifted_content_lands_where_map_point_says_and_preview_equals_result(tmp_path, edit):
    source_path = _pdf(tmp_path / "a.pdf", 1)
    target = tmp_path / "out.pdf"
    write_edited_pdf(source_path, [1], {1: edit}, target)
    source, edited = fitz.open(source_path), fitz.open(target)
    try:
        expected = source_transform(source, 1, edit).map_point(*_word_center(source[0], "P1"))
        assert _word_center(edited[0], "P1") == pytest.approx(expected, abs=1.5)
        preview = render_edited_page(source, 1, edit, zoom=0.5)
        result = edited[0].get_pixmap(matrix=fitz.Matrix(0.5, 0.5), alpha=False)
        assert preview.samples == result.samples
    finally:
        source.close()
        edited.close()


def test_half_centimetre_shift_moves_the_word_by_14_17_points(tmp_path):
    source_path = _pdf(tmp_path / "a.pdf", 1)
    write_edited_pdf(source_path, [1], {1: PageEdit(offset_x_pt=0.5 * _CM)}, tmp_path / "out.pdf")
    source, edited = fitz.open(source_path), fitz.open(tmp_path / "out.pdf")
    try:
        before, after = _word_center(source[0], "P1"), _word_center(edited[0], "P1")
        assert after[0] - before[0] == pytest.approx(14.17, abs=0.05) and after[1] == pytest.approx(before[1], abs=0.05)
    finally:
        source.close()
        edited.close()


def test_order_delete_rotate_and_shift_combine_independently(tmp_path):
    """A2: all four edits at once; deletion/order semantics unchanged, edits stay with the original page."""
    session = ScanWorkshopSession([_student("a.pdf", 3)])
    session.go_page(2)  # page 3
    session.rotate_by(2.0)
    session.shift_by(5.0, -3.0)
    session.move_page(-2)  # page 3 to the front
    session.go_page(2)  # position 3 = page 2
    session.toggle_delete()
    state = session.current_state
    assert state.order == [3, 1, 2] and state.page_mapping() == {1: 2, 2: None, 3: 1}
    assert state.edit_for(3) == PageEdit(rotation_deg=2.0, offset_x_pt=5.0, offset_y_pt=-3.0)

    count = write_edited_pdf(_pdf(tmp_path / "a.pdf", 3), state.order, state.edits, tmp_path / "out.pdf")
    assert count == 2 and _texts(tmp_path / "out.pdf") == ["P3", "P1"]


def test_set_offset_and_reset_to_unchanged():
    session = ScanWorkshopSession([_student("a.pdf", 1)])
    session.shift_by(2.0, 0.0)
    session.set_offset(y_pt=4.0)
    assert session.current_edit == PageEdit(offset_x_pt=2.0, offset_y_pt=4.0) and session.changed_pdfs() == ["a.pdf"]
    session.set_offset(0.0, 0.0)
    assert session.current_state.edits == {} and not session.changed_pdfs()


def test_shift_step_setting_is_clamped():
    from app.infrastructure.repositories.json_app_settings_repository import clamp_scan_shift_step

    assert clamp_scan_shift_step("0,5") == 0.5 and clamp_scan_shift_step(9) == 5.0 and clamp_scan_shift_step(0) == 0.1
    assert clamp_scan_shift_step("abc") == 0.5
