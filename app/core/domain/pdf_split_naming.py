from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from app.core.domain.pdf_split_planning import compute_split_ranges
from app.infrastructure.repositories.file_utils import build_pdf_filename_from_name

PageRange = tuple[int, int]
"""1-indexed, inclusive ``(start_page, end_page)`` - same convention as `compute_split_ranges`."""


@dataclass(frozen=True, slots=True)
class SplitSection:
    """One Abgabe-Abschnitt of the (merged) import document.

    Page numbers follow the Korrektor import convention: 1-indexed pages of
    the whole (merged) document, ``end_page`` inclusive. ``name`` is the name
    as entered (outer whitespace stripped); ``""`` means "not named yet".
    """

    start_page: int
    end_page: int
    name: str


@dataclass(frozen=True, slots=True)
class PlannedSplitFile:
    """One output PDF of a split.

    ``page_ranges`` are in document order; more than one range means that
    several sections with the same name key were merged into this file.
    ``uses_fallback_name`` marks a placeholder name (``Abgabe_NN``) for an
    unnamed section or one whose name yields no valid filename.
    """

    filename: str
    display_name: str
    page_ranges: tuple[PageRange, ...]
    uses_fallback_name: bool


@dataclass(frozen=True, slots=True)
class SplitFilePlan:
    """Result of `plan_split_files`: what will be written, plus what the user must be told.

    - ``files``: every output file, ordered by its first page.
    - ``fallback_sections``: sections without a name (get ``Abgabe_NN``).
    - ``invalid_name_sections``: sections whose name sanitizes to nothing
      (e.g. ``"???"``); they also get a fallback name.
    - ``merged_groups``: sections combined into one file because their names
      share a name key (only groups with more than one section).
    - ``suffixed_files``: files that got a ``_2``/``_3`` suffix because a
      *different* name produced the same filename after sanitizing.
    """

    files: tuple[PlannedSplitFile, ...]
    fallback_sections: tuple[SplitSection, ...]
    invalid_name_sections: tuple[SplitSection, ...]
    merged_groups: tuple[tuple[SplitSection, ...], ...]
    suffixed_files: tuple[PlannedSplitFile, ...]

    @property
    def needs_fallback_confirmation(self) -> bool:
        """True when some section is exported under a placeholder name (wish: warn before export)."""
        return bool(self.fallback_sections or self.invalid_name_sections)


def build_split_sections(
    page_count: int, boundary_pages: Iterable[int], name_by_start_page: Mapping[int, str]
) -> list[SplitSection]:
    """Turn boundaries plus per-start-page names into ordered `SplitSection` objects.

    Reuses `compute_split_ranges` (page 1 is always an implicit boundary,
    out-of-range boundaries raise ``ValueError``). Names are looked up by the
    section's start page; a name stored for a page that is not a section
    start is ignored defensively (the import session removes such names when
    a split is undone, so this only guards against stale state).

    Example: ``build_split_sections(6, {4}, {1: "Anna", 4: " Ben "})`` ->
    ``[SplitSection(1, 3, "Anna"), SplitSection(4, 6, "Ben")]``.
    """
    ranges = compute_split_ranges(page_count, set(boundary_pages))
    return [SplitSection(start, end, name_by_start_page.get(start, "").strip()) for start, end in ranges]


def section_name_key(name: str) -> str:
    """Return the comparison key that decides whether two sections belong together.

    Case-insensitive (``casefold``) with collapsed whitespace - nothing else.
    Deliberately *not* the sanitized filename: ``"Anna?"`` and ``"Anna"``
    have different keys (different names) even though both sanitize to
    ``Anna.pdf``; that collision is resolved with a suffix, never a merge.
    An empty key means "unnamed".
    """
    return " ".join(name.split()).casefold()


def find_other_sections_with_name(
    sections: Iterable[SplitSection], name: str, *, exclude_start_page: int
) -> list[SplitSection]:
    """Return the sections - other than the one starting at ``exclude_start_page`` - sharing ``name``'s key.

    Feeds the live hint shown while a name is typed ("gibt es schon bei
    Seiten 2-6 und 13-19"). An empty name has no duplicates.
    """
    key = section_name_key(name)
    if not key:
        return []
    return [
        section
        for section in sections
        if section.start_page != exclude_start_page and section_name_key(section.name) == key
    ]


