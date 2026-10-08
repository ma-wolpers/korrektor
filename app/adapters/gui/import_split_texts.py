"""German user-facing texts of the PDF import wizard (presentation only, Tk-free and unit-tested).

Kept out of the domain on purpose: these functions produce concrete UI
wording ("Seiten 2-6 und 13-19"), not import rules. All page numbers are
1-indexed pages of the (merged) import document, as everywhere in the
import flow.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from app.core.domain.pdf_split_naming import SplitFilePlan, SplitSection
from app.infrastructure.pdf.pdf_merger import MergedSourceSpan
from app.infrastructure.pdf.pdf_sources import PdfSourceProblem

KEY_HELP_TEXT = "←/→ Seite · Enter: hier aufteilen · Shift+Enter: zurücknehmen · ↑/↓ Bild↑/↓ Vorschau"
ALREADY_RUNNING_TEXT = "Es läuft bereits ein PDF-Import. Bitte erst abschließen oder schließen."
_MAX_LISTED = 12


def format_range(start: int, end: int) -> str:
    """``(4, 7)`` -> ``"4-7"``, ``(9, 9)`` -> ``"9"``."""
    return str(start) if start == end else f"{start}-{end}"


def format_page_ranges(ranges: Sequence[tuple[int, int]]) -> str:
    """Join ranges into German prose: ``"Seite 9"``, ``"Seiten 2-6 und 13-19"``, ``"Seiten 1-2, 5 und 9-10"``."""
    parts = [format_range(start, end) for start, end in ranges]
    if not parts:
        return ""
    is_single_page = len(ranges) == 1 and ranges[0][0] == ranges[0][1]
    prefix = "Seite" if is_single_page else "Seiten"
    if len(parts) == 1:
        return f"{prefix} {parts[0]}"
    return f"{prefix} {', '.join(parts[:-1])} und {parts[-1]}"


def section_label(section: SplitSection) -> str:
    """Short label of a section, e.g. ``"S. 4-7"``."""
    return f"S. {format_range(section.start_page, section.end_page)}"


def name_caption(section: SplitSection) -> str:
    """Caption in front of the name field, e.g. ``"Name (Abgabe S. 4-7):"``."""
    return f"Name (Abgabe {section_label(section)}):"


def origin_text(page: int, page_count: int, span: MergedSourceSpan | None, *, multiple_sources: bool) -> str:
    """Header line: ``"Seite 5/40"``, with several sources ``"Seite 5/40 · aus scan_02.pdf, S. 3/20"``."""
    text = f"Seite {page}/{page_count}"
    if multiple_sources and span is not None:
        text += f" · aus {span.path.name}, S. {span.local_page(page)}/{span.page_count}"
    return text


def duplicate_hint(other_sections: Sequence[SplitSection]) -> str:
    """Live hint while typing a name that other sections already use (single line on purpose)."""
    ranges = [(section.start_page, section.end_page) for section in other_sections]
    return f"⚠ Diesen Namen gibt es schon ({format_page_ranges(ranges)}) – wird beim Aufteilen zusammengeführt"


def invalid_name_hint() -> str:
    """Live hint for a name that sanitizes to no valid filename."""
    return "⚠ Ergibt keinen gültigen Dateinamen – wird mit Ersatznamen gespeichert"


def counter_text(section_count: int, plan: SplitFilePlan) -> str:
    """Navigation bar summary, e.g. ``"5 Abgaben · 2 ohne Namen · 1 Name doppelt"``."""
    parts = [f"{section_count} Abgabe" + ("" if section_count == 1 else "n")]
    unnamed = len(plan.fallback_sections) + len(plan.invalid_name_sections)
    if unnamed:
        parts.append(f"{unnamed} ohne gültigen Namen")
    if plan.merged_groups:
        count = len(plan.merged_groups)
        parts.append(f"{count} Name{'' if count == 1 else 'n'} doppelt")
    return " · ".join(parts)


def section_status(section: SplitSection, plan: SplitFilePlan) -> str:
    """Status column of the section list: ohne Namen / ungültig / zusammengeführt / empty."""
    if section in plan.fallback_sections:
        return "ohne Namen"
    if section in plan.invalid_name_sections:
        return "ungültig"
    if any(section in group for group in plan.merged_groups):
        return "zusammengeführt"
    return ""


def fallback_warning_text(plan: SplitFilePlan) -> str:
    """Confirmation text before exporting with placeholder names (wish 3a)."""
    lines = []
    for planned in plan.files:
        if planned.uses_fallback_name:
            lines.append(f"• {format_page_ranges(planned.page_ranges)} → {planned.filename}")
    shown = lines[:_MAX_LISTED]
    if len(lines) > len(shown):
        shown.append(f"… und {len(lines) - len(shown)} weitere")
    return (
        "Diese Abschnitte haben keinen (gültigen) Namen und werden mit Ersatznamen gespeichert:\n\n"
        + "\n".join(shown)
        + "\n\nTrotzdem aufteilen?"
    )


def source_problems_text(problems: Sequence[PdfSourceProblem]) -> str:
    """Error text listing every unusable source PDF (nothing is imported)."""
    lines = [f"• {problem.path.name}: {problem.reason}" for problem in problems]
    return (
        "Diese Datei(en) können nicht importiert werden:\n\n"
        + "\n".join(lines)
        + "\n\nBitte die Auswahl ohne diese Datei(en) wiederholen."
    )


def split_summary_text(plan: SplitFilePlan, output_dir: Path, created_count: int) -> str:
    """Final message of the standalone wizard: count, folder, merged names, suffixed files."""
    text = f"{created_count} Datei(en) erstellt in:\n{output_dir}"
    if plan.merged_groups:
        merged = [
            f"• {group[0].name}: {format_page_ranges([(s.start_page, s.end_page) for s in group])}"
            for group in plan.merged_groups
        ]
        text += "\n\nZusammengeführt:\n" + "\n".join(merged[:_MAX_LISTED])
    if plan.suffixed_files:
        suffixed = [f"• {planned.display_name} → {planned.filename}" for planned in plan.suffixed_files]
        text += "\n\nWegen gleicher Dateinamen umbenannt:\n" + "\n".join(suffixed[:_MAX_LISTED])
    return text


def write_error_text(cause: BaseException, leftover_files: Sequence[Path]) -> str:
    """Error text after a failed write; the rollback removed everything except ``leftover_files``."""
    text = f"Beim Schreiben ist ein Fehler aufgetreten:\n{cause}\n\n"
    if leftover_files:
        text += "Diese Dateien konnten nicht wieder entfernt werden – bitte prüfen:\n" + "\n".join(
            f"• {path}" for path in leftover_files
        )
    else:
        text += "Es wurden keine Dateien angelegt. Grenzen und Namen sind unverändert."
    return text
