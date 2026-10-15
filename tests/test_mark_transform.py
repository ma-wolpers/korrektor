"""Orientation algebra: mirror first, then rotate; the two mirror buttons in screen terms."""

from __future__ import annotations

import itertools

import pytest
from PIL import Image

from app.core.domain.mark_transform import Orientation, flipped_horizontally, flipped_vertically, rotated
from app.infrastructure.rendering.mark_renderer import MarkStyle, render_mark_image

GRID = [45.0 * step for step in range(8)]


def test_wish_list_example_45_left_mirrored_vertically_is_mirrored_and_135_left():
    assert flipped_vertically(Orientation.of(45.0, False)) == Orientation(135.0, True)


@pytest.mark.parametrize(("theta", "mirrored"), itertools.product(GRID, [False, True]))
def test_mirroring_twice_restores_and_h_then_v_is_a_half_turn(theta, mirrored):
    start = Orientation.of(theta, mirrored)
    assert flipped_horizontally(flipped_horizontally(start)) == start
    assert flipped_vertically(flipped_vertically(start)) == start
    assert flipped_vertically(flipped_horizontally(start)) == rotated(start, 180.0)


def test_rotation_snaps_to_45_degree_grid_and_keeps_the_mirror_flag():
    assert rotated(Orientation.of(0.0, True), -45.0) == Orientation(315.0, True)
    assert Orientation.of(15.0, False).rotation_deg == 0.0
    assert Orientation.of(-90.0, False).rotation_deg == 270.0


def _pixels(orientation: Orientation) -> Image.Image:
    return render_mark_image(
        MarkStyle("symbol", "sym:arrow_curved", "#d62828", 20.0, orientation.rotation_deg, orientation.mirrored), 2.0
    )


@pytest.mark.parametrize("theta", [0.0, 90.0, 180.0, 270.0])
@pytest.mark.parametrize("mirrored", [False, True])
def test_mirror_buttons_mirror_what_is_shown(theta, mirrored):
    """The stored normal form after a button press draws exactly the mirrored picture."""
    start = Orientation.of(theta, mirrored)
    shown = _pixels(start)
    horizontal = _pixels(flipped_horizontally(start))
    vertical = _pixels(flipped_vertically(start))
    assert horizontal.tobytes() == shown.transpose(Image.Transpose.FLIP_LEFT_RIGHT).tobytes()
    assert vertical.tobytes() == shown.transpose(Image.Transpose.FLIP_TOP_BOTTOM).tobytes()