def plan_split_files(sections: Iterable[SplitSection], *, fallback_prefix: str = "Abgabe") -> SplitFilePlan:
    """Plan the output files of a split: merging, fallback names and filename collisions.

    Rules (binding, see the Korrektor import contract V8):

    1. Named sections are grouped by `section_name_key`, in order of first
       appearance; the group's display name is the first occurrence's name
       as entered. All its page ranges go into one file, in document order.
    2. The filename comes from `build_pdf_filename_from_name` (Namenmodus
       convention, e.g. ``Anna_Müller.pdf``). A name that sanitizes to
       nothing is treated like a missing name and reported in
       ``invalid_name_sections``.
    3. Unnamed (and invalid) sections are never merged with each other:
       each gets ``f"{fallback_prefix}_{NN}"`` where NN is its 1-based
       position among all sections.
    4. Filenames are made unique case-insensitively (Windows): a later
       colliding name gets ``_2``, ``_3``, ... (as in
       `plan_target_filenames`). Explicit names are resolved before
       fallback names, so a real name never loses its plain filename to a
       placeholder.

    Example: sections "Anna" (1-2), "" (3-4), "anna" (5-6) -> files
    ``Anna.pdf`` with ranges ``((1, 2), (5, 6))`` and ``Abgabe_02.pdf``.
    """
    ordered = sorted(sections, key=lambda section: section.start_page)
    groups: dict[str, list[SplitSection]] = {}
    fallback_sections: list[SplitSection] = []
    invalid_sections: list[SplitSection] = []
    for section in ordered:
        key = section_name_key(section.name)
        if not key:
            fallback_sections.append(section)
        elif build_pdf_filename_from_name(section.name) is None:
            invalid_sections.append(section)
        else:
            groups.setdefault(key, []).append(section)

    used_filenames: set[str] = set()
    suffixed: list[PlannedSplitFile] = []
    planned: list[PlannedSplitFile] = []

    def _add(base_filename: str, display_name: str, members: list[SplitSection], uses_fallback: bool) -> None:
        filename = _unique_filename(base_filename, used_filenames)
        planned_file = PlannedSplitFile(
            filename=filename,
            display_name=display_name,
            page_ranges=tuple((member.start_page, member.end_page) for member in members),
            uses_fallback_name=uses_fallback,
        )
        planned.append(planned_file)
        if filename != base_filename:
            suffixed.append(planned_file)

    for members in groups.values():
        display_name = members[0].name
        _add(build_pdf_filename_from_name(display_name), display_name, members, False)

    position_by_start = {section.start_page: index + 1 for index, section in enumerate(ordered)}
    for section in sorted(fallback_sections + invalid_sections, key=lambda item: item.start_page):
        display_name = f"{fallback_prefix}_{position_by_start[section.start_page]:02d}"
        _add(f"{display_name}.pdf", display_name, [section], True)

    planned.sort(key=lambda planned_file: planned_file.page_ranges[0][0])
    return SplitFilePlan(
        files=tuple(planned),
        fallback_sections=tuple(fallback_sections),
        invalid_name_sections=tuple(invalid_sections),
        merged_groups=tuple(tuple(members) for members in groups.values() if len(members) > 1),
        suffixed_files=tuple(suffixed),
    )


def _unique_filename(filename: str, used_casefolded: set[str]) -> str:
    """Return ``filename`` or the first free ``stem_N.pdf`` (N >= 2), compared case-insensitively.

    Records the returned name in ``used_casefolded``.
    """
    stem, dot, extension = filename.rpartition(".")
    candidate = filename
    suffix = 2
    while candidate.casefold() in used_casefolded:
        candidate = f"{stem}_{suffix}{dot}{extension}"
        suffix += 1
    used_casefolded.add(candidate.casefold())
    return candidate
