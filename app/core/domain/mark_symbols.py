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

``drawing``: ``"glyph"`` = the content string set in DejaVu Sans Bold; ``"drawn"`` =
a shape from ``app/infrastructure/rendering/mark_shapes.py`` (keyed by ``key``).
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


MARK_SYMBOLS: tuple[MarkSymbol, ...] = (
    MarkSymbol("check", "✓", "Richtig", "r", "glyph"),
    MarkSymbol("wrong", "✗", "Falsch", "f", "glyph"),
    MarkSymbol("consequential", "(✓)", "Folgerichtig", "g", "glyph"),
    # Formerly "Folgefehler"; same glyph, so existing ↻ marks keep their look.
    MarkSymbol("circular", "↻", "Zirkelschluss", "z", "glyph"),
    MarkSymbol("swap_h", "⇄", "Vertauschung horizontal", "t", "glyph"),
    MarkSymbol("swap_v", "⇅", "Vertauschung vertikal", "T", "glyph"),
    MarkSymbol("hint", "!", "Hinweis", "h", "glyph"),
    MarkSymbol("question", "?", "Unklar", "u", "glyph"),
    MarkSymbol("gap", "[…]", "Hier fehlt etwas", "l", "glyph"),
    MarkSymbol("useless", "✓∅", "Stimmt, hilft aber nicht", "n", "glyph"),
    MarkSymbol("jargon", "sym:jargon", "Fachsprache", "s", "drawn"),
    MarkSymbol("arrow_curved", "sym:arrow_curved", "Gebogener Pfeil", "b", "drawn"),
    MarkSymbol("arrow_straight", "sym:arrow_straight", "Gerader Pfeil", "p", "drawn"),
    MarkSymbol("example", "sym:example", "Beispiel ist kein Beweis", "e", "drawn"),
    MarkSymbol("strike", "sym:strike", "Durchstreichen", "d", "drawn"),
    MarkSymbol("wavy", "sym:wavy", "Wellenlinie (Form/Schreibweise)", "w", "drawn"),
)

SYMBOL_BY_KEY: dict[str, MarkSymbol] = {symbol.key: symbol for symbol in MARK_SYMBOLS}
SYMBOL_BY_CONTENT: dict[str, MarkSymbol] = {symbol.content: symbol for symbol in MARK_SYMBOLS}
DEFAULT_SYMBOL_KEY = "check"
