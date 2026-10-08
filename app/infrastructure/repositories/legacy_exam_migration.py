from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from app.infrastructure.repositories.exam_registry import REGISTRY_FILENAME, ExamRegistry
from app.infrastructure.repositories.file_utils import atomic_write_json

MIGRATED_SUFFIX = ".migriert"


@dataclass
class LegacyMigrationReport:
    """What one migration run did; ``status_text`` is the one-line notice for the GUI."""

    migrated: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    missing_folders: list[str] = field(default_factory=list)
    unreadable: list[str] = field(default_factory=list)

    def status_text(self) -> str | None:
        """German summary for the status line, or ``None`` if there was nothing to report."""
        parts = []
        if self.migrated:
            parts.append(f"{len(self.migrated)} Klausur(en) in ihren Ordner umgezogen")
        if self.missing_folders:
            parts.append(f"{len(self.missing_folders)} alte Klausur(en): Ordner nicht gefunden ({self.missing_folders[0]})")
        if self.conflicts:
            parts.append(f"{len(self.conflicts)} Konflikt(e): {self.conflicts[0]}")
        if self.unreadable:
            parts.append(f"{len(self.unreadable)} alte Datei(en) unlesbar: {self.unreadable[0]}")
        return " · ".join(parts) or None


def migrate_legacy_index(
    index_root: Path,
    registry: ExamRegistry,
    exam_file_for_folder: Callable[[Path], Path],
    read_header: Callable[[Path], dict[str, str] | None],
) -> LegacyMigrationReport:
    """Move every legacy ``<exam_id>.json`` from the index directory into its exam folder.

    Per legacy file, in this order (each step idempotent, so a run that was
    interrupted after any step simply continues on the next start):

    1. Write the folder file ``<folder>/korrektor_klausur.json`` atomically:
       missing -> write it; same ``exam_id`` already there -> the newer
       ``updated_at`` wins (an older folder file is first backed up next to
       it as ``korrektor_klausur.json.migriert``); equal ``updated_at`` -> no
       write (already done); foreign ``exam_id`` -> conflict, nothing
       touched; folder missing -> legacy file stays, reported.
    2. Register ``exam_id -> folder`` (set semantics).
    3. Rename the legacy file to ``<name>.migriert`` - it is never deleted.

    Crash-atomicity is not guaranteed beyond this per-step idempotence.
    """
    report = LegacyMigrationReport()
    for legacy_file in sorted(index_root.glob("*.json")):
        if legacy_file.name == REGISTRY_FILENAME:
            continue
        _migrate_one(legacy_file, registry, exam_file_for_folder, read_header, report)
    return report


def _migrate_one(legacy_file, registry, exam_file_for_folder, read_header, report) -> None:
    try:
        payload = json.loads(legacy_file.read_text(encoding="utf-8"))
        exam_id = str(payload["exam_id"]).strip()
        folder = Path(str(payload["folder_path"]))
    except Exception:
        report.unreadable.append(legacy_file.name)
        return
    if not exam_id or not folder.is_dir():
        report.missing_folders.append(str(folder))
        return

    target = exam_file_for_folder(folder)
    existing = read_header(target) if target.exists() else None
    legacy_updated_at = str(payload.get("updated_at", "")).strip()
    if existing is not None and existing.get("exam_id") != exam_id:
        report.conflicts.append(f"{folder.name} enthält bereits eine andere Klausur")
        return
    if existing is None or legacy_updated_at > existing.get("updated_at", ""):
        if existing is not None:
            backup = _unique_path(target.with_name(f"{target.name}{MIGRATED_SUFFIX}"))
            backup.write_bytes(target.read_bytes())
        payload["folder_path"] = str(target.parent)
        atomic_write_json(target, payload)

    registry.register(exam_id, target.parent)
    legacy_file.replace(_unique_path(legacy_file.with_name(f"{legacy_file.name}{MIGRATED_SUFFIX}")))
    report.migrated.append(str(payload.get("exam_name", exam_id)))


def _unique_path(path: Path) -> Path:
    """Return ``path`` or the first free ``path_2``, ``path_3``, ... (never overwrite a backup)."""
    candidate = path
    counter = 2
    while candidate.exists():
        candidate = path.with_name(f"{path.name}_{counter}")
        counter += 1
    return candidate
