"""Klausur-Zuordnung im PDF-Import: which exam each Abgabe-Abschnitt belongs to, and where it is written.

One stack of scans may hold several exams (e.g. 10a and 10b). Every section
of the import document belongs to exactly one *group* (= one future exam
folder). Groups are addressed by a 0-based index into the session's list of
group names; the GUI shows them 1-based ("Klausur 1" … "Klausur 9").

Assignment model (user decision "Wechsel gilt ab hier"): the assignment is a
*switch marker* on a section start page. A section belongs to the group of
the last marker at or before its start; without any marker everything is
group 0. Setting a marker therefore changes the current section *and all
following sections* up to the next marker. Markers are kept normalized
(`normalize_switches`): only on section starts, and only where the group
actually changes - so a redundant later marker disappears when an earlier one
makes it superfluous.

Folder rule: if only one group has sections, the split is written straight
into the chosen target folder exactly as before (folder ``""``). With two or
more used groups, every used group gets a subfolder named after the group
(`folder_name_for`, Windows-safe via the shared `sanitize_filename_stem`).

Per group the unchanged `plan_split_files` decides merging, placeholder names
and filename suffixes - so equal names are only merged *within* one exam and
``Abgabe_NN`` counts per exam.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Literal

from app.core.domain.pdf_split_naming import PlannedSplitFile, SplitFilePlan, SplitSection, plan_split_files
from app.infrastructure.repositories.file_utils import sanitize_filename_stem

MAX_GROUPS = 9
"""Upper bound of groups per import - one per digit key Ctrl+1 … Ctrl+9."""

GroupNameProblem = Literal["invalid", "duplicate", "too_many"]
"""Why a group name was rejected (wording lives in the GUI texts module)."""


def default_group_name(index: int) -> str:
    """Name a group gets until the user renames it: ``0`` -> ``"Klausur 1"``."""
    return f"Klausur {index + 1}"


def folder_name_for(group_name: str) -> str | None:
    """Windows-safe folder name of a group (spaces kept); ``None`` if nothing valid remains."""
    return sanitize_filename_stem(group_name, replace_spaces_with=None)


def group_name_problem(
    name: str, existing_names: Sequence[str], *, exclude_index: int | None = None
) -> GroupNameProblem | None:
    """Check a new or renamed group name; ``None`` means acceptable.

    Args:
        name: The name as typed.
        existing_names: Current group names (index = group index).
        exclude_index: The group being renamed (its own name never counts
            as a duplicate); ``None`` when a new group is added.

    Returns:
        ``"invalid"`` if the name yields no folder name, ``"duplicate"`` if
        another group already has the same folder name (case-insensitive,
        as on Windows), ``"too_many"`` if a new group would exceed
        `MAX_GROUPS`, else ``None``.
    """
    if exclude_index is None and len(existing_names) >= MAX_GROUPS:
        return "too_many"
    folder = folder_name_for(name)
    if folder is None:
        return "invalid"
    for index, other in enumerate(existing_names):
        other_folder = folder_name_for(other)
        if index != exclude_index and other_folder is not None and other_folder.casefold() == folder.casefold():
            return "duplicate"
    return None


def group_for_start(start_page: int, switches: Mapping[int, int]) -> int:
    """Group index of the section starting at ``start_page``: the last marker at or before it, else 0."""
    candidates = [page for page in switches if page <= start_page]
    return switches[max(candidates)] if candidates else 0


def normalize_switches(switches: Mapping[int, int], section_starts: Iterable[int]) -> dict[int, int]:
    """Keep only markers on section starts where the group changes (see module docstring).

    Markers on pages that are no section start are dropped defensively (the
    session removes them when a split is undone, so this only guards
    against stale state).

    Example: starts ``1, 4, 7``, markers ``{4: 1, 7: 1}`` -> ``{4: 1}``.
    """
    normalized: dict[int, int] = {}
    current = 0
    for start in sorted(set(section_starts)):
        wanted = switches.get(start, current)
        if wanted != current:
            normalized[start] = wanted
        current = wanted
    return normalized


def assign_group(
    start_page: int, group_index: int, switches: Mapping[int, int], section_starts: Iterable[int]
) -> dict[int, int]:
    """Return the markers after assigning the section at ``start_page`` (and all following) to ``group_index``."""
    updated = dict(switches)
    updated[start_page] = group_index
    return normalize_switches(updated, section_starts)


def drop_section_start(start_page: int, switches: Mapping[int, int], remaining_starts: Iterable[int]) -> dict[int, int]:
    """Return the markers after the section start ``start_page`` was removed (split undone).

    The merged pages join the previous section and its group. A marker that
    sat on the removed start moves to the next section start (unless that
    one has its own marker), so the *following* sections keep their group -
    undoing a split never silently moves later Abgaben to another exam.
    """
    starts = sorted(set(remaining_starts))
    updated = dict(switches)
    moved = updated.pop(start_page, None)
    following = [page for page in starts if page > start_page]
    if moved is not None and following and following[0] not in updated:
        updated[following[0]] = moved
    return normalize_switches(updated, starts)


def section_counts(sections: Iterable[SplitSection], switches: Mapping[int, int], group_count: int) -> list[int]:
    """Number of sections per group index ``0 … group_count-1`` (for the Klausur bar)."""
    counts = [0] * group_count
    for section in sections:
        index = group_for_start(section.start_page, switches)
        if 0 <= index < group_count:
            counts[index] += 1
    return counts


@dataclass(frozen=True, slots=True)
class SplitGroupPlan:
    """The split plan of one used group.

    ``folder`` is the subfolder below the target folder (``""`` = the
    target folder itself, i.e. only one group is used). ``plan.files``
    carry plain filenames (as `CreateExamUseCase` needs them).
    """

    index: int
    name: str
    folder: str
    sections: tuple[SplitSection, ...]
    plan: SplitFilePlan

    def relative_path(self, filename: str) -> str:
        """``"Anna.pdf"`` -> ``"Bio 10b/Anna.pdf"`` (unchanged when ``folder`` is empty)."""
        return f"{self.folder}/{filename}" if self.folder else filename


@dataclass(frozen=True, slots=True)
class GroupedSplitPlan:
    """Result of `plan_grouped_split`: one `SplitGroupPlan` per used group, in group order.

    The aggregate properties mirror `SplitFilePlan` so the wizard texts work
    on either; their files carry the *relative* path (``"Bio 10b/Anna.pdf"``)
    as ``filename`` and are exactly what `write_split_outputs` gets.
    """

    groups: tuple[SplitGroupPlan, ...]

    @property
    def uses_subfolders(self) -> bool:
        """True when more than one group has sections (each gets its own folder)."""
        return len(self.groups) > 1

    @property
    def files(self) -> tuple[PlannedSplitFile, ...]:
        """Every output file with its relative path, grouped by exam, each group in page order."""
        return tuple(
            replace(planned, filename=group.relative_path(planned.filename))
            for group in self.groups
            for planned in group.plan.files
        )

    @property
    def fallback_sections(self) -> tuple[SplitSection, ...]:
        """Unnamed sections of all groups."""
        return tuple(section for group in self.groups for section in group.plan.fallback_sections)

    @property
    def invalid_name_sections(self) -> tuple[SplitSection, ...]:
        """Sections of all groups whose name yields no filename."""
        return tuple(section for group in self.groups for section in group.plan.invalid_name_sections)

    @property
    def merged_groups(self) -> tuple[tuple[SplitSection, ...], ...]:
        """Merged name groups of all exams (equal names are only merged within one exam)."""
        return tuple(members for group in self.groups for members in group.plan.merged_groups)

    @property
    def suffixed_files(self) -> tuple[PlannedSplitFile, ...]:
        """Files of all groups that got a ``_2``/``_3`` suffix, with relative path."""
        return tuple(
            replace(planned, filename=group.relative_path(planned.filename))
            for group in self.groups
            for planned in group.plan.suffixed_files
        )

    @property
    def needs_fallback_confirmation(self) -> bool:
        """True when some section of any group is exported under a placeholder name."""
        return bool(self.fallback_sections or self.invalid_name_sections)

    def group_of(self, section: SplitSection) -> SplitGroupPlan | None:
        """The group plan that contains ``section`` (``None`` for an unknown section)."""
        return next((group for group in self.groups if section in group.sections), None)


def plan_grouped_split(
    sections: Iterable[SplitSection], switches: Mapping[int, int], group_names: Sequence[str]
) -> GroupedSplitPlan:
    """Plan a split over several exams: group the sections, then `plan_split_files` per group.

    A marker pointing past ``group_names`` (stale state) falls back to
    `default_group_name`; a name without a valid folder name falls back to
    the folder of that default name - both only defensively, the session
    validates names when they are entered.

    Example: sections 1-2 "Anna", 3-4 "Ben", markers ``{3: 1}``, names
    ``["10a", "10b"]`` -> groups ``10a`` (``10a/Anna.pdf``) and ``10b``
    (``10b/Ben.pdf``).
    """
    by_group: dict[int, list[SplitSection]] = {}
    for section in sorted(sections, key=lambda item: item.start_page):
        by_group.setdefault(group_for_start(section.start_page, switches), []).append(section)
    multiple = len(by_group) > 1
    groups = []
    for index in sorted(by_group):
        name = group_names[index] if 0 <= index < len(group_names) else default_group_name(index)
        folder = (folder_name_for(name) or folder_name_for(default_group_name(index)) or "") if multiple else ""
        members = tuple(by_group[index])
        groups.append(SplitGroupPlan(index=index, name=name, folder=folder, sections=members, plan=plan_split_files(members)))
    return GroupedSplitPlan(groups=tuple(groups))
