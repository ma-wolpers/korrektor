"""Symbol legend for students: icon, name and explanation of every symbol used in an exam.

Rendering only - which symbols, their names and explanations come finished from the
domain (``symbol_usage.SymbolUsage``). **No counts** are written: the legend is meant for
students, the counts in the evaluation window are for the teacher.

* PDF: A4 portrait pages with a header (exam name) and at most ``ROWS_PER_PAGE`` rows;
  more symbols continue on further pages (``PdfPages``).
* PNG: one tall image with every row (height grows with the number of rows).

Icons are the very images the correction draws (``mark_renderer.render_mark_image``),
in the given marker colour; text uses the marks' letter font (``mark_fonts``).
"""

from __future__ import annotations

import textwrap
from collections.abc import Sequence
from pathlib import Path

import numpy
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties

from app.core.domain.symbol_usage import SymbolUsage
from app.infrastructure.rendering.mark_fonts import TEXT_FONT_PATH, font_for_text
from app.infrastructure.rendering.mark_renderer import MarkStyle, render_mark_image

A4_INCHES = (8.27, 11.69)
ROWS_PER_PAGE = 18
_HEADER_INCHES = 1.1
_ROW_INCHES = (A4_INCHES[1] - _HEADER_INCHES - 0.6) / ROWS_PER_PAGE
_ICON_FONT_PT = 20.0
_WRAP = 78


def _font(size: float, bold: bool = False, text: str = "") -> FontProperties:
    """Font at ``size`` points: the marks' letter font, or - if ``text`` needs glyphs it lacks
    (an older symbol's name is the symbol itself, e.g. △) - the font that covers ``text``."""
    path = font_for_text(text) if text else TEXT_FONT_PATH
    return FontProperties(fname=path, size=size, weight="bold" if bold else "normal")


def _draw_rows(figure: Figure, entries: Sequence[SymbolUsage], title: str, color_hex: str, height_in: float) -> None:
    """Header plus one row per entry, laid out in inches from the top of ``figure``."""
    width_in = figure.get_figwidth()
    figure.text(0.6 / width_in, 1 - 0.45 / height_in, "Symbole in der Korrektur", fontproperties=_font(16, bold=True))
    figure.text(0.6 / width_in, 1 - 0.75 / height_in, title, fontproperties=_font(10), color="#555555")
    for index, entry in enumerate(entries):
        top = _HEADER_INCHES + index * _ROW_INCHES
        icon = render_mark_image(MarkStyle("symbol", entry.content, color_hex, _ICON_FONT_PT), 4.0)
        axes = figure.add_axes((0.6 / width_in, 1 - (top + _ROW_INCHES * 0.85) / height_in, 0.7 / width_in, _ROW_INCHES * 0.75 / height_in))
        axes.imshow(numpy.asarray(icon))
        axes.set_axis_off()
        text_x = 1.55 / width_in
        figure.text(text_x, 1 - (top + 0.2) / height_in, entry.label, fontproperties=_font(11, bold=True, text=entry.label), va="top")
        description = "\n".join(textwrap.wrap(entry.description, _WRAP))
        figure.text(text_x, 1 - (top + 0.42) / height_in, description, fontproperties=_font(9.5, text=description), va="top", color="#333333")


def legend_pages(entries: Sequence[SymbolUsage], *, title: str, color_hex: str) -> list[Figure]:
    """A4 pages of at most ``ROWS_PER_PAGE`` rows each (at least one page)."""
    pages = []
    chunks = [entries[start:start + ROWS_PER_PAGE] for start in range(0, len(entries), ROWS_PER_PAGE)] or [[]]
    for chunk in chunks:
        figure = Figure(figsize=A4_INCHES)
        FigureCanvasAgg(figure)
        _draw_rows(figure, chunk, title, color_hex, A4_INCHES[1])
        pages.append(figure)
    return pages


def legend_image(entries: Sequence[SymbolUsage], *, title: str, color_hex: str) -> Figure:
    """One tall figure with every row (for PNG)."""
    height = _HEADER_INCHES + len(entries) * _ROW_INCHES + 0.4
    figure = Figure(figsize=(A4_INCHES[0], height))
    FigureCanvasAgg(figure)
    _draw_rows(figure, entries, title, color_hex, height)
    return figure


def write_symbol_legend(entries: Sequence[SymbolUsage], output_path: Path, *, title: str, color_hex: str) -> None:
    """Write the legend as PDF (paged) or PNG (one image), chosen by the file extension."""
    if output_path.suffix.lower() == ".png":
        legend_image(entries, title=title, color_hex=color_hex).savefig(output_path, format="png", dpi=150)
        return
    with PdfPages(output_path) as pdf:
        for page in legend_pages(entries, title=title, color_hex=color_hex):
            pdf.savefig(page)


class MatplotlibSymbolLegendExportRepository:
    """``SymbolLegendExportRepository`` port implementation (matplotlib)."""

    def export_symbol_legend(self, *, entries: Sequence[SymbolUsage], title: str, color_hex: str, output_path: Path) -> None:
        """See ``write_symbol_legend``."""
        write_symbol_legend(entries, output_path, title=title, color_hex=color_hex)
