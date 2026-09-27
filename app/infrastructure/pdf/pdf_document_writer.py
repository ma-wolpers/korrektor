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


def _save_and_replace_atomically(document: fitz.Document, target_path: Path) -> None:
    """Save `document` to a sibling temp file next to `target_path`, then atomically replace it.

    The shared core behind `rewrite_pdf_atomically` (target = the file the
    document was itself opened from) and `write_pdf_copy_atomically`
    (target = a different, new export destination) - both need the exact
    same "temp file next to the target, close before replace, clean up on
    error" mechanics, only the target path differs. Windows keeps an open
    file handle locked, so `os.replace` must never run while `document` is
    still open.

    On any exception, `document` is closed if still open, the temp file is
    removed if it exists, `target_path` is left completely untouched, and
    the exception is re-raised - this function never swallows errors.
    """
    temp_path = target_path.with_name(f"{target_path.stem}.korrektor.tmp.pdf")
    try:
        document.save(temp_path, garbage=4, deflate=True)
        document.close()
        os.replace(temp_path, target_path)
    except Exception:
        try:
            document.close()
        except Exception:
            pass
        try:
            if temp_path.exists():
                temp_path.unlink()
        except Exception:
            pass
        raise


def rewrite_pdf_atomically(pdf_path: Path, mutate: Callable[[fitz.Document], None]) -> None:
    """Open `pdf_path`, let `mutate` edit it in place, then atomically replace the original.

    The technical SSOT for every safe PDF rewrite in this codebase (both
    the correction-annotation burn-in and the Statistikseite append/
    remove flows build on this). Lifecycle is deliberately explicit:

        open original -> mutate(...) -> save to a sibling temp file
        -> close the original document -> os.replace(temp, original)

    (`_save_and_replace_atomically` performs the save/close/replace half;
    see its docstring for the error-handling contract, which applies here
    unchanged.) If `mutate` itself raises, the freshly opened document is
    closed and the exception re-raised before any temp file is even
    written - callers decide how to report/roll back (see
    `main_window_correction_markers_export.py`'s `failures` collection, or
    the Statistikseite controller's batch rollback).
    """
    document = fitz.open(pdf_path)
    try:
        mutate(document)
    except Exception:
        document.close()
        raise
    _save_and_replace_atomically(document, pdf_path)


def write_pdf_copy_atomically(
    source_path: Path, destination_path: Path, mutate: Callable[[fitz.Document], None] | None = None
) -> None:
    """Write a (optionally mutated) copy of `source_path` to `destination_path`, atomically.

    `source_path` is only ever read from - this function never writes
    back to it, unlike `rewrite_pdf_atomically` where source and target
    are the same file. Used by the zentraler Exportmodus
    (`ui_intent_controller_batch_export.py`): the Klausur's working PDF is
    the source, a freshly chosen export path is the destination, and
    `mutate` (when given) applies the export-specific Statistikseite
    replacement before the copy is written. Shares
    `_save_and_replace_atomically` with `rewrite_pdf_atomically` - no
    second, diverging write strategy. Creates `destination_path`'s parent
    directory (e.g. a per-student export subfolder) if it does not exist
    yet.
    """
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    document = fitz.open(source_path)
    try:
        if mutate is not None:
            mutate(document)
    except Exception:
        document.close()
        raise
    _save_and_replace_atomically(document, destination_path)


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


def stamp_marked_stats_page(document: fitz.Document, page_pdf_bytes: bytes, *, replace_existing: bool) -> None:
    """Insert `page_pdf_bytes` as `document`'s new last page, stamped with the Korrektor marker.

    Purely mechanical: if `replace_existing`, the current last page is
    deleted first; the new page is always inserted at the end and stamped
    with `KORREKTOR_STATS_PAGE_MARKER`. Does not decide *whether*
    replacing is currently safe - the caller must already have
    established that (via `read_trailing_page_marker`) before calling
    this. Shared between `append_marked_stats_page` (rewrites the
    Klausur-PDF itself) and the zentraler Exportmodus's export-copy
    mutation (`ui_intent_controller_batch_export.py`) - both need the
    identical "replace-or-append, then stamp" mechanics so an export copy
    carries the exact same marker convention as a PDF the append/remove
    feature itself produced.
    """
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


def append_marked_stats_page(pdf_path: Path, page_pdf_bytes: bytes, *, replace_existing: bool) -> None:
    """Append `page_pdf_bytes` as the last page of `pdf_path`, stamped with the Korrektor marker."""

    def _mutate(document: fitz.Document) -> None:
        stamp_marked_stats_page(document, page_pdf_bytes, replace_existing=replace_existing)

    rewrite_pdf_atomically(pdf_path, _mutate)


def remove_trailing_page(pdf_path: Path) -> None:
    """Delete the last page, purely mechanically - no consistency check (see module docstring)."""

    def _mutate(document: fitz.Document) -> None:
        if document.page_count > 0:
            document.delete_page(document.page_count - 1)

    rewrite_pdf_atomically(pdf_path, _mutate)
