from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from app.core.domain.symbol_usage import SymbolUsage
from app.core.ports.repositories import SymbolLegendExportRepository


class ExportSymbolLegendUseCase:
    """Export the symbol legend (icon, name, explanation - no counts) for students."""

    def __init__(self, export_repo: SymbolLegendExportRepository) -> None:
        """Args: export_repo: port implementation (PDF/PNG writer)."""
        self._export_repo = export_repo

    def execute(self, *, entries: Sequence[SymbolUsage], title: str, color_hex: str, output_path: Path) -> None:
        """Write ``entries`` (in their given order) to ``output_path``; the file type follows its extension."""
        self._export_repo.export_symbol_legend(entries=entries, title=title, color_hex=color_hex, output_path=output_path)
