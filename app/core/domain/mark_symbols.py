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

``drawing``: ``"glyph"`` = the content string in its font (Segoe UI Semibold / Segoe UI Symbol, see
``app/infrastructure/rendering/mark_fonts.py``); ``"combo"`` =
the same characters set tightly, ink to ink (``mark_shapes.draw_combo``); ``"drawn"`` =
a shape from ``app/infrastructure/rendering/mark_shapes.py`` (keyed by ``key``).

``scale`` multiplies the symbol's size so that every symbol shows about as big as the
former on-screen ✗ (glyphs differ in size within and between fonts - see ``mark_fonts``);
measured, see ``tests/test_mark_renderer.py::test_symbols_have_the_former_on_screen_size``.
``combo_gap_em`` is the ink-to-ink gap of a ``"combo"`` (negative = slight overlap).
``description`` explains the symbol to students (``DESCRIPTIONS``; shown in the evaluation's
symbol overview and in the exported symbol legend).
"""

from __future__ import annotations

from dataclasses import dataclass, replace


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
    description: str = ""


_PALETTE: tuple[MarkSymbol, ...] = (
    MarkSymbol("check", "✓", "Richtig", "r", "glyph", 0.96),
    MarkSymbol("wrong", "✗", "Falsch", "f", "glyph", 0.88),
    MarkSymbol("consequential", "(✓)", "Folgerichtig", "g", "combo"),
    # Formerly "Folgefehler"; same glyph, so existing ↻ marks keep their look.
    MarkSymbol("circular", "↻", "Zirkelschluss", "z", "glyph", 1.17),
    MarkSymbol("swap_h", "⇄", "Vertauschung horizontal", "t", "glyph", 0.83),
    MarkSymbol("swap_v", "⇅", "Vertauschung vertikal", "T", "glyph", 0.89),
    MarkSymbol("hint", "!", "Hinweis", "h", "glyph"),
    MarkSymbol("question", "?", "Unklar", "u", "glyph"),
    MarkSymbol("gap", "[…]", "Hier fehlt etwas", "l", "glyph", 0.84),
    MarkSymbol("useless", "✓∅", "Stimmt, hilft aber nicht", "n", "combo", combo_gap_em=-0.04),
    MarkSymbol("jargon", "sym:jargon", "Fachsprache", "s", "drawn", 0.84),
    MarkSymbol("arrow_curved", "sym:arrow_curved", "Gebogener Pfeil", "b", "drawn", 0.86),
    MarkSymbol("arrow_straight", "sym:arrow_straight", "Gerader Pfeil", "p", "drawn"),
    MarkSymbol("example", "sym:example", "Beispiel ist kein Beweis", "e", "drawn", 0.92),
    MarkSymbol("strike", "sym:strike", "Durchstreichen", "d", "drawn"),
    MarkSymbol("wavy", "sym:wavy", "Wellenlinie (Form/Schreibweise)", "w", "drawn"),
    MarkSymbol("smile", "sym:smile", "Lächeln", "L", "drawn", 0.79),
    MarkSymbol("sad", "sym:sad", "Traurig", "U", "drawn", 0.79),
    MarkSymbol("shocked", "sym:shocked", "Schockiert", "o", "drawn", 0.79),
    MarkSymbol("heart", "sym:heart", "Herz", "H", "drawn", 0.79),
)

# What each symbol means, for students (symbol overview and symbol legend export).
DESCRIPTIONS: dict[str, str] = {
    "check": "Dieser Schritt ist richtig.",
    "wrong": "Hier ist ein Fehler.",
    "consequential": "Mit einem früheren Fehler richtig weitergearbeitet – dieser Schritt zählt.",
    "circular": "Die Begründung setzt schon voraus, was gezeigt werden soll.",
    "swap_h": "Hier wurde etwas vertauscht (z. B. Reihenfolge oder Zuordnung nebeneinander).",
    "swap_v": "Hier wurde etwas vertauscht (z. B. übereinanderstehende Teile).",
    "hint": "Achtung – hier lohnt sich ein genauer Blick.",
    "question": "Hier ist nicht nachvollziehbar, was gemeint ist.",
    "gap": "Ein Schritt, eine Begründung oder eine Angabe fehlt.",
    "useless": "Die Aussage stimmt, bringt die Lösung aber nicht weiter.",
    "jargon": "Hier fehlt der Fachbegriff oder eine fachlich genaue Formulierung.",
    "arrow_curved": "Bezieht sich auf die Stelle, auf die der Pfeil zeigt.",
    "arrow_straight": "Zeigt auf die gemeinte Stelle oder die richtige Position.",
    "example": "Ein Beispiel ist keine Begründung und kein Beweis für den allgemeinen Fall.",
    "strike": "Gestrichen – gehört nicht dazu oder ist falsch.",
    "wavy": "Formaler Fehler: Schreibweise, Notation oder Form stimmt nicht.",
    "smile": "Schön gemacht!",
    "sad": "Schade – hier wäre mehr drin gewesen.",
    "shocked": "Ups – hier ist etwas gründlich schiefgegangen.",
    "heart": "Besonders gelungen!",
}

MARK_SYMBOLS: tuple[MarkSymbol, ...] = tuple(replace(symbol, description=DESCRIPTIONS[symbol.key]) for symbol in _PALETTE)

SYMBOL_BY_KEY: dict[str, MarkSymbol] = {symbol.key: symbol for symbol in MARK_SYMBOLS}
SYMBOL_BY_CONTENT: dict[str, MarkSymbol] = {symbol.content: symbol for symbol in MARK_SYMBOLS}
DEFAULT_SYMBOL_KEY = "check"
