"""Human-readable names of correction marks for hints and dialogs - no raw content, no ids.

A symbol mark is named by its catalog label (``SYMBOL_BY_CONTENT``, e.g. "Richtig");
an older symbol that is no longer in the palette keeps its raw content (e.g. "△"),
exactly like the evaluation's symbol view (`symbol_usage.SymbolUsage.label`). A text
mark (comment, points/grade superposition) is shown as ``Text „…“``, shortened.
"""

from __future__ import annotations

from app.core.domain.mark_symbols import SYMBOL_BY_CONTENT
from app.core.domain.models import PdfAnnotation

_TEXT_PREVIEW = 30


def mark_label(annotation: PdfAnnotation) -> str:
    """"Richtig" for a catalog symbol, the raw content for an older symbol, ``Text „…“`` for text."""
    if annotation.annotation_type == "symbol":
        symbol = SYMBOL_BY_CONTENT.get(annotation.content)
        return symbol.label if symbol is not None else annotation.content
    text = " ".join(annotation.content.split())
    if len(text) > _TEXT_PREVIEW:
        text = text[: _TEXT_PREVIEW - 1].rstrip() + "…"
    return f"Text „{text}“"


def mark_location_line(annotation: PdfAnnotation, person: str) -> str:
    """One line naming person, page, sub-task and mark: "Anna, S. 2, Aufgabe 2C: Richtig"."""
    task = f"Aufgabe {annotation.task_code}" if annotation.task_code else "ohne Aufgabe"
    return f"{person}, S. {annotation.page_number}, {task}: {mark_label(annotation)}"
