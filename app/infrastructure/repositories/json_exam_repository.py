from __future__ import annotations

import json
from pathlib import Path

from app.core.domain.models import ExamProject, utc_now_iso
from app.core.domain.validation import ExamConflictError, validate_regions
from app.core.ports.repositories import ExamRepository
from app.infrastructure.repositories.file_utils import atomic_write_json
from app.infrastructure.repositories.legacy_migration import migrate_legacy_area_code_references


class JsonExamRepository(ExamRepository):
    def __init__(self, index_root: Path) -> None:
        self.set_index_root(index_root)

    @property
    def index_root(self) -> Path:
        return self._index_root

    def set_index_root(self, index_root: Path) -> None:
        normalized = index_root.resolve()
        normalized.mkdir(parents=True, exist_ok=True)
        self._index_root = normalized

    def list_exam_files(self) -> list[Path]:
        return sorted(self._index_root.glob("*.json"))

    def load_exam(self, exam_file: Path) -> ExamProject:
        """Load, migrate and validate one exam JSON file.

        Pipeline: raw JSON -> legacy area_code-to-region_id migration (on the
        raw dict) -> `ExamProject.from_dict` (materializes the new domain
        model, raises `ValueError` for an unsupported/legacy schema) ->
        `validate_regions` (raises `ExamStructureError` for structurally
        ambiguous region identifiers that parsed successfully but must not
        be used as-is). Callers decide how to surface either exception.
        """
        with exam_file.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        raw = migrate_legacy_area_code_references(raw)
        try:
            exam = ExamProject.from_dict(raw)
        except ValueError as exc:
            raise ValueError(f"{exam_file.name}: {exc}") from exc
        validate_regions(exam)
        return exam

    def save_exam(self, exam: ExamProject) -> Path:
        """Persist `exam`, refusing to overwrite a newer on-disk version.

        `exam.updated_at` still holds whatever value this in-memory copy was
        loaded/last saved with (this method is the only place that ever
        changes it). If the file already on disk has a *different*
        `updated_at`, something else wrote it since - most likely the same
        Exam-Indexordner opened on another computer via cloud sync - so this
        save is rejected with `ExamConflictError` instead of silently
        discarding that other change. A brand-new exam (no file yet) or a
        file whose `updated_at` cannot be read (corrupt/legacy) is not
        blocked by this check.
        """
        target = self._index_root / f"{exam.exam_id}.json"
        on_disk_updated_at = self._read_on_disk_updated_at(target)
        if on_disk_updated_at is not None and on_disk_updated_at != exam.updated_at:
            raise ExamConflictError(
                f"Klausur '{exam.exam_name}' wurde seit dem Laden an anderer Stelle veraendert "
                "(z. B. auf einem anderen Rechner ueber denselben Exam-Indexordner) - Speichern "
                "abgebrochen, um diese Aenderung nicht zu verlieren. Bitte die Klausur schliessen "
                "und neu oeffnen, um den aktuellen Stand zu laden, und die eigene Aenderung danach "
                "erneut vornehmen."
            )
        exam.updated_at = utc_now_iso()
        atomic_write_json(target, exam.to_dict())
        return target

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

    def delete_exam(self, exam_file: Path) -> None:
        candidate = exam_file.resolve()
        if candidate.parent != self._index_root:
            raise ValueError("Exam file is outside configured index directory")
        if candidate.exists():
            candidate.unlink()
