"""Symbol legend export: pages, PNG height, no counts, usecase writes the file, empty state."""

from __future__ import annotations

from pathlib import Path

import fitz
from PIL import Image

from app.core.domain.mark_symbols import MARK_SYMBOLS
from app.core.domain.symbol_usage import SymbolUsage
from app.core.usecases.export_symbol_legend_usecase import ExportSymbolLegendUseCase
from app.infrastructure.rendering.symbol_legend_renderer import (
    ROWS_PER_PAGE,
    MatplotlibSymbolLegendExportRepository,
    write_symbol_legend,
)


def _catalog_usages() -> list[SymbolUsage]:
    return [SymbolUsage(symbol.content, symbol, 7, 3, ("1A",)) for symbol in MARK_SYMBOLS]


def _many(count: int) -> list[SymbolUsage]:
    """Synthetic unknown contents to force several pages."""
    return [SymbolUsage(chr(0x25A0 + index), None, 1, 1, ()) for index in range(count)]


def test_all_catalog_symbols_fit_on_two_pages_and_text_has_no_counts(tmp_path: Path):
    target = tmp_path / "legende.pdf"
    write_symbol_legend(_catalog_usages(), target, title="Mathe 8a", color_hex="#d62828")
    with fitz.open(target) as document:
        assert document.page_count == 2  # 18 + 2
        text = "".join(page.get_text() for page in document)
    assert "Richtig" in text and "Dieser Schritt ist richtig." in text and "Mathe 8a" in text
    assert "7×" not in text and "Abgabe" not in text  # counts stay in the teacher's view


def test_many_rows_continue_on_further_pages(tmp_path: Path):
    target = tmp_path / "viele.pdf"
    write_symbol_legend(_many(45), target, title="X", color_hex="#111111")
    with fitz.open(target) as document:
        assert document.page_count == -(-45 // ROWS_PER_PAGE) == 3


def test_png_is_one_image_growing_with_the_rows(tmp_path: Path):
    small, large = tmp_path / "a.png", tmp_path / "b.png"
    write_symbol_legend(_many(3), small, title="X", color_hex="#111111")
    write_symbol_legend(_many(30), large, title="X", color_hex="#111111")
    with Image.open(small) as first, Image.open(large) as second:
        assert first.width == second.width and second.height > first.height * 3


def test_usecase_writes_the_file(tmp_path: Path):
    target = tmp_path / "legende.pdf"
    ExportSymbolLegendUseCase(MatplotlibSymbolLegendExportRepository()).execute(
        entries=_catalog_usages()[:3], title="Mathe", color_hex="#d62828", output_path=target
    )
    assert target.is_file() and target.stat().st_size > 1000


def test_older_symbol_names_render_without_missing_glyphs(tmp_path: Path, recwarn):
    """An older symbol's name is the symbol itself (e.g. △) - it must not fall into a font without it."""
    write_symbol_legend([SymbolUsage("△", None, 1, 1, ())], tmp_path / "alt.pdf", title="X", color_hex="#111111")
    assert not [warning for warning in recwarn if "missing from font" in str(warning.message)]
