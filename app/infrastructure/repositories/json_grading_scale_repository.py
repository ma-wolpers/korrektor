from __future__ import annotations

import json
from pathlib import Path

from bw_libs.app_paths import AppPaths

from app.core.domain.grading_scale import GradingScale, GradingScaleUsageEntry
from app.infrastructure.repositories.file_utils import atomic_write_json


class JsonGradingScaleRepository:
    """Global, exam-independent store for grading-scale templates and their usage log.

    Lives in `%APPDATA%/<app_name>/` (same discovery mechanism as
    `JsonAppSettingsRepository`), deliberately *not* under the
    user-configurable Exam-Indexordner (`update_exam_index_dir`) - a
    Notenschluessel is meant to be reusable across exams even if the
    teacher later points korrektor at a different exam folder. Two files,
    one class: `grading_scales.json` (the editable templates) and
    `grading_scale_usage.json` (an append-only log of assignments, used by
    the Notenschluessel-Verwaltung's "wo verwendet"-Uebersicht and to decide
    whether a template may still be hard-deleted) share the same storage
    lifecycle, so splitting them into two repository classes would only add
    ceremony without a real seam.
    """

    def __init__(self, *, app_name: str, base_dir: Path) -> None:
        app_paths = AppPaths.discover(app_name=app_name, start_dir=base_dir)
        self._scales_file = app_paths.data_dir / "grading_scales.json"
        self._usage_file = app_paths.data_dir / "grading_scale_usage.json"

    def list_scales(self) -> list[GradingScale]:
        raw = self._read(self._scales_file)
        return [GradingScale.from_dict(item) for item in raw.get("scales", [])]

    def get_scale(self, scale_id: str) -> GradingScale | None:
        return next((scale for scale in self.list_scales() if scale.scale_id == scale_id), None)

    def save_scale(self, scale: GradingScale) -> GradingScale:
        """Create or update (by `scale_id`) one template. Editing never touches any exam's snapshot."""
        scales = self.list_scales()
        for index, existing in enumerate(scales):
            if existing.scale_id == scale.scale_id:
                scales[index] = scale
                break
        else:
            scales.append(scale)
        atomic_write_json(self._scales_file, {"scales": [item.to_dict() for item in scales]})
        return scale

    def delete_scale(self, scale_id: str) -> None:
        """Remove a template permanently.

        Callers must check `has_usage(scale_id)` first and archive instead
        (`GradingScale.status`) when it has recorded usage - this method
        itself does not enforce that policy, matching the rest of the
        codebase's split between fachliche Validierung (UseCase/Controller)
        and reiner Persistenz (Repository).
        """
        scales = [scale for scale in self.list_scales() if scale.scale_id != scale_id]
        atomic_write_json(self._scales_file, {"scales": [item.to_dict() for item in scales]})

    def list_usage(self, scale_id: str | None = None) -> list[GradingScaleUsageEntry]:
        raw = self._read(self._usage_file)
        entries = [GradingScaleUsageEntry.from_dict(item) for item in raw.get("entries", [])]
        if scale_id is None:
            return entries
        return [entry for entry in entries if entry.source_scale_id == scale_id]

    def has_usage(self, scale_id: str) -> bool:
        return bool(self.list_usage(scale_id))

    def record_usage(self, entry: GradingScaleUsageEntry) -> None:
        """Append one usage record. Never mutated or removed afterwards - see `GradingScaleUsageEntry`."""
        entries = self.list_usage()
        entries.append(entry)
        atomic_write_json(self._usage_file, {"entries": [item.to_dict() for item in entries]})

    @staticmethod
    def _read(path: Path) -> dict[str, object]:
        if not path.exists():
            return {}
        try:
            with path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception:
            return {}
