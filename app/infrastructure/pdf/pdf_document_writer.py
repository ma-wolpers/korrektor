from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import fitz

KORREKTOR_STATS_PAGE_MARKER = "KORREKTOR_STATS_PAGE"
"""Annotation `subject` stamped onto a Korrektor-generated Statistikseite.

Read by `read_trailing_page_marker` so a caller can tell whether the last
page of a PDF is actually one Korrektor appended, rather than trusting
persisted JSON state (`StudentExam.stats_report_appended`) alone - the two
can disagree if the PDF was changed externally between sessions. Mirrors
the existing `KORREKTOR_MARKER:<annotation_id>` convention used for
correction annotations (`main_window_correction_markers_export.py`).
"""


def rewrite_pdf_atomically(pdf_path: Path, mutate: Callable[[fitz.Document], None]) -> None:
    """Open `pdf_path`, let `mutate` edit it in place, then atomically replace the original.

    The technical SSOT for every safe PDF rewrite in this codebase (both
    the correction-annotation burn-in and the Statistikseite append/
    remove flows build on this). Lifecycle is deliberately explicit,
    because Windows keeps an open file handle locked - `os.replace` must
    never run while the original `fitz.Document` is still open:

        open original -> mutate(...) -> save to a sibling temp file
        -> close the original document -> os.replace(temp, original)

    On any exception raised by `mutate` or `document.save`, the (still
    open) document is closed, the temp file is removed if it exists, the
    original is left completely untouched, and the exception is
    re-raised - this function never swallows errors; callers decide how
    to report/roll back (see `main_window_correction_markers_export.py`'s
    `failures` collection, or the Statistikseite controller's batch
    rollback).
    """
    temp_path = pdf_path.with_name(f"{pdf_path.stem}.korrektor.tmp.pdf")
    document: fitz.Document | None = None
    try:
        document = fitz.open(pdf_path)
        mutate(document)
        document.save(temp_path, garbage=4, deflate=True)
        document.close()
        document = None
        os.replace(temp_path, pdf_path)
    except Exception:
        if document is not None:
            try:
                document.close()
            except Exception:
                pass
            document = None
        try:
            if temp_path.exists():
                temp_path.unlink()
        except Exception:
            pass
        raise
    finally:
        if document is not None:
            try:
                document.close()
            except Exception:
                pass


def read_trailing_page_bytes(pdf_path: Path) -> bytes | None:
    """Return the last page of `pdf_path` as a standalone one-page PDF's bytes, or `None` if empty.

    Used to capture "what was there before" ahead of a mutation, so an
    undo/redo can restore the exact previous page byte-for-byte instead of
    recomputing anything.
    """
    document = fitz.open(pdf_path)
    try:
        if document.page_count == 0:
            return None
        extracted = fitz.open()
        try:
            extracted.insert_pdf(document, from_page=document.page_count - 1, to_page=document.page_count - 1)
            return extracted.tobytes()
        finally:
            extracted.close()
    finally:
        document.close()


def read_trailing_page_marker(pdf_path: Path) -> str | None:
    """Return the last page's Korrektor marker `subject`, or `None` if it has none.

    Purely a factual read - whether that means "consistent", "safe to
    replace", or "needs a diagnostic" is a decision for the caller
    (`ui_intent_controller_student_result_pdf_export.py`), not this
    module.
    """
    document = fitz.open(pdf_path)
    try:
        if document.page_count == 0:
            return None
        page = document.load_page(document.page_count - 1)
        for annot in page.annots() or []:
            info = annot.info or {}
            subject = str(info.get("subject", ""))
            if subject == KORREKTOR_STATS_PAGE_MARKER:
                return subject
        return None
    finally:
        document.close()


def append_marked_stats_page(pdf_path: Path, page_pdf_bytes: bytes, *, replace_existing: bool) -> None:
    """Append `page_pdf_bytes` as the last page, stamped with the Korrektor marker.

    Purely mechanical: if `replace_existing`, the current last page is
    deleted first; the new page is always inserted at the end and stamped
    with `KORREKTOR_STATS_PAGE_MARKER`. This function does not decide
    *whether* replacing is currently safe - the caller must already have
    established that (via `read_trailing_page_marker`) before calling
    this.
    """

    def _mutate(document: fitz.Document) -> None:
        if replace_existing and document.page_count > 0:
            document.delete_page(document.page_count - 1)
        source = fitz.open(stream=page_pdf_bytes, filetype="pdf")
        try:
            document.insert_pdf(source, from_page=0, to_page=0, start_at=-1)
        finally:
            source.close()
        page = document.load_page(document.page_count - 1)
        annot = page.add_text_annot(fitz.Point(2, 2), "")
        annot.set_info(title="Korrektor", subject=KORREKTOR_STATS_PAGE_MARKER, content="")
        annot.update()

    rewrite_pdf_atomically(pdf_path, _mutate)


def remove_trailing_page(pdf_path: Path) -> None:
    """Delete the last page, purely mechanically - no consistency check (see module docstring)."""

    def _mutate(document: fitz.Document) -> None:
        if document.page_count > 0:
            document.delete_page(document.page_count - 1)

    rewrite_pdf_atomically(pdf_path, _mutate)
