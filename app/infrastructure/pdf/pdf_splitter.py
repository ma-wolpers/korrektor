from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

import fitz

from app.infrastructure.pdf.pdf_sources import close_quietly


class SplitOutputSpec(Protocol):
    """What `write_split_outputs` needs per output file (e.g. the domain's ``PlannedSplitFile``).

    ``page_ranges`` are 1-indexed, inclusive ``(start, end)`` pages of the
    source document, written in the given order.
    """

    filename: str
    page_ranges: Sequence[tuple[int, int]]


class SplitWriteError(Exception):
    """Writing a split output failed; everything already written was rolled back as far as possible.

    ``cause`` is the original exception. ``leftover_files`` lists files of
    this call that could not be deleted during rollback (empty when the
    rollback was complete) - the GUI tells the user to check them.
    """

    def __init__(self, cause: BaseException, leftover_files: list[Path]) -> None:
        """Store the original error and the files the rollback could not remove."""
        super().__init__(str(cause))
        self.cause = cause
        self.leftover_files = leftover_files


def write_split_outputs(
    source_document: fitz.Document, outputs: Sequence[SplitOutputSpec], output_dir: Path
) -> list[Path]:
    """Write one PDF per output spec from ``source_document`` into ``output_dir``; return the written paths.

    An output may consist of several page ranges (sections with the same
    name merged into one file); they are appended in the given order.

    Guarantees, because a half-finished split is worse than none:

    - **Input check first**: duplicate filenames (case-insensitive, as on
      Windows), outputs without ranges and ranges outside the document raise
      ``ValueError`` before anything is written.
    - **Collision preflight**: if any destination already exists, nothing is
      written and `FileExistsError` names the colliding files - never a
      silent overwrite.
    - **All or nothing**: if writing any output fails, every file written by
      this call (including a partially saved one) is deleted again and
      `SplitWriteError` is raised; files that could not be deleted are
      reported in ``leftover_files`` instead of being silently ignored.

    Ownership: ``source_document`` belongs to the caller and is only read,
    never closed; every target document created here is always closed.
    Only page content and order are copied (``links=False, widgets=False``).
    PyMuPDF's 0-based page indices are confined to this function.
    """
    _validate_outputs(source_document.page_count, outputs)
    output_dir.mkdir(parents=True, exist_ok=True)
    destinations = [output_dir / output.filename for output in outputs]

    colliding = [path.name for path in destinations if path.exists()]
    if colliding:
        raise FileExistsError(
            "Diese Datei(en) existieren bereits im Zielordner und wuerden ueberschrieben: " + ", ".join(colliding)
        )

    written: list[Path] = []
    for destination, output in zip(destinations, outputs):
        new_document = None
        try:
            new_document = fitz.open()
            _copy_ranges(new_document, source_document, output.page_ranges)
            new_document.save(destination)
        except Exception as exc:
            close_quietly(new_document)
            leftovers = _remove_files([*written, destination])
            raise SplitWriteError(exc, leftovers) from exc
        close_quietly(new_document)
        written.append(destination)
    return written


def _copy_ranges(target: fitz.Document, source: fitz.Document, page_ranges: Sequence[tuple[int, int]]) -> None:
    """Append the 1-indexed inclusive ``page_ranges`` of ``source`` to ``target``.

    ``final=False`` keeps PyMuPDF's graft map (source objects/resources
    already copied into ``target`` and their target xrefs) alive until the
    last range of the same source, so shared resources are referenced again
    instead of being copied once per range. It is an optimization only;
    correctness does not depend on it.
    """
    last_index = len(page_ranges) - 1
    for index, (start, end) in enumerate(page_ranges):
        target.insert_pdf(
            source,
            from_page=start - 1,
            to_page=end - 1,
            links=False,
            widgets=False,
            final=index == last_index,
        )


def _validate_outputs(page_count: int, outputs: Sequence[SplitOutputSpec]) -> None:
    """Reject duplicate filenames, empty outputs and out-of-document ranges before anything is written."""
    seen: set[str] = set()
    for output in outputs:
        key = output.filename.casefold()
        if key in seen:
            raise ValueError(f"Doppelter Ziel-Dateiname: {output.filename}")
        seen.add(key)
        if not output.page_ranges:
            raise ValueError(f"Keine Seiten fuer {output.filename}.")
        for start, end in output.page_ranges:
            if not (1 <= start <= end <= page_count):
                raise ValueError(f"Ungueltiger Seitenbereich {start}-{end} fuer {output.filename} (1..{page_count}).")


def _remove_files(paths: list[Path]) -> list[Path]:
    """Delete ``paths`` where present; return the ones that still exist afterwards."""
    leftovers: list[Path] = []
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        if path.exists():
            leftovers.append(path)
    return leftovers


class _SequentialOutput:
    """Output spec with a sequential placeholder name, used only by `split_pdf_by_ranges`."""

    def __init__(self, filename: str, page_range: tuple[int, int]) -> None:
        self.filename = filename
        self.page_ranges = (page_range,)


def split_pdf_by_ranges(
    source_path: Path, ranges: list[tuple[int, int]], output_dir: Path, *, name_prefix: str = "Abgabe"
) -> list[Path]:
    """Transitional wrapper for the current import wizard: one ``{name_prefix}_NN.pdf`` per range.

    Removed again once the wizard writes named outputs via
    `write_split_outputs` directly (Importmodus step 4). Opens and closes
    ``source_path`` itself; all guarantees are those of `write_split_outputs`.
    """
    outputs = [_SequentialOutput(f"{name_prefix}_{index + 1:02d}.pdf", page_range) for index, page_range in enumerate(ranges)]
    source = fitz.open(source_path)
    try:
        return write_split_outputs(source, outputs, output_dir)
    finally:
        close_quietly(source)
