from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.domain.pdf_split_naming import SplitSection, build_split_sections
from app.infrastructure.pdf.pdf_merger import MergedSourceSpan
from app.infrastructure.pdf.pdf_sources import PdfSourceInfo

_LOG = logging.getLogger(__name__)

SplitCompleteCallback = Callable[[Path, dict[str, str]], None]
"""``on_split_complete(output_dir, {filename: display_name})`` - called once after a successful split."""


class ImportSplitSession:
    """State and rules of one running PDF import (Tk-free, so the keyboard semantics are unit-testable).

    Owns the merged ``fitz.Document`` from creation until `close()`. Page
    numbers are 1-indexed pages of the merged document (``current_page``,
    ``boundaries``, ``names`` keys) - PyMuPDF's 0-based indices never appear
    here. Page 1 always starts the first section and is never stored in
    ``boundaries``. ``names`` maps a section's start page to the name as
    typed; it only ever holds keys that are section starts.

    Binding rules (user decisions):

    - `mark_boundary` (Enter / checkbox on) starts a new section with an
      *empty* name.
    - `unmark_section_of` (Shift+Enter / checkbox off) removes the start of
      the section containing the page and discards that section's name; its
      pages join the previous section and therefore carry its name.
    """

    def __init__(
        self,
        document: Any,
        source_spans: list[MergedSourceSpan],
        on_split_complete: SplitCompleteCallback | None = None,
    ) -> None:
        """Take ownership of ``document`` (the merged PDF) and start on page 1.

        Args:
            document: Open ``fitz.Document``; closed by `close()`.
            source_spans: Where each source PDF ended up (for the origin display).
            on_split_complete: Bound for the whole session; ``None`` for the
                standalone wizard from the "Datei" menu.
        """
        self.document = document
        self.page_count = int(document.page_count)
        self.source_spans = list(source_spans)
        self.on_split_complete = on_split_complete
        self.current_page = 1
        self.boundaries: set[int] = set()
        self.names: dict[int, str] = {}
        self.closed = False

    @property
    def creates_exam(self) -> bool:
        """True when this import was started from "Neue Klausur" (a completion callback is bound)."""
        return self.on_split_complete is not None

    def sections(self) -> list[SplitSection]:
        """Return the current sections in document order (names stripped, see `build_split_sections`)."""
        return build_split_sections(self.page_count, self.boundaries, self.names)

    def section_start_for_page(self, page: int) -> int:
        """Return the start page of the section that contains ``page``."""
        return max((start for start in self.boundaries if start <= page), default=1)

    def section_for_page(self, page: int) -> SplitSection:
        """Return the section that contains ``page``."""
        start = self.section_start_for_page(page)
        return next(section for section in self.sections() if section.start_page == start)

    def go_to_page(self, page: int) -> bool:
        """Make ``page`` current if it exists and differs from the current page; return whether it changed."""
        if not (1 <= page <= self.page_count) or page == self.current_page:
            return False
        self.current_page = page
        return True

    def step_page(self, delta: int) -> bool:
        """Move by ``delta`` pages (no wrap-around); return whether the page changed."""
        return self.go_to_page(self.current_page + delta)

    def mark_boundary(self, page: int) -> bool:
        """Start a new section at ``page`` with an empty name; ``False`` if page 1 or already a start."""
        if page == 1 or page in self.boundaries or not (1 <= page <= self.page_count):
            return False
        self.boundaries.add(page)
        self.names.pop(page, None)
        return True

    def unmark_section_of(self, page: int) -> bool:
        """Undo the split that starts the section containing ``page``; ``False`` in the first section."""
        start = self.section_start_for_page(page)
        if start == 1:
            return False
        self.boundaries.discard(start)
        self.names.pop(start, None)
        return True

    def name_for_page(self, page: int) -> str:
        """Return the name (as typed) of the section that contains ``page``."""
        return self.names.get(self.section_start_for_page(page), "")

    def set_name_for_page(self, page: int, name: str) -> None:
        """Store ``name`` (as typed) for the section that contains ``page``; empty text removes it."""
        start = self.section_start_for_page(page)
        if name.strip():
            self.names[start] = name
        else:
            self.names.pop(start, None)

    def has_user_input(self) -> bool:
        """True once a split or a name was entered (closing then asks for confirmation)."""
        return bool(self.boundaries) or any(name.strip() for name in self.names.values())

    def source_span_for_page(self, page: int) -> MergedSourceSpan | None:
        """Return the source PDF span that contains ``page`` (``None`` only for an empty span list)."""
        return next((span for span in self.source_spans if span.first_page <= page <= span.last_page), None)

    def close(self) -> None:
        """Close the merged document once; later calls do nothing. Close errors are logged, never raised."""
        if self.closed:
            return
        self.closed = True
        try:
            self.document.close()
        except Exception:
            _LOG.exception("Import-Split: Schliessen des zusammengefuehrten PDFs fehlgeschlagen")


@dataclass
class ImportSplitPending:
    """The phase before a session: validated sources waiting in the order dialog.

    ``infos`` is the current merge order (already validated by
    ``inspect_pdf_sources``). ``popup``/``listbox`` are set once the dialog
    is built. Ended exactly by ``_end_import_split_pending``.
    """

    infos: list[PdfSourceInfo]
    on_split_complete: SplitCompleteCallback | None = None
    popup: Any = None
    listbox: Any = None
    binder: Any = None
