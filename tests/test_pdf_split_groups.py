"""Unit tests for the Klausur-Zuordnung rules of the PDF import (`pdf_split_groups`)."""

import pytest

from app.core.domain.pdf_split_groups import (
    MAX_GROUPS,
    assign_group,
    drop_section_start,
    group_for_start,
    group_name_problem,
    normalize_switches,
    plan_grouped_split,
    section_counts,
)
from app.core.domain.pdf_split_naming import SplitSection


def _sections(*specs: tuple[int, int, str]) -> list[SplitSection]:
    return [SplitSection(start, end, name) for start, end, name in specs]


def test_group_is_last_marker_at_or_before_start():
    switches = {4: 1, 9: 2}

    assert [group_for_start(page, switches) for page in (1, 4, 6, 9, 12)] == [0, 1, 1, 2, 2]


def test_assign_switches_this_and_all_following_sections_and_drops_redundant_markers():
    starts = [1, 3, 5, 7, 9]

    switches = assign_group(5, 1, {}, starts)
    assert switches == {5: 1}
    # Setting an earlier section to the same group makes the later marker superfluous.
    assert assign_group(3, 1, switches, starts) == {3: 1}
    # Back to group 0 from section 7 on: a single marker, the run 5-6 stays group 1.
    assert assign_group(7, 0, switches, starts) == {5: 1, 7: 0}
    # Assigning the group a section already has changes nothing.
    assert assign_group(7, 1, switches, starts) == {5: 1}


def test_normalize_drops_markers_off_section_starts_and_without_change():
    assert normalize_switches({1: 0, 2: 1, 5: 1, 7: 1}, [1, 5, 7]) == {5: 1}


def test_drop_section_start_moves_its_marker_to_the_next_section():
    # Sections 1, 4, 7; marker on 4 -> 4 and 7 are group 1. Undo the split at 4.
    assert drop_section_start(4, {4: 1}, [1, 7]) == {7: 1}
    # The next section has an own marker: that one wins.
    assert drop_section_start(4, {4: 1, 7: 2}, [1, 7]) == {7: 2}
    # No following section: the marker disappears with its start.
    assert drop_section_start(7, {7: 1}, [1, 4]) == {}


def test_section_counts_per_group():
    sections = _sections((1, 2, "A"), (3, 4, "B"), (5, 6, "C"))

    assert section_counts(sections, {3: 1}, 3) == [1, 2, 0]


@pytest.mark.parametrize(
    "name, exclude, expected",
    [
        ("Bio 10b", None, None),
        ("???", None, "invalid"),
        ("bio 10A", None, "duplicate"),
        ("Bio 10a", 0, None),
        ("Bio 10a.", None, "duplicate"),
    ],
)
def test_group_name_problem(name, exclude, expected):
    assert group_name_problem(name, ["Bio 10a", "Chemie"], exclude_index=exclude) == expected


def test_group_name_problem_limits_new_groups():
    names = [f"K{index}" for index in range(MAX_GROUPS)]

    assert group_name_problem("Neu", names) == "too_many"
    assert group_name_problem("Neu", names, exclude_index=0) is None


def test_single_used_group_writes_into_the_target_folder_as_before():
    sections = _sections((1, 2, "Anna"), (3, 4, ""))

    plan = plan_grouped_split(sections, {}, ["Klausur 1", "Leer"])

    assert plan.uses_subfolders is False
    assert [planned.filename for planned in plan.files] == ["Anna.pdf", "Abgabe_02.pdf"]


def test_several_groups_get_subfolders_and_merge_and_number_per_group():
    sections = _sections((1, 2, "Anna"), (3, 4, ""), (5, 6, "Anna"), (7, 8, "anna"), (9, 10, ""))

    plan = plan_grouped_split(sections, {5: 1}, ["Bio 10a", "Bio: 10b"])

    assert plan.uses_subfolders is True
    assert [(group.name, group.folder) for group in plan.groups] == [("Bio 10a", "Bio 10a"), ("Bio: 10b", "Bio 10b")]
    assert [(planned.filename, planned.page_ranges) for planned in plan.files] == [
        ("Bio 10a/Anna.pdf", ((1, 2),)),
        ("Bio 10a/Abgabe_02.pdf", ((3, 4),)),
        ("Bio 10b/Anna.pdf", ((5, 6), (7, 8))),
        ("Bio 10b/Abgabe_03.pdf", ((9, 10),)),
    ]
    # The group plans keep plain filenames (for the exam's display names).
    assert [planned.filename for planned in plan.groups[1].plan.files] == ["Anna.pdf", "Abgabe_03.pdf"]
    assert len(plan.merged_groups) == 1 and len(plan.fallback_sections) == 2
    assert plan.needs_fallback_confirmation is True
    assert plan.group_of(sections[2]).index == 1


def test_unused_groups_get_no_folder_and_stale_markers_fall_back_to_default_names():
    sections = _sections((1, 2, "Anna"), (3, 4, "Ben"))

    plan = plan_grouped_split(sections, {3: 4}, ["10a", "unbenutzt"])

    assert [(group.index, group.folder) for group in plan.groups] == [(0, "10a"), (4, "Klausur 5")]
