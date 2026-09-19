from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from bw_libs.app_paths import atomic_write_text
from app.adapters.bootstrap.wiring import GuiDependencies
from app.adapters.gui.dialog_services import filedialog, messagebox, simpledialog
from app.adapters.gui.ui_intent_controller_completion import UiIntentControllerCompletionMixin
from app.adapters.gui.ui_intent_controller_naming import UiIntentControllerNamingMixin
from app.adapters.gui.ui_intent_controller_regions import UiIntentControllerRegionsMixin
from app.adapters.gui.ui_intent_controller_scoring import UiIntentControllerScoringMixin
from app.adapters.gui.ui_intent_controller_supersymbol import UiIntentControllerSupersymbolMixin
from app.adapters.gui.view_models import ExamOverviewRow
from app.adapters.undo import HistoryAction
from app.core.domain.models import ExamProject
from app.infrastructure.repositories.file_utils import atomic_write_json

if TYPE_CHECKING:
    from app.adapters.gui.main_window import MainWindow


class UiIntentController(
    UiIntentControllerSupersymbolMixin,
    UiIntentControllerNamingMixin,
    UiIntentControllerRegionsMixin,
    UiIntentControllerScoringMixin,
    UiIntentControllerCompletionMixin,
):
    def __init__(self, app: "MainWindow", deps: GuiDependencies) -> None:
        self._app = app
        self._deps = deps

    def can_undo(self) -> bool:
        return self._deps.undo_history.can_undo()

    def can_redo(self) -> bool:
        return self._deps.undo_history.can_redo()

    def undo_label(self) -> str | None:
        return self._deps.undo_history.peek_undo()

    def redo_label(self) -> str | None:
        return self._deps.undo_history.peek_redo()

    def undo(self) -> bool:
        description = self._deps.undo_history.undo()
        if description is None:
            self._app.set_status("Nichts zum Rueckgaengigmachen")
            return False
        self._refresh_after_history_action()
        self._app.set_status(f"Rueckgaengig: {description}")
        return True

    def redo(self) -> bool:
        description = self._deps.undo_history.redo()
        if description is None:
            self._app.set_status("Nichts zum Wiederholen")
            return False
        self._refresh_after_history_action()
        self._app.set_status(f"Wiederholt: {description}")
        return True

    def _refresh_after_history_action(self) -> None:
        self.refresh_exam_overview()
        self._app.sync_current_exam_from_repository()

    def _record_history_action(self, *, description: str, undo, redo) -> None:
        self._deps.undo_history.push(
            HistoryAction(
                description=description,
                undo=undo,
                redo=redo,
            )
        )

    @staticmethod
    def _read_text_or_none(path: Path) -> str | None:
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    @staticmethod
    def _restore_text(path: Path, content: str | None) -> None:
        if content is None:
            if path.exists():
                path.unlink()
            return
        atomic_write_text(path, content, encoding="utf-8")

    @staticmethod
    def _write_exam_payload(exam_file: Path, payload: dict[str, object]) -> None:
        exam_file.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(exam_file, payload)

    def _record_exam_payload_action(
        self,
        *,
        description: str,
        exam_id: str,
        before_payload: dict[str, object],
        after_payload: dict[str, object],
    ) -> None:
        """Push one undo/redo entry that replays the given exam JSON snapshots.

        `before_payload`/`after_payload` must already be independent snapshots
        (e.g. a fresh `ExamProject.to_dict()` call) — `to_dict()` recursively
        builds new dicts/lists of primitive values with no references back to
        the live exam object, so callers must not deep-copy them again before
        passing them in here.
        """
        exam_file = self._deps.exam_repository.index_root / f"{exam_id}.json"

        self._record_history_action(
            description=description,
            undo=lambda: self._write_exam_payload(exam_file, before_payload),
            redo=lambda: self._write_exam_payload(exam_file, after_payload),
        )

    def _apply_exam_index_dir(self, target: Path) -> None:
        self._deps.settings_repository.save_exam_index_dir(target)
        self._deps.exam_repository.set_index_root(target)
        self._app.on_exam_index_dir_changed(target)
        self.refresh_exam_overview()

    def refresh_exam_overview(self) -> None:
        """Rebuild the exam overview list from a single load pass.

        `ListExamsUseCase.execute()` already loads and parses every exam file
        once; it must not be followed by a second directory-wide reload just
        to look up `exam_id`/`exam_name`/the source path, since `exam_file`
        is already carried on each `ExamOverview` result. A file that fails
        to load is skipped (not shown) rather than aborting the whole
        overview; if any did, a short status hint names how many and the
        first one, instead of a popup on every refresh.
        """
        overviews, load_errors = self._deps.list_exams_usecase.execute()
        rows = [
            ExamOverviewRow(
                exam_id=item.exam_id,
                exam_name=item.exam_name,
                reading_percent=item.reading_percent,
                correction_percent=item.correction_percent,
                region_count=item.region_count,
                corrected_region_count=item.corrected_region_count,
                reading_complete=item.reading_complete,
                has_open_flags=item.has_unassigned_extra_pages or item.has_missing_page_markings,
                source_file=item.exam_file,
            )
            for item in overviews
        ]
        self._app.render_overview_rows(rows)
        if load_errors:
            first = load_errors[0]
            suffix = f" ({len(load_errors) - 1} weitere)" if len(load_errors) > 1 else ""
            self._app.set_status(
                f"{len(load_errors)} Klausur(en) uebersprungen - fehlerhaft: {first.exam_file.name}: {first.message}{suffix}"
            )

    def create_exam(self) -> None:
        folder = filedialog.askdirectory(title="Klausurordner wählen")
        if not folder:
            return

        suggested = Path(folder).name
        exam_name = simpledialog.askstring("Neue Klausur", "Name der Klausur:", initialvalue=suggested)
        if exam_name is None:
            return

        try:
            result = self._deps.create_exam_usecase.execute(folder_path=Path(folder), exam_name=exam_name)
        except Exception as exc:  # pragma: no cover - UI messaging
            messagebox.showerror("Fehler", str(exc))
            return

        payload = result.exam.to_dict()
        exam_file = result.exam_file
        self._record_history_action(
            description=f"Klausur angelegt: {result.exam.exam_name}",
            undo=lambda: exam_file.exists() and exam_file.unlink(),
            redo=lambda: self._write_exam_payload(exam_file, payload),
        )

        self.refresh_exam_overview()
        self._app.open_exam_detail(result.exam, result.exam_file)
        self._app.start_reading_mode_for_current_exam()

    def open_selected_exam(self) -> None:
        """Open the exam selected in the overview, reporting a broken file instead of crashing.

        A structurally invalid exam (see `validate_regions`) or an
        unsupported legacy schema raises here; the user gets a clear error
        naming the file instead of an unhandled exception.
        """
        selected = self._app.get_selected_row()
        if selected is None:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Klausur auswählen.")
            return

        try:
            exam = self._deps.load_exam_usecase.execute(exam_file=selected.source_file)
        except Exception as exc:
            messagebox.showerror("Klausur fehlerhaft", f"'{selected.source_file.name}' konnte nicht geoeffnet werden:\n{exc}")
            return
        self._app.open_exam_detail(exam, selected.source_file)

    def delete_selected_exam(self) -> None:
        selected = self._app.get_selected_row()
        if selected is None:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Klausur auswählen.")
            return

        confirm = messagebox.askyesno(
            "Klausur loeschen",
            f"Klausur '{selected.exam_name}' wirklich loeschen?\nDie zugehoerige JSON-Datei wird entfernt.",
        )
        if not confirm:
            return

        try:
            snapshot_exam = self._deps.load_exam_usecase.execute(exam_file=selected.source_file)
        except Exception as exc:
            messagebox.showerror("Fehler", f"Klausur konnte nicht geladen werden: {exc}")
            return
        payload = snapshot_exam.to_dict()
        exam_file = selected.source_file

        try:
            self._deps.delete_exam_usecase.execute(exam_file=selected.source_file)
        except Exception as exc:
            messagebox.showerror("Fehler", f"Klausur konnte nicht geloescht werden: {exc}")
            return

        self._record_history_action(
            description=f"Klausur geloescht: {selected.exam_name}",
            undo=lambda: self._write_exam_payload(exam_file, payload),
            redo=lambda: exam_file.exists() and exam_file.unlink(),
        )

        self._app.on_exam_deleted(selected.exam_id)
        self.refresh_exam_overview()
        self._app.set_status("Klausur geloescht")

    def update_exam_index_dir(self, raw_path: str) -> Path | None:
        try:
            normalized = self._deps.settings_repository.normalize_exam_index_dir(raw_path)
        except Exception as exc:
            messagebox.showerror("Ungueltiger Pfad", str(exc))
            return None

        current = self._deps.exam_repository.index_root
        if normalized == current:
            self._app.set_status(f"JSON-Ablagepfad unveraendert: {normalized}")
            return normalized

        self._apply_exam_index_dir(normalized)
        self._record_history_action(
            description=f"JSON-Ablagepfad geaendert: {normalized}",
            undo=lambda: self._apply_exam_index_dir(current),
            redo=lambda: self._apply_exam_index_dir(normalized),
        )
        self._app.set_status(f"JSON-Ablagepfad aktualisiert: {normalized}")
        return normalized

    def save_exam_immediate(self, *, exam: ExamProject) -> ExamProject:
        before_payload = exam.to_dict()
        exam_file = self._deps.exam_repository.save_exam(exam)
        updated = self._deps.exam_repository.load_exam(exam_file)
        self._record_exam_payload_action(
            description="Klausur gespeichert",
            exam_id=updated.exam_id,
            before_payload=before_payload,
            after_payload=updated.to_dict(),
        )
        self.refresh_exam_overview()
        self._app.set_status("Aenderungen sofort gespeichert")
        return updated

