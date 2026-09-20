from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from bw_libs.app_paths import atomic_write_json as _shared_atomic_write_json


def atomic_write_json(file_path: Path, payload: dict[str, Any]) -> None:
    _shared_atomic_write_json(file_path, payload)


def slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "klausur"


_WINDOWS_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED_STEMS = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}
_MAX_FILENAME_STEM_LENGTH = 150


def sanitize_filename_stem(name: str, *, replace_spaces_with: str | None = "_") -> str | None:
    """Turn arbitrary text into a Windows-safe filename stem (no extension).

    Shared pipeline behind `build_pdf_filename_from_name` and the
    Auswertungs-Export (`export_student_results`, one file per Schueler:in
    named after `display_name`): normalize whitespace/case -> optionally
    replace spaces (`replace_spaces_with=None` keeps them, e.g. for export
    filenames where readability matters more than the Namenmodus
    underscore convention) -> strip invalid characters -> strip trailing
    dots/spaces -> defuse reserved Windows device names -> truncate to a
    safe length. Returns ``None`` (never a guessed fallback name) if
    nothing valid remains after normalization — the caller must treat that
    as a validation error, not silently proceed with an arbitrary name.
    """
    collapsed = " ".join(name.strip().split())
    stem = collapsed if replace_spaces_with is None else collapsed.replace(" ", replace_spaces_with)
    stem = _WINDOWS_INVALID_CHARS.sub("", stem)
    stem = stem.rstrip(" .")
    if not stem:
        return None

    if stem.upper() in _WINDOWS_RESERVED_STEMS:
        stem = f"{stem}_name"

    stem = stem[:_MAX_FILENAME_STEM_LENGTH].rstrip(" .")
    return stem or None


def build_pdf_filename_from_name(name: str) -> str | None:
    """Turn an entered student name into a Windows-safe ``<stem>.pdf`` filename.

    Namenmodus rule: spaces become underscores, case is preserved (no
    lowercasing, no Vorname/Nachname reordering) — this only makes the name
    filesystem-safe, it does not change what is shown as `display_name`.
    """
    stem = sanitize_filename_stem(name)
    return f"{stem}.pdf" if stem else None
