"""Catalog of correction symbols (palette, keyboard shortcuts, drawing kind).

A symbol mark is stored as ``PdfAnnotation(annotation_type="symbol", content=...)``;
``content`` is the symbol's identity in the exam JSON. Symbols that have always been
Unicode glyphs keep their glyph as ``content`` ("✓", "↻" …), so existing exams load
unchanged. Symbols that are drawn as shapes use ``"sym:<key>"``.

``content`` values that are not in this catalog (e.g. the removed "Teilrichtig" △)
are still shown and exported: the renderer draws them as plain glyph text.

``shortcut`` is the canonical ``KeySpec`` character: a lowercase letter means the
key without Shift, an uppercase letter means Shift + that key (bw-gui matches
letters by Shift, never by CapsLock), so ``"t"`` and ``"T"`` are different shortcuts.

``drawing``: ``"glyph"`` = the content string set in DejaVu Sans Bold; ``"combo"`` =
the same characters set tightly, ink to ink (``mark_shapes.draw_combo``); ``"drawn"`` =
a shape from ``app/infrastructure/rendering/mark_shapes.py`` (keyed by ``key``).

``scale`` multiplies the symbol's size so that every symbol shows about as big as the
former on-screen ✗ (DejaVu's ✓ is small, its ⇄/⇅ are large compared with the old font);
measured, see ``tests/test_mark_renderer.py::test_symbols_have_the_former_on_screen_size``.
``combo_gap_em`` is the ink-to-ink gap of a ``"combo"`` (negative = slight overlap).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarkSymbol:
    """One palette entry."""

    key: str
    content: str
    label: str
    shortcut: str
    drawing: str
    scale: float = 1.0
    combo_gap_em: float = 0.07


MARK_SYMBOLS: tuple[MarkSymbol, ...] = (
    MarkSymbol("check", "✓", "Richtig", "r", "glyph", 1.36),
    MarkSymbol("wrong", "✗", "Falsch", "f", "glyph"),
    MarkSymbol("consequential", "(✓)", "Folgerichtig", "g", "combo"),
    # Formerly "Folgefehler"; same glyph, so existing ↻ marks keep their look.
    MarkSymbol("circular", "↻", "Zirkelschluss", "z", "glyph"),
    MarkSymbol("swap_h", "⇄", "Vertauschung horizontal", "t", "glyph", 0.71),
    MarkSymbol("swap_v", "⇅", "Vertauschung vertikal", "T", "glyph", 0.82),
    MarkSymbol("hint", "!", "Hinweis", "h", "glyph"),
    MarkSymbol("question", "?", "Unklar", "u", "glyph"),
    MarkSymbol("gap", "[…]", "Hier fehlt etwas", "l", "glyph", 0.85),
    MarkSymbol("useless", "✓∅", "Stimmt, hilft aber nicht", "n", "combo", 0.8, combo_gap_em=-0.04),
    MarkSymbol("jargon", "sym:jargon", "Fachsprache", "s", "drawn", 0.84),
    MarkSymbol("arrow_curved", "sym:arrow_curved", "Gebogener Pfeil", "b", "drawn", 0.86),
    MarkSymbol("arrow_straight", "sym:arrow_straight", "Gerader Pfeil", "p", "drawn"),
    MarkSymbol("example", "sym:example", "Beispiel ist kein Beweis", "e", "drawn", 0.85),
    MarkSymbol("strike", "sym:strike", "Durchstreichen", "d", "drawn"),
    MarkSymbol("wavy", "sym:wavy", "Wellenlinie (Form/Schreibweise)", "w", "drawn"),
    MarkSymbol("smile", "sym:smile", "Lächeln", "L", "drawn", 0.79),
    MarkSymbol("sad", "sym:sad", "Traurig", "U", "drawn", 0.79),
    MarkSymbol("shocked", "sym:shocked", "Schockiert", "o", "drawn", 0.79),
    MarkSymbol("heart", "sym:heart", "Herz", "H", "drawn", 0.79),
)

SYMBOL_BY_KEY: dict[str, MarkSymbol] = {symbol.key: symbol for symbol in MARK_SYMBOLS}
SYMBOL_BY_CONTENT: dict[str, MarkSymbol] = {symbol.content: symbol for symbol in MARK_SYMBOLS}
DEFAULT_SYMBOL_KEY = "check"
