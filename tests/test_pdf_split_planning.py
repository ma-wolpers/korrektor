import pytest

from app.core.domain.pdf_split_planning import compute_split_ranges


def test_no_boundaries_besides_page_one_is_a_single_abgabe():
    assert compute_split_ranges(5, set()) == [(1, 5)]


def test_single_boundary_splits_into_two():
    assert compute_split_ranges(10, {6}) == [(1, 5), (6, 10)]


def test_multiple_boundaries():
    assert compute_split_ranges(10, {1, 4, 8}) == [(1, 3), (4, 7), (8, 10)]


def test_unsorted_and_duplicate_boundaries_are_normalized():
    assert compute_split_ranges(10, {8, 4, 4, 1}) == [(1, 3), (4, 7), (8, 10)]


def test_boundary_on_page_one_is_not_double_counted():
    assert compute_split_ranges(6, {1}) == [(1, 6)]


def test_single_page_document():
    assert compute_split_ranges(1, set()) == [(1, 1)]


def test_rejects_zero_total_pages():
    with pytest.raises(ValueError):
        compute_split_ranges(0, set())


def test_rejects_boundary_page_zero():
    with pytest.raises(ValueError):
        compute_split_ranges(10, {0})


def test_rejects_negative_boundary_page():
    with pytest.raises(ValueError):
        compute_split_ranges(10, {-3})


def test_rejects_boundary_page_beyond_total_pages():
    with pytest.raises(ValueError):
        compute_split_ranges(10, {3, 999})
