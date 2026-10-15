"""mark_renderer: extents, real orientation of asymmetric symbols, formulas, fallbacks."""

from __future__ import annotations

import numpy
import pytest
from PIL import Image

from app.core.domain.mark_symbols import MARK_SYMBOLS
from app.infrastructure.rendering.mark_renderer import MarkStyle, render_mark_image, rotate_ccw, validate_mark_text

RED = "#d62828"


def _style(content: str, rotation: float = 0.0, mirrored: bool = False, kind: str = "symbol") -> MarkStyle:
    return MarkStyle(kind, content, RED, 20.0, rotation, mirrored)


def _ink_halves(image: Image.Image) -> dict[str, int]:
    """Ink pixel counts per half: left/right/top/bottom."""
    alpha = numpy.asarray(image.getchannel("A")) > 128
    height, width = alpha.shape

    def count(box):
        left, top, right, bottom = box
        return int(alpha[top:bottom, left:right].sum())

    return {
        "left": count((0, 0, width // 2, height)),
        "right": count((width - width // 2, 0, width, height)),
        "top": count((0, 0, width, height // 2)),
        "bottom": count((0, height - height // 2, width, height)),
    }


@pytest.mark.parametrize("symbol", MARK_SYMBOLS, ids=lambda s: s.key)
def test_every_catalog_symbol_renders_ink(symbol):
    image = render_mark_image(_style(symbol.content), 2.0)
    assert image.getchannel("A").getbbox() is not None


@pytest.mark.parametrize("symbol", MARK_SYMBOLS, ids=lambda s: s.key)
def test_quarter_turn_swaps_extent_and_mirroring_keeps_it(symbol):
    upright = render_mark_image(_style(symbol.content), 2.0)
    quarter = render_mark_image(_style(symbol.content, 90.0), 2.0)
    mirrored = render_mark_image(_style(symbol.content, 0.0, True), 2.0)
    assert quarter.size == (upright.height, upright.width)
    assert mirrored.size == upright.size


@pytest.mark.parametrize("rotation", [0.0, 90.0, 180.0, 270.0])
@pytest.mark.parametrize("mirrored", [False, True])
def test_transform_is_mirror_then_rotate(rotation, mirrored):
    """The stored (θ, m) means: mirror the upright image first, then rotate it by θ."""
    upright = render_mark_image(_style("sym:arrow_curved"), 2.0)
    expected = upright.transpose(Image.Transpose.FLIP_LEFT_RIGHT) if mirrored else upright
    expected = rotate_ccw(expected, rotation)
    actual = render_mark_image(_style("sym:arrow_curved", rotation, mirrored), 2.0)
    assert actual.size == expected.size
    assert actual.tobytes() == expected.tobytes()


@pytest.mark.parametrize(
    ("rotation", "mirrored", "tip"),
    [(0.0, False, "right"), (90.0, False, "top"), (180.0, False, "left"), (0.0, True, "left"), (90.0, True, "bottom")],
)
def test_straight_arrow_points_where_expected(rotation, mirrored, tip):
    """The filled head carries more ink than the shaft end, so the heavier half is the tip."""
    halves = _ink_halves(render_mark_image(_style("sym:arrow_straight", rotation, mirrored), 4.0))
    opposite = {"right": "left", "left": "right", "top": "bottom", "bottom": "top"}[tip]
    assert halves[tip] > halves[opposite] * 1.2


def test_example_symbol_is_taller_than_wide_and_strike_rises():
    example = render_mark_image(_style("sym:example"), 4.0)
    assert example.height > example.width
    strike = _ink_halves(render_mark_image(_style("sym:strike"), 4.0))
    # rising diagonal: ink of the left half sits low, so bottom-left dominates top-left
    image = render_mark_image(_style("sym:strike"), 4.0)
    left = image.crop((0, 0, image.width // 3, image.height)).getchannel("A").getbbox()
    assert left is not None and left[1] > image.height // 3
    assert strike["left"] > 0 and strike["right"] > 0


def test_unknown_symbol_content_is_drawn_as_glyph():
    image = render_mark_image(_style("△"), 2.0)
    assert image.getchannel("A").getbbox() is not None


def test_formula_is_typeset_and_differs_from_literal_text():
    formula = render_mark_image(_style(r"$\frac{1}{2}$", kind="text"), 2.0)
    literal = render_mark_image(_style(r"\frac{1}{2}", kind="text"), 2.0)
    assert formula.size != literal.size
    assert formula.height > formula.width * 0.6  # a stacked fraction, not one line of text


def test_several_formulas_in_one_comment():
    assert validate_mark_text("aus $a=1$ folgt $b^2=2$") is None
    assert render_mark_image(_style("aus $a=1$ folgt $b^2=2$", kind="text"), 1.0).width > 0


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        ("kostet 5$", "Ungerade"),
        (r"$\frac{1}{$ und $x$", r"Expected \frac{num}{den}"),
        (r"$\begin{matrix}1\end{matrix}$", r"Unknown symbol: \begin"),
    ],
)
def test_invalid_formulas_are_explained_and_drawn_literally(text, problem):
    message = validate_mark_text(text)
    assert message is not None and problem in message
    assert render_mark_image(_style(text, kind="text"), 1.0).getchannel("A").getbbox() is not None


def test_escaped_dollar_is_literal():
    assert validate_mark_text(r"kostet \$5") is None
    assert validate_mark_text(r"\$ und $x$") is None
