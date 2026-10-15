"""Symbol catalog: unique identities and shortcuts, user decisions kept."""

from __future__ import annotations

from app.core.domain.mark_symbols import MARK_SYMBOLS, SYMBOL_BY_CONTENT, SYMBOL_BY_KEY
from app.infrastructure.rendering.mark_shapes import DRAWN_SHAPES

from bw_gui.contracts.key_spec import KeySpec, overlaps


def test_keys_contents_and_shortcuts_are_unique():
    assert len(SYMBOL_BY_KEY) == len(SYMBOL_BY_CONTENT) == len(MARK_SYMBOLS)
    assert len({symbol.shortcut for symbol in MARK_SYMBOLS}) == len(MARK_SYMBOLS)


def test_shortcuts_are_single_printable_characters_that_never_overlap():
    specs = [KeySpec.char(symbol.shortcut) for symbol in MARK_SYMBOLS]
    assert all(len(symbol.shortcut) == 1 and symbol.shortcut.isprintable() for symbol in MARK_SYMBOLS)
    for index, first in enumerate(specs):
        for second in specs[index + 1:]:
            assert not overlaps(first, second), (first, second)


def test_user_decisions():
    assert "△" not in SYMBOL_BY_CONTENT  # "Teilrichtig" removed
    assert SYMBOL_BY_CONTENT["↻"].label == "Zirkelschluss"
    assert SYMBOL_BY_KEY["consequential"].content == "(✓)"
    assert SYMBOL_BY_KEY["useless"].content == "✓∅"
    assert SYMBOL_BY_KEY["swap_h"].shortcut == "t" and SYMBOL_BY_KEY["swap_v"].shortcut == "T"


def test_every_drawn_symbol_has_a_shape_and_drawn_contents_are_namespaced():
    for symbol in MARK_SYMBOLS:
        if symbol.drawing == "drawn":
            assert symbol.key in DRAWN_SHAPES
            assert symbol.content == f"sym:{symbol.key}"
        else:
            assert symbol.drawing == "glyph" and not symbol.content.startswith("sym:")
