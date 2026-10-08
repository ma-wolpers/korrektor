from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import fitz


@dataclass(frozen=True, slots=True)
class PdfSourceInfo:
    """A source PDF that passed inspection: readable, not password-protected, at least one page."""

    path: Path
    page_count: int


@dataclass(frozen=True, slots=True)
class PdfSourceProblem:
    """Why one selected source PDF cannot be imported (``reason`` is user-facing German text)."""

    path: Path
    reason: str


def describe_source_problem(document: fitz.Document) -> str | None:
    """Return a user-facing reason why an *opened* document cannot be imported, or ``None``.

    Shared by `inspect_pdf_sources` and the merger, so the inspection that
    feeds the order dialog and the later merge apply exactly the same rules:
    not a PDF (PyMuPDF also opens images), password-protected, or no pages.
    """
    if not document.is_pdf:
        return "keine PDF-Datei"
    if document.needs_pass:
        return "passwortgeschützt"
    if document.page_count < 1:
        return "enthält keine Seiten"
    return None


def inspect_pdf_sources(paths: Iterable[Path]) -> tuple[list[PdfSourceInfo], list[PdfSourceProblem]]:
    """Check every selected source PDF and return ``(valid_infos, problems)``.

    Inspects *all* files instead of stopping at the first problem, so the
    user gets one message listing every unusable file. Each file is opened
    and closed again inside this call (``try/finally`` per file) - nothing
    stays open. The result is a snapshot: a file changed afterwards is
    re-checked by the merge, which then fails with `PdfImportError`.

    Example: ``[ok.pdf, locked.pdf, ok2.pdf]`` -> two infos and one problem
    ``(locked.pdf, "passwortgeschützt")``.
    """
    infos: list[PdfSourceInfo] = []
    problems: list[PdfSourceProblem] = []
    for path in paths:
        try:
            document = fitz.open(path)
        except Exception as exc:
            problems.append(PdfSourceProblem(path, f"nicht lesbar ({exc})"))
            continue
        try:
            reason = describe_source_problem(document)
            if reason is None:
                infos.append(PdfSourceInfo(path, document.page_count))
            else:
                problems.append(PdfSourceProblem(path, reason))
        finally:
            close_quietly(document)
    return infos, problems


def close_quietly(document: fitz.Document | None) -> None:
    """Close ``document`` if given, ignoring errors (cleanup paths must never mask the real error)."""
    if document is None:
        return
    try:
        document.close()
    except Exception:
        pass
