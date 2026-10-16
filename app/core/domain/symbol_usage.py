"""Which correction symbols an exam uses: counts per symbol, per submission and per task.

Contracts (see ``docs/ARCHITEKTUR.md`` "Auswertung"):

* Only ``annotation_type == "symbol"`` counts. Supersymbols are real symbols and count;
  comments and points/grade superpositions are ``"text"`` and do not.
* Only marks on the PDFs of the current persons (``student_pdfs``) count.
* ``count`` = number of marks (several in one submission count several times);
  ``submission_count`` = number of different submissions (``student_pdf``) with at least
  one such mark; ``task_codes`` = the distinct non-empty task codes, in task order.
  Each mark is counted once (deduplicated by ``annotation_id``).
* ``content`` is matched exactly against the catalog (``SYMBOL_BY_CONTENT``), no
  normalisation; unknown content (e.g. the removed △) is its own entry with
  ``symbol=None`` - it is never mapped onto a catalog symbol.
* Order: catalog symbols in palette order, then unknown contents by count (descending),
  ties by content - deterministic.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.core.domain.mark_symbols import MARK_SYMBOLS, SYMBOL_BY_CONTENT, MarkSymbol
from app.core.domain.models import PdfAnnotation

LEGACY_DESCRIPTION = "Älteres Symbol (nicht mehr in der Palette)"
_PALETTE_POSITION = {symbol.content: index for index, symbol in enumerate(MARK_SYMBOLS)}


@dataclass(frozen=True)
class SymbolUsage:
    """How one symbol content is used in the exam (see module contracts)."""

    content: str
    symbol: MarkSymbol | None
    count: int
    submission_count: int
    task_codes: tuple[str, ...]

    @property
    def label(self) -> str:
        """Catalog name, or the raw content for unknown (older) symbols."""
        return self.symbol.label if self.symbol is not None else self.content

    @property
    def description(self) -> str:
        """Catalog explanation, or the legacy explanation for unknown symbols."""
        return self.symbol.description if self.symbol is not None else LEGACY_DESCRIPTION


def _symbol_marks(annotations: Iterable[PdfAnnotation], student_pdfs: Iterable[str]) -> list[PdfAnnotation]:
    """Symbol marks of the current persons, each once (by ``annotation_id``)."""
    allowed = set(student_pdfs)
    seen: set[str] = set()
    marks = []
    for annotation in annotations:
        if annotation.annotation_type != "symbol" or annotation.student_pdf not in allowed:
            continue
        if annotation.annotation_id in seen:
            continue
        seen.add(annotation.annotation_id)
        marks.append(annotation)
    return marks


def _sort_key(usage: SymbolUsage) -> tuple[int, int, str]:
    """Palette order for catalog symbols; unknown ones after them by count, then content."""
    position = _PALETTE_POSITION.get(usage.content)
    if position is not None:
        return (0, position, "")
    return (1, -usage.count, usage.content)


def _usages(marks: Sequence[PdfAnnotation], task_order: Sequence[str]) -> list[SymbolUsage]:
    """Aggregate ``marks`` per content."""
    order = {code: index for index, code in enumerate(task_order)}
    grouped: dict[str, list[PdfAnnotation]] = {}
    for mark in marks:
        grouped.setdefault(mark.content, []).append(mark)
    usages = []
    for content, items in grouped.items():
        codes = {item.task_code for item in items if item.task_code}
        usages.append(
            SymbolUsage(
                content=content,
                symbol=SYMBOL_BY_CONTENT.get(content),
                count=len(items),
                submission_count=len({item.student_pdf for item in items}),
                task_codes=tuple(sorted(codes, key=lambda code: (order.get(code, len(order)), code))),
            )
        )
    return usages


def used_symbols(
    annotations: Iterable[PdfAnnotation], student_pdfs: Iterable[str], task_order: Sequence[str] = ()
) -> list[SymbolUsage]:
    """Every symbol used in at least one current submission (palette order, unknown last).

    Args:
        annotations: ``exam.pdf_annotations``.
        student_pdfs: PDF file names of ``exam.students``.
        task_order: ``exam.tasks`` codes, for ordering ``task_codes``.
    """
    return sorted(_usages(_symbol_marks(annotations, student_pdfs), task_order), key=_sort_key)


def symbols_for_task(
    annotations: Iterable[PdfAnnotation], student_pdfs: Iterable[str], task_code: str, limit: int = 5
) -> list[SymbolUsage]:
    """The ``limit`` most frequent symbols of one task: by count, then palette order, then content."""
    marks = [mark for mark in _symbol_marks(annotations, student_pdfs) if mark.task_code == task_code]
    usages = _usages(marks, (task_code,))
    return sorted(usages, key=lambda usage: (-usage.count, *_sort_key(usage)))[:limit]
