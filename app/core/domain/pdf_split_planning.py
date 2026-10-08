from __future__ import annotations


def compute_split_ranges(total_pages: int, boundary_pages: set[int]) -> list[tuple[int, int]]:
    """Turn "pages where a new Abgabe begins" into contiguous, 1-indexed, inclusive page ranges.

    `boundary_pages` are 1-indexed page numbers where a new Abgabe starts;
    page 1 always counts as the first boundary implicitly, whether or not
    it is present in `boundary_pages` - a document is never split into
    zero Abgaben. Duplicate and unsorted boundaries are accepted and
    normalized; every boundary must satisfy `1 <= page <= total_pages`,
    otherwise this raises `ValueError` rather than silently clamping or
    ignoring it - a boundary outside the document is a real input error
    (e.g. a stale mark from a previously loaded, longer PDF), not a case
    worth guessing about.

    Example: `compute_split_ranges(10, {1, 4, 8})` -> `[(1, 3), (4, 7), (8, 10)]`.
    """
    if total_pages < 1:
        raise ValueError(f"total_pages muss mindestens 1 sein, war {total_pages}.")
    for page in boundary_pages:
        if not (1 <= page <= total_pages):
            raise ValueError(
                f"Ungültige Abgabe-Grenze: Seite {page} liegt außerhalb des Dokuments (1..{total_pages})."
            )

    boundaries = sorted({1, *boundary_pages})
    ranges: list[tuple[int, int]] = []
    for index, start in enumerate(boundaries):
        end = boundaries[index + 1] - 1 if index + 1 < len(boundaries) else total_pages
        ranges.append((start, end))
    return ranges
