import pytest

from app.core.domain.pdf_split_naming import (
    SplitSection,
    build_split_sections,
    find_other_sections_with_name,
    plan_split_files,
    section_name_key,
)


def test_build_split_sections_attaches_names_to_section_starts():
    sections = build_split_sections(6, {4}, {1: "Anna", 4: " Ben "})
    assert sections == [SplitSection(1, 3, "Anna"), SplitSection(4, 6, "Ben")]


def test_build_split_sections_ignores_names_of_pages_that_are_no_section_start():
    sections = build_split_sections(6, {4}, {2: "verwaist", 4: "Ben"})
    assert sections == [SplitSection(1, 3, ""), SplitSection(4, 6, "Ben")]


def test_build_split_sections_keeps_compute_split_ranges_validation():
    with pytest.raises(ValueError):
        build_split_sections(3, {5}, {})


def test_name_key_ignores_case_and_whitespace_only():
    assert section_name_key("  Anna   Müller ") == section_name_key("anna müller")
    assert section_name_key("Anna?") != section_name_key("Anna")
    assert section_name_key("   ") == ""


def test_find_other_sections_with_name_excludes_current_section():
    sections = [SplitSection(1, 1, "Anna"), SplitSection(2, 6, "anna"), SplitSection(7, 12, "Ben"), SplitSection(13, 19, "ANNA")]
    others = find_other_sections_with_name(sections, "Anna", exclude_start_page=1)
    assert [(section.start_page, section.end_page) for section in others] == [(2, 6), (13, 19)]
    assert find_other_sections_with_name(sections, "  ", exclude_start_page=1) == []


def test_same_name_key_is_merged_in_document_order_with_first_display_name():
    plan = plan_split_files(
        [SplitSection(1, 2, "Anna Müller"), SplitSection(3, 4, "Ben"), SplitSection(5, 6, "anna  müller")]
    )
    assert [(f.filename, f.display_name, f.page_ranges) for f in plan.files] == [
        ("Anna_Müller.pdf", "Anna Müller", ((1, 2), (5, 6))),
        ("Ben.pdf", "Ben", ((3, 4),)),
    ]
    assert [[s.start_page for s in group] for group in plan.merged_groups] == [[1, 5]]
    assert plan.needs_fallback_confirmation is False


def test_unnamed_sections_get_positional_fallback_and_are_never_merged():
    plan = plan_split_files([SplitSection(1, 2, "Anna"), SplitSection(3, 4, ""), SplitSection(5, 6, "")])
    assert [(f.filename, f.page_ranges, f.uses_fallback_name) for f in plan.files] == [
        ("Anna.pdf", ((1, 2),), False),
        ("Abgabe_02.pdf", ((3, 4),), True),
        ("Abgabe_03.pdf", ((5, 6),), True),
    ]
    assert [s.start_page for s in plan.fallback_sections] == [3, 5]
    assert plan.needs_fallback_confirmation is True


def test_name_that_sanitizes_to_nothing_is_reported_and_gets_a_fallback():
    plan = plan_split_files([SplitSection(1, 2, "???"), SplitSection(3, 4, "Ben")])
    assert [s.start_page for s in plan.invalid_name_sections] == [1]
    assert plan.fallback_sections == ()
    assert [(f.filename, f.uses_fallback_name) for f in plan.files] == [("Abgabe_01.pdf", True), ("Ben.pdf", False)]
    assert plan.needs_fallback_confirmation is True


def test_different_names_with_same_sanitized_filename_get_suffix_not_merge():
    plan = plan_split_files([SplitSection(1, 2, "Anna"), SplitSection(3, 4, "Anna?")])
    assert [(f.filename, f.display_name, f.page_ranges) for f in plan.files] == [
        ("Anna.pdf", "Anna", ((1, 2),)),
        ("Anna_2.pdf", "Anna?", ((3, 4),)),
    ]
    assert plan.merged_groups == ()
    assert [f.filename for f in plan.suffixed_files] == ["Anna_2.pdf"]


def test_explicit_name_wins_over_fallback_on_filename_collision():
    plan = plan_split_files([SplitSection(1, 2, ""), SplitSection(3, 4, "abgabe 01")])
    by_display = {f.display_name: f.filename for f in plan.files}
    assert by_display == {"abgabe 01": "abgabe_01.pdf", "Abgabe_01": "Abgabe_01_2.pdf"}


def test_files_are_ordered_by_first_page():
    plan = plan_split_files([SplitSection(1, 1, ""), SplitSection(2, 2, "Zoe"), SplitSection(3, 3, "Anna")])
    assert [f.page_ranges[0][0] for f in plan.files] == [1, 2, 3]
