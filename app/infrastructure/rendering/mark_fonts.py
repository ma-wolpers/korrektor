"""Fonts of the correction marks: Segoe UI Semibold for letters, Segoe UI Symbol for symbol glyphs.

User decision (2026-10-15): the marks should look like the former canvas preview, which
used Windows' Segoe UI (DejaVu Sans Bold looked too wide and angular) - in Semibold, and
the symbol glyphs (✓ ✗ ↻ ⇄ ⇅ ∅ …) in the normal weight of Segoe UI Symbol, where Windows
used to find them. Segoe exists on Windows only; elsewhere (or if the files are missing)
both fall back to matplotlib's bundled DejaVu Sans Bold, which covers every glyph.

Choice per character: the letter font if it has the glyph, else the symbol font, else
DejaVu (``font_for_char``); a whole string uses the first font that covers all of it
(``font_for_text``), so "[…]" stays in one font.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import matplotlib
from matplotlib.ft2font import FT2Font

_WINDOWS_FONTS = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
FALLBACK_FONT_PATH = os.path.join(matplotlib.get_data_path(), "fonts", "ttf", "DejaVuSans-Bold.ttf")


def _existing(path: Path) -> str | None:
    """``str(path)`` if the font file exists, else ``None``."""
    return str(path) if path.is_file() else None


TEXT_FONT_PATH = _existing(_WINDOWS_FONTS / "seguisb.ttf") or FALLBACK_FONT_PATH
SYMBOL_FONT_PATH = _existing(_WINDOWS_FONTS / "seguisym.ttf") or FALLBACK_FONT_PATH
USES_SEGOE = TEXT_FONT_PATH != FALLBACK_FONT_PATH and SYMBOL_FONT_PATH != FALLBACK_FONT_PATH


@lru_cache(maxsize=None)
def _has_glyph(font_path: str, char: str) -> bool:
    """True if ``font_path`` contains a glyph for ``char``."""
    return FT2Font(font_path).get_char_index(ord(char)) != 0


def font_for_char(char: str) -> str:
    """Letter font, else symbol font, else DejaVu - the first that has ``char``."""
    for path in (TEXT_FONT_PATH, SYMBOL_FONT_PATH):
        if _has_glyph(path, char):
            return path
    return FALLBACK_FONT_PATH


def font_for_text(text: str) -> str:
    """The first of letter font, symbol font, DejaVu that covers every character of ``text``."""
    for path in (TEXT_FONT_PATH, SYMBOL_FONT_PATH):
        if all(_has_glyph(path, char) for char in text if not char.isspace()):
            return path
    return FALLBACK_FONT_PATH
