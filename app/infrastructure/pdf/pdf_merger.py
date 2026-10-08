from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import fitz

from app.infrastructure.pdf.pdf_sources import close_quietly, describe_source_problem


@dataclass(frozen=True, slots=True)
class MergedSourceSpan:
    """Where one source PDF ended up in the merged document.

    ``first_page``/``last_page`` are 1-indexed pages of the merged document,
    inclusive - the same convention as the split planning. Used for the
    "aus scan_02.pdf, S. 3/20" origin display.
    """

    path: Path
    first_page: int
    last_page: int

    @property
    def page_count(self) -> int:
        """Number of pages this source contributed."""
        return self.last_page - self.first_page + 1

    def local_page(self, page: int) -> int:
        """Translate a merged-document page (1-indexed) into this source's own page number."""
        return page - self.first_page + 1


class PdfImportError(Exception):
    """A source PDF could not be merged; ``path`` and user-facing ``reason`` name the culprit."""

    def __init__(self, path: Path, reason: str) -> None:
        """Store the failing file and the German reason shown to the user."""
        super().__init__(f"{path.name}: {reason}")
        self.path = path
        self.reason = reason


def open_merged_pdf(paths: Sequence[Path]) -> tuple[fitz.Document, list[MergedSourceSpan]]:
    """Merge ``paths`` in the given order into one new in-memory document and return it with its spans.

    Ownership: the returned document belongs to the caller, who must close
    it. Every source is opened and closed inside this call; if any source
    fails (unreadable, password-protected, no pages, or an error while
    copying), the partially built merged document is closed as well and
    `PdfImportError` names the file - nothing leaks on the error path.

    Merge semantics (binding): only page content and page order are
    guaranteed. Links and form fields are deliberately not copied
    (``links=False, widgets=False``); bookmarks, metadata, attachments and
    annotations are neither promised nor tested. The whole merge happens in
    memory and blocks the caller - an accepted limit for the expected size
    of about 800 pages.

    The page numbers of the returned spans are 1-indexed and inclusive
    (PyMuPDF's 0-based indices never leave this function).
    """
    if not paths:
        raise ValueError("open_merged_pdf braucht mindestens eine Datei.")
    merged = fitz.open()
    spans: list[MergedSourceSpan] = []
    try:
        next_first_page = 1
        for path in paths:
            page_count = _append_source(merged, path)
            spans.append(MergedSourceSpan(path, next_first_page, next_first_page + page_count - 1))
            next_first_page += page_count
    except BaseException:
        close_quietly(merged)
        raise
    return merged, spans


def _append_source(merged: fitz.Document, path: Path) -> int:
    """Copy all pages of ``path`` to the end of ``merged`` and return how many were copied.

    Re-validates the source with `describe_source_problem` (the earlier
    inspection is only a snapshot) and always closes it again.
    """
    try:
        source = fitz.open(path)
    except Exception as exc:
        raise PdfImportError(path, f"nicht lesbar ({exc})") from exc
    try:
        problem = describe_source_problem(source)
        if problem is not None:
            raise PdfImportError(path, problem)
        page_count = source.page_count
        try:
            merged.insert_pdf(source, links=False, widgets=False)
        except Exception as exc:
            raise PdfImportError(path, f"Zusammenführen fehlgeschlagen ({exc})") from exc
        return page_count
    finally:
        close_quietly(source)
