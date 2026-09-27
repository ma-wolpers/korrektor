from __future__ import annotations

from pathlib import Path

import fitz


def split_pdf_by_ranges(
    source_path: Path, ranges: list[tuple[int, int]], output_dir: Path, *, name_prefix: str = "Abgabe"
) -> list[Path]:
    """Split `source_path` into one PDF per `(start, end)` range (1-indexed, inclusive), sequentially named.

    Sequential placeholder names (`f"{name_prefix}_{index:02d}.pdf"`) - the
    real per-student names are assigned later via the existing Namenmodus,
    once the split files have become an exam's students.

    Two safety guarantees, both because a half-finished split is worse
    than no split at all:
    - **Collision preflight**: every destination path is computed and
      checked for an already-existing file *before* anything is written.
      Any collision aborts the whole call (`FileExistsError`, naming the
      colliding files) - never a silent overwrite, never a `_2` suffix.
    - **All-or-nothing on a write failure**: if writing any range fails
      partway through, every split file already written by this call is
      deleted again before the exception propagates - never a state where
      e.g. `Abgabe_01.pdf`/`Abgabe_02.pdf` exist but `Abgabe_03.pdf` is
      missing because of a mid-run error.

    The source is only ever opened for reading; it is never written to.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    destinations = [output_dir / f"{name_prefix}_{index + 1:02d}.pdf" for index in range(len(ranges))]

    colliding = [path.name for path in destinations if path.exists()]
    if colliding:
        raise FileExistsError(
            "Diese Datei(en) existieren bereits im Zielordner und wuerden ueberschrieben: " + ", ".join(colliding)
        )

    written: list[Path] = []
    source = fitz.open(source_path)
    try:
        for destination, (start, end) in zip(destinations, ranges):
            new_document = None
            try:
                new_document = fitz.open()
                new_document.insert_pdf(source, from_page=start - 1, to_page=end - 1)
                new_document.save(destination)
            except Exception:
                if new_document is not None:
                    try:
                        new_document.close()
                    except Exception:
                        pass
                for already_written in written:
                    try:
                        already_written.unlink()
                    except OSError:
                        pass
                raise
            new_document.close()
            written.append(destination)
    finally:
        source.close()
    return written
