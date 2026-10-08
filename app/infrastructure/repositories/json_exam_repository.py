from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.domain.models import ExamProject, utc_now_iso
from app.core.domain.validation import ExamConflictError, validate_regions
from app.core.ports.repositories import ExamRepository
from app.infrastructure.repositories.exam_registry import ExamRegistry
from app.infrastructure.repositories.file_utils import atomic_write_json
from app.infrastructure.repositories.legacy_exam_migration import LegacyMigrationReport, migrate_legacy_index
from app.infrastructure.repositories.legacy_migration import migrate_legacy_area_code_references

EXAM_DATA_FILENAME = "korrektor_klausur.json"


class ExamFolderMissingError(ValueError):
    """A registered exam's folder or its ``korrektor_klausur.json`` is gone (reported, never crashes the overview)."""


class JsonExamRepository(ExamRepository):
    """Exam storage: the exam folder is the single source of all exam data.

    Each exam lives in ``<Klausurordner>/korrektor_klausur.json`` next to its
    PDFs and ``korrektor_scores.csv``, so copying/syncing the folder carries
    everything. The index directory (``index_root``) only holds the discovery
    list `ExamRegistry` (``known_exams.json``) and, until migrated, legacy
    ``<exam_id>.json`` files of the old central storage.

    ``folder_path`` contract: on load it is always derived from where the
    file actually is; the stored value is never read as truth. On save it is
    rewritten to the current folder, so a stale absolute path survives at
    most until the next save and never becomes authoritative.

    Crash-atomicity is not guaranteed for multi-step operations (save +
    registry update): a hard crash between them leaves an unregistered but
    intact folder file, which "Neue Klausur" can adopt again.
    """

    def __init__(self, index_root: Path) -> None:
        """Use ``index_root`` for the discovery registry (created if missing)."""
        self.set_index_root(index_root)

    @property
    def index_root(self) -> Path:
        """Directory holding ``known_exams.json`` (and legacy files until migrated)."""
        return self._index_root

    @property
    def registry(self) -> ExamRegistry:
        """The discovery registry of the current index directory."""
        return self._registry

    def set_index_root(self, index_root: Path) -> None:
        """Switch to another index directory (the registry file there is used from now on)."""
        normalized = index_root.resolve()
        normalized.mkdir(parents=True, exist_ok=True)
        self._index_root = normalized
        self._registry = ExamRegistry(normalized)

    @staticmethod
    def exam_file_for_folder(folder: Path) -> Path:
        """Return the exam data file of ``folder`` (whether or not it exists)."""
        return folder.resolve() / EXAM_DATA_FILENAME

    def exam_file_for(self, exam: ExamProject) -> Path:
        """Return the data file of ``exam`` (its folder is the one it was loaded from / created in)."""
        return self.exam_file_for_folder(Path(exam.folder_path))

    def exam_file_for_id(self, exam_id: str) -> Path | None:
        """Return the data file of a registered exam, or ``None`` if ``exam_id`` is unknown."""
        folder = self._registry.folder_for(exam_id)
        return None if folder is None else self.exam_file_for_folder(folder)

    def list_exam_files(self) -> list[Path]:
        """Return the data files of all registered exams (missing ones fail on `load_exam`, by design)."""
        return sorted((self.exam_file_for_folder(folder) for folder in self._registry.entries().values()), key=str)

    def read_exam_header(self, exam_file: Path) -> dict[str, str] | None:
        """Return ``exam_id``/``exam_name``/``updated_at`` of a data file without full validation, or ``None``."""
        try:
            raw = json.loads(exam_file.read_text(encoding="utf-8"))
        except Exception:
            return None
        return {key: str(raw.get(key, "")).strip() for key in ("exam_id", "exam_name", "updated_at")}

    def load_exam(self, exam_file: Path) -> ExamProject:
        """Load, migrate and validate one exam data file; ``folder_path`` is set from its location.

        Pipeline: raw JSON -> legacy area_code-to-region_id migration (on the
        raw dict) -> ``folder_path`` replaced by the file's folder ->
        `ExamProject.from_dict` (raises `ValueError` for an unsupported schema)
        -> `validate_regions` (raises `ExamStructureError`). A missing file
        raises `ExamFolderMissingError` (a `ValueError`), so the overview lists
        it as "Ordner nicht gefunden" instead of crashing.
        """
        if not exam_file.exists():
            raise ExamFolderMissingError(f"Ordner oder Klausurdatei nicht gefunden: {exam_file.parent}")
        with exam_file.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        raw = migrate_legacy_area_code_references(raw)
        raw["folder_path"] = str(exam_file.parent.resolve())
        try:
            exam = ExamProject.from_dict(raw)
        except ValueError as exc:
            raise ValueError(f"{_label(exam_file)}: {exc}") from exc
        validate_regions(exam)
        return exam

    def save_exam(self, exam: ExamProject) -> Path:
        """Persist ``exam`` into its folder atomically and make sure it is registered.

        Atomic contract: the file is written to a temporary file and then
        replaces the target (`atomic_write_json`); on any error the previous
        ``korrektor_klausur.json`` stays byte-identical. Conflict contract:
        if the file on disk has a different ``updated_at`` than this in-memory
        copy was loaded with, someone else saved meanwhile (e.g. another PC
        via a synced folder) and `ExamConflictError` is raised before
        anything is written.
        """
        target = self.exam_file_for(exam)
        on_disk_updated_at = self._read_on_disk_updated_at(target)
        if on_disk_updated_at is not None and on_disk_updated_at != exam.updated_at:
            raise ExamConflictError(
                f"Klausur '{exam.exam_name}' wurde seit dem Laden an anderer Stelle verändert "
                "(z. B. auf einem anderen Rechner über denselben Klausurordner) - Speichern "
                "abgebrochen, um diese Änderung nicht zu verlieren. Bitte die Klausur schließen "
                "und neu öffnen, um den aktuellen Stand zu laden, und die eigene Änderung danach "
                "erneut vornehmen."
            )
        previous_updated_at = exam.updated_at
        exam.updated_at = utc_now_iso()
        exam.folder_path = str(target.parent)
        try:
            atomic_write_json(target, exam.to_dict())
        except Exception:
            exam.updated_at = previous_updated_at
            raise
        self._registry.register(exam.exam_id, target.parent)
        return target

    def write_exam_payload(self, exam_file: Path, payload: dict[str, Any]) -> None:
        """Write a full exam snapshot (undo/redo) to ``exam_file`` atomically and (re-)register it.

        ``folder_path`` in the written file is set to ``exam_file``'s folder
        (contract: never a stale absolute path).
        """
        data = dict(payload)
        data["folder_path"] = str(exam_file.parent.resolve())
        atomic_write_json(exam_file, data)
        exam_id = str(data.get("exam_id", "")).strip()
        if exam_id:
            self._registry.register(exam_id, exam_file.parent)

    def delete_exam(self, exam_file: Path) -> None:
        """Delete the exam data file and unregister it (PDFs and scores are untouched)."""
        if exam_file.name != EXAM_DATA_FILENAME:
            raise ValueError(f"Keine Klausurdatei: {exam_file}")
        header = self.read_exam_header(exam_file)
        if exam_file.exists():
            exam_file.unlink()
        exam_id = (header or {}).get("exam_id") or self._registry.exam_id_for_folder(exam_file.parent)
        if exam_id:
            self._registry.unregister(exam_id)

    def migrate_legacy_index(self) -> LegacyMigrationReport:
        """Move legacy ``<exam_id>.json`` files of the old central storage into their exam folders."""
        return migrate_legacy_index(self._index_root, self._registry, self.exam_file_for_folder, self.read_exam_header)

    @staticmethod
    def _read_on_disk_updated_at(target: Path) -> str | None:
        if not target.exists():
            return None
        try:
            with target.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except Exception:
            return None
        value = str(raw.get("updated_at", "")).strip()
        return value or None


def _label(exam_file: Path) -> str:
    """Human label of a data file: ``<folder>/korrektor_klausur.json`` (all data files share one name)."""
    return f"{exam_file.parent.name}/{exam_file.name}"
