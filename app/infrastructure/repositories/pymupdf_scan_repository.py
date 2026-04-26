from __future__ import annotations

from pathlib import Path

import fitz

from app.core.ports.repositories import PdfScanRepository


class PyMuPdfScanRepository(PdfScanRepository):
    def scan_exam_folder(self, folder_path: Path) -> list[tuple[str, int]]:
        pdf_files = sorted(folder_path.glob("*.pdf"))
        entries: list[tuple[str, int]] = []
        for pdf_file in pdf_files:
            with fitz.open(pdf_file) as document:
                entries.append((pdf_file.name, document.page_count))
        return entries
