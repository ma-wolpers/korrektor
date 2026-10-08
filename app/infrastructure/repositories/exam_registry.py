from __future__ import annotations

import json
import logging
from pathlib import Path

from app.infrastructure.repositories.file_utils import atomic_write_json

REGISTRY_FILENAME = "known_exams.json"

_LOG = logging.getLogger(__name__)


class ExamRegistry:
    """Discovery list of known exam folders (``exam_id`` -> folder), stored in the index directory.

    Contract: the registry is **only** for discovery and the overview. The
    exam folder (``<folder>/korrektor_klausur.json``) is the single source of
    all exam data - nothing here is domain data, so losing the registry only
    means re-adopting folders via "Neue Klausur".

    Every write replaces the whole file atomically. A corrupt registry file
    is moved aside to ``known_exams.json.defekt`` (never silently overwritten)
    and treated as empty; ``corruption_notice`` then says so once.
    """

    def __init__(self, index_root: Path) -> None:
        """Use ``<index_root>/known_exams.json`` (the directory must already exist)."""
        self._file = index_root / REGISTRY_FILENAME
        self.corruption_notice: str | None = None

    @property
    def file(self) -> Path:
        """Path of the registry file."""
        return self._file

    def entries(self) -> dict[str, Path]:
        """Return ``{exam_id: resolved folder}`` for every registered exam."""
        if not self._file.exists():
            return {}
        try:
            raw = json.loads(self._file.read_text(encoding="utf-8"))
            return {
                str(item["exam_id"]): Path(str(item["folder"])).resolve()
                for item in raw.get("exams", [])
                if str(item.get("exam_id", "")).strip() and str(item.get("folder", "")).strip()
            }
        except Exception:
            self._quarantine_corrupt_file()
            return {}

    def folder_for(self, exam_id: str) -> Path | None:
        """Return the registered folder of ``exam_id``, or ``None``."""
        return self.entries().get(exam_id)

    def exam_id_for_folder(self, folder: Path) -> str | None:
        """Return the ``exam_id`` registered for ``folder`` (compared resolved), or ``None``."""
        resolved = folder.resolve()
        return next((exam_id for exam_id, known in self.entries().items() if known == resolved), None)

    def register(self, exam_id: str, folder: Path) -> None:
        """Map ``exam_id`` to ``folder`` (set semantics: re-registering is a no-op, a new folder replaces the old)."""
        entries = self.entries()
        resolved = folder.resolve()
        if entries.get(exam_id) == resolved:
            return
        entries[exam_id] = resolved
        self._write(entries)

    def unregister(self, exam_id: str) -> Path | None:
        """Remove ``exam_id``; return its former folder (``None`` if it was not registered)."""
        entries = self.entries()
        folder = entries.pop(exam_id, None)
        if folder is not None:
            self._write(entries)
        return folder

    def replace_all(self, entries: dict[str, Path]) -> None:
        """Set the complete registry state (used by undo/redo, which store full states, not diffs)."""
        self._write({exam_id: folder.resolve() for exam_id, folder in entries.items()})

    def _write(self, entries: dict[str, Path]) -> None:
        payload = {
            "exams": [
                {"exam_id": exam_id, "folder": str(folder)}
                for exam_id, folder in sorted(entries.items(), key=lambda item: str(item[1]).lower())
            ]
        }
        atomic_write_json(self._file, payload)

    def _quarantine_corrupt_file(self) -> None:
        """Move an unreadable registry aside so it is never overwritten; remember a one-time notice."""
        target = self._file.with_name(f"{REGISTRY_FILENAME}.defekt")
        try:
            self._file.replace(target)
        except OSError:
            _LOG.exception("Klausurliste konnte nicht beiseitegelegt werden: %s", self._file)
            return
        self.corruption_notice = (
            f"Die Klausurliste war beschädigt und wurde als {target.name} gesichert. "
            "Klausuren lassen sich über 'Neue Klausur' aus ihrem Ordner wieder übernehmen."
        )
