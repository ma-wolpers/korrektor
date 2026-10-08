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
    # Scan-Werkstatt: Strg+←/→ step in degrees (product decision: default 2.0, allowed 0.1-45).
    scan_rotation_step_deg: float = 2.0


SCAN_ROTATION_STEP_RANGE = (0.1, 45.0)


def clamp_scan_rotation_step(value: object) -> float:
    """Scan-Werkstatt rotation step in degrees, clamped to 0.1-45 (invalid input -> default 2.0)."""
    try:
        step = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return 2.0
    return max(SCAN_ROTATION_STEP_RANGE[0], min(SCAN_ROTATION_STEP_RANGE[1], step))


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
        """Read the settings file; missing or invalid values fall back to defaults (rotation step clamped to `SCAN_ROTATION_STEP_RANGE`)."""
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
            scan_rotation_step_deg=clamp_scan_rotation_step(raw.get("scan_rotation_step_deg", 2.0)),
        )

    def save(self, settings: AppRuntimeSettings) -> AppRuntimeSettings:
        """Write all runtime settings atomically (including `scan_rotation_step_deg`)."""
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
            "scan_rotation_step_deg": clamp_scan_rotation_step(settings.scan_rotation_step_deg),
        }
        atomic_write_json(self._settings_file, payload)
        return AppRuntimeSettings(
            exam_index_dir=normalized,
            default_annotation_color=color,
            default_annotation_pdf_font_size=size,
            scan_rotation_step_deg=clamp_scan_rotation_step(settings.scan_rotation_step_deg),
        )

    def save_exam_index_dir(self, exam_index_dir: Path) -> AppRuntimeSettings:
        """Change only the exam index folder, keeping every other stored setting."""
        current = self.load()
        return self.save(
            AppRuntimeSettings(
                exam_index_dir=exam_index_dir,
                default_annotation_color=current.default_annotation_color,
                default_annotation_pdf_font_size=current.default_annotation_pdf_font_size,
                scan_rotation_step_deg=current.scan_rotation_step_deg,
            )
        )
