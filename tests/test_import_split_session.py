"""Unit tests for `ImportSplitSession` - the Tk-free rules behind Enter / Shift+Enter / the name field."""

from pathlib import Path

import pytest

from app.adapters.gui.import_split_session import ImportSplitSession
from app.infrastructure.pdf.pdf_merger import MergedSourceSpan


class _FakeDocument:
    def __init__(self, page_count: int) -> None:
        self.page_count = page_count
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1


def _session(page_count: int = 10) -> ImportSplitSession:
    return ImportSplitSession(_FakeDocument(page_count), [MergedSourceSpan(Path("a.pdf"), 1, page_count)])


def test_mark_on_new_page_starts_section_with_empty_name():
    session = _session()
    session.set_name_for_page(1, "Anna")

    assert session.mark_boundary(4) is True
    assert session.name_for_page(4) == ""
    assert session.name_for_page(3) == "Anna"


@pytest.mark.parametrize("page", [1, 4])
def test_mark_on_page_one_or_existing_start_changes_nothing(page):
    session = _session()
    session.mark_boundary(4)
    session.set_name_for_page(4, "Ben")

    assert session.mark_boundary(page) is False
    assert session.boundaries == {4}
    assert session.name_for_page(4) == "Ben"


def test_unmark_inside_section_removes_its_start_and_name_and_shows_previous_name():
    session = _session()
    session.set_name_for_page(1, "Anna")
    session.mark_boundary(4)
    session.set_name_for_page(4, "Ben")

    assert session.unmark_section_of(6) is True
    assert session.boundaries == set()
    assert session.names == {1: "Anna"}
    assert session.name_for_page(6) == "Anna"


def test_unmark_in_first_section_changes_nothing():
    session = _session()
    session.mark_boundary(4)

    assert session.unmark_section_of(2) is False
    assert session.boundaries == {4}


def test_names_follow_section_starts_and_empty_text_removes_name():
    session = _session()
    session.mark_boundary(5)
    session.set_name_for_page(7, "Ben")

    assert session.names == {5: "Ben"}
    session.set_name_for_page(6, "   ")
    assert session.names == {}


def test_page_navigation_has_no_wraparound():
    session = _session(3)

    assert session.step_page(-1) is False
    assert session.step_page(1) is True
    assert session.go_to_page(3) is True
    assert session.step_page(1) is False
    assert session.current_page == 3


def test_has_user_input_ignores_blank_names():
    session = _session()
    assert session.has_user_input() is False
    session.names[1] = "  "
    assert session.has_user_input() is False
    session.mark_boundary(2)
    assert session.has_user_input() is True


def test_sections_and_source_span_lookup():
    session = ImportSplitSession(
        _FakeDocument(7), [MergedSourceSpan(Path("a.pdf"), 1, 3), MergedSourceSpan(Path("b.pdf"), 4, 7)]
    )
    session.mark_boundary(4)
    session.set_name_for_page(4, " Ben ")

    assert [(s.start_page, s.end_page, s.name) for s in session.sections()] == [(1, 3, ""), (4, 7, "Ben")]
    assert session.source_span_for_page(4).path == Path("b.pdf")
    assert session.creates_exam is False


def test_close_is_idempotent():
    document = _FakeDocument(2)
    session = ImportSplitSession(document, [])

    session.close()
    session.close()

    assert document.close_calls == 1
    assert session.closed is True


def test_new_section_inherits_group_and_assignment_switches_from_here_on():
    session = _session(12)
    session.mark_boundary(4)
    session.mark_boundary(7)
    second = session.add_group("Bio 10b")

    assert session.assign_group_for_page(5, second) is True
    assert [session.group_index_for_page(page) for page in (1, 4, 7, 12)] == [0, 1, 1, 1]
    session.mark_boundary(10)
    assert session.group_index_for_page(10) == second
    assert session.assign_group_for_page(8, second) is False


def test_unmark_keeps_the_group_of_following_sections():
    session = _session(12)
    session.mark_boundary(4)
    session.mark_boundary(7)
    session.assign_group_for_page(4, session.add_group("10b"))

    assert session.unmark_section_of(5) is True
    assert session.group_index_for_page(4) == 0
    assert session.group_index_for_page(7) == 1
    assert session.group_switches == {7: 1}


def test_neighbor_group_index_offers_a_new_group_past_the_last():
    session = _session()
    session.add_group("B")

    assert session.neighbor_group_index(1, -1) is None
    assert session.neighbor_group_index(1, 1) == 1
    session.assign_group_for_page(1, 1)
    assert session.neighbor_group_index(1, 1) == 2
    assert session.neighbor_group_index(1, -1) == 0


def test_group_names_are_validated_on_add_and_rename():
    session = _session()

    with pytest.raises(ValueError, match="duplicate"):
        session.add_group("klausur 1")
    with pytest.raises(ValueError, match="invalid"):
        session.rename_group(0, "///")
    session.rename_group(0, "  Bio 10a ")
    assert session.group_names == ["Bio 10a"]
    assert session.assign_group_for_page(1, 3) is False


def test_klausur_changes_count_as_user_input():
    session = _session()
    session.add_group("B")
    assert session.has_user_input() is True

    renamed = _session()
    renamed.rename_group(0, "Bio")
    assert renamed.has_user_input() is True
