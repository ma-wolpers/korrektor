from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from bw_libs.app_paths import AppPaths

from app.infrastructure.repositories.file_utils import atomic_write_json


@dataclass(slots=True, frozen=True)
class AppRuntimeSettings:
    exam_index_dir: Path
    default_annotation_color: str = "#d62828"
    default_annotation_pdf_font_size: float = 14.0


class JsonAppSettingsRepository:
    def __init__(self, *, app_name: str, base_dir: Path, default_exam_index_dir: Path) -> None:
        self._base_dir = base_dir.resolve()
        self._default_exam_index_dir = default_exam_index_dir.resolve()
        app_paths = AppPaths.discover(app_name=app_name, start_dir=self._base_dir)
        self._settings_file = app_paths.data_dir / "settings.json"

    def normalize_exam_index_dir(self, raw_path: str) -> Path:
        normalized_raw = raw_path.strip()
        if not normalized_raw:
            raise ValueError("Bitte einen gueltigen Ordnerpfad angeben.")

        candidate = Path(normalized_raw).expanduser()
        if not candidate.is_absolute():
            candidate = (self._base_dir / candidate).resolve()
        else:
            candidate = candidate.resolve()

        candidate.mkdir(parents=True, exist_ok=True)
        return candidate

    def load(self) -> AppRuntimeSettings:
        if not self._settings_file.exists():
            self._default_exam_index_dir.mkdir(parents=True, exist_ok=True)
            return AppRuntimeSettings(exam_index_dir=self._default_exam_index_dir)

        try:
            with self._settings_file.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except Exception:
            self._default_exam_index_dir.mkdir(parents=True, exist_ok=True)
            return AppRuntimeSettings(exam_index_dir=self._default_exam_index_dir)

        raw_exam_index_dir = str(raw.get("exam_index_dir", "")).strip()
        if not raw_exam_index_dir:
            self._default_exam_index_dir.mkdir(parents=True, exist_ok=True)
            return AppRuntimeSettings(exam_index_dir=self._default_exam_index_dir)

        try:
            exam_index_dir = self.normalize_exam_index_dir(raw_exam_index_dir)
        except ValueError:
            exam_index_dir = self._default_exam_index_dir
            exam_index_dir.mkdir(parents=True, exist_ok=True)
        raw_color = str(raw.get("default_annotation_color", "#d62828")).strip()
        default_color = raw_color if raw_color.startswith("#") and len(raw_color) == 7 else "#d62828"

        raw_size = raw.get("default_annotation_pdf_font_size", 14.0)
        try:
            default_size = float(raw_size)
        except (TypeError, ValueError):
            default_size = 14.0
        default_size = max(8.0, min(96.0, default_size))

        return AppRuntimeSettings(
            exam_index_dir=exam_index_dir,
            default_annotation_color=default_color,
            default_annotation_pdf_font_size=default_size,
        )

    def save(self, settings: AppRuntimeSettings) -> AppRuntimeSettings:
        normalized = settings.exam_index_dir.resolve()
        normalized.mkdir(parents=True, exist_ok=True)
        color = settings.default_annotation_color.strip()
        if not (color.startswith("#") and len(color) == 7):
            color = "#d62828"
        size = max(8.0, min(96.0, float(settings.default_annotation_pdf_font_size)))
        payload = {
            "exam_index_dir": str(normalized),
            "default_annotation_color": color,
            "default_annotation_pdf_font_size": size,
        }
        atomic_write_json(self._settings_file, payload)
        return AppRuntimeSettings(
            exam_index_dir=normalized,
            default_annotation_color=color,
            default_annotation_pdf_font_size=size,
        )

    def save_exam_index_dir(self, exam_index_dir: Path) -> AppRuntimeSettings:
        current = self.load()
        return self.save(
            AppRuntimeSettings(
                exam_index_dir=exam_index_dir,
                default_annotation_color=current.default_annotation_color,
                default_annotation_pdf_font_size=current.default_annotation_pdf_font_size,
            )
        )
