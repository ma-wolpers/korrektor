from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from app.adapters.gui.dialog_services import filedialog, messagebox
from app.core.domain.grading_scale import GradingScale

from bw_libs.app_paths import atomic_write_json

EXPORT_FORMAT_KEY = "korrektor_grading_scales_export"
EXPORT_FORMAT_VERSION = 1


@dataclass(slots=True)
class GradingScaleImportSummary:
    """What happened to every scale found in an imported file, by name."""

    added: list[str] = field(default_factory=list)
    skipped_identical: list[str] = field(default_factory=list)
    skipped_conflict: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.added or self.skipped_identical or self.skipped_conflict)


class UiIntentControllerGradingScaleTransferMixin:
    """Datei-Export/-Import fuer globale Notenschluessel-Vorlagen.

    Notenschluessel leben global unter `%APPDATA%/<app_name>/` (siehe
    `JsonGradingScaleRepository`) statt im - ueber mehrere Rechner hinweg
    ggf. synchronisierten - Exam-Indexordner; ein Wechsel des Rechners
    (anderer Exam-Indexordner-Pfad reicht schon) laesst die dort verwaltete
    Klausur-Historie unberuehrt, startet aber ohne jeden Notenschluessel.
    Dieser Export/Import ist der manuelle Uebertragungsweg dafuer - bewusst
    kein automatischer Sync, da `%APPDATA%` nicht Teil des vom Nutzer
    gewaehlten (ggf. synchronisierten) Ordners ist.
    """

    def export_grading_scales_to_file(self) -> bool:
        """Write every currently stored scale (active and archived) to a chosen JSON file."""
        scales = self._deps.grading_scale_repository.list_scales()
        if not scales:
            messagebox.showinfo("Keine Notenschluessel", "Es sind noch keine Notenschluessel angelegt.")
            return False

        output_path_raw = filedialog.asksaveasfilename(
            title="Notenschluessel exportieren",
            defaultextension=".json",
            filetypes=[("Notenschluessel-Export", "*.json"), ("Alle Dateien", "*.*")],
            initialfile="notenschluessel_export.json",
        )
        if not output_path_raw:
            return False

        payload = {
            EXPORT_FORMAT_KEY: EXPORT_FORMAT_VERSION,
            "scales": [scale.to_dict() for scale in scales],
        }
        try:
            atomic_write_json(Path(output_path_raw), payload)
        except OSError as exc:
            messagebox.showerror("Export fehlgeschlagen", str(exc))
            return False

        self._app.set_status(f"{len(scales)} Notenschluessel exportiert: {Path(output_path_raw).name}")
        return True

    def import_grading_scales_from_file(self) -> GradingScaleImportSummary | None:
        """Read a previously exported file and add scales missing locally.

        A `scale_id` already present locally is never overwritten - if its
        content differs from the imported one, that is reported as a
        conflict (`skipped_conflict`) instead of silently discarding either
        version; the teacher decides (e.g. re-export the newer one, or
        rename before re-importing) rather than the import guessing.
        """
        source_path_raw = filedialog.askopenfilename(
            title="Notenschluessel importieren",
            filetypes=[("Notenschluessel-Export", "*.json"), ("Alle Dateien", "*.*")],
        )
        if not source_path_raw:
            return None

        try:
            with Path(source_path_raw).open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Import fehlgeschlagen", f"Datei konnte nicht gelesen werden: {exc}")
            return None

        if EXPORT_FORMAT_KEY not in raw:
            messagebox.showerror(
                "Import fehlgeschlagen", "Diese Datei ist kein Notenschluessel-Export von Korrektor."
            )
            return None

        summary = self._merge_imported_grading_scales(raw.get("scales", []))
        if summary.is_empty:
            messagebox.showinfo("Import", "Die Datei enthielt keine gueltigen Notenschluessel.")
            return summary

        self._app.set_status(
            f"Notenschluessel-Import: {len(summary.added)} neu, "
            f"{len(summary.skipped_identical)} bereits vorhanden, "
            f"{len(summary.skipped_conflict)} Konflikt(e)"
        )
        return summary

    def _merge_imported_grading_scales(self, raw_scales: list[object]) -> GradingScaleImportSummary:
        repo = self._deps.grading_scale_repository
        existing_by_id = {scale.scale_id: scale for scale in repo.list_scales()}
        summary = GradingScaleImportSummary()

        for raw_scale in raw_scales:
            if not isinstance(raw_scale, dict):
                continue
            scale = GradingScale.from_dict(raw_scale)
            if not scale.scale_id or not scale.name:
                continue

            existing = existing_by_id.get(scale.scale_id)
            if existing is None:
                repo.save_scale(scale)
                summary.added.append(scale.name)
            elif existing.to_dict() == scale.to_dict():
                summary.skipped_identical.append(scale.name)
            else:
                summary.skipped_conflict.append(scale.name)

        return summary
