from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.adapters.gui.dialog_services import choicedialog, messagebox
from app.core.usecases.adopt_exam_usecase import AdoptionAnalysis
from app.infrastructure.repositories.file_utils import atomic_write_bytes
from bw_gui.dialogs import ChoiceOption

_REMOVE_UNREGISTER = "unregister"
_REMOVE_DELETE_DATA = "delete_data"
_COPY_AS_NEW = "as_new"
_COPY_SWITCH = "switch"


class UiIntentControllerExamStorageMixin:
    """Exam folders as the single source: adopt existing exam data, remove exams from the list or delete their data.

    History contract: every action stores complete states (full Klausurliste
    state and, where a file changes, its full bytes) - never diffs that
    depend on later changes.
    """

    def _adopt_existing_exam(self, analysis: AdoptionAnalysis) -> bool:
        """"Neue Klausur" on a folder that already holds exam data; return True if an exam was opened.

        Policy (see `AdoptionAnalysis`): the chosen folder's exam is opened -
        never another exam just because the Klausurliste knows its id.
        """
        name = analysis.exam_name
        changed = _format_timestamp(analysis.updated_at)
        as_new_exam = False
        if analysis.situation == "new":
            if not messagebox.askyesno(
                "Klausur übernehmen",
                f"In diesem Ordner liegt bereits die Klausur „{name}“ (zuletzt geändert {changed}).\n\nÜbernehmen?",
            ):
                return False
        elif analysis.situation == "moved":
            if not messagebox.askyesno(
                "Klausur wurde verschoben",
                f"Die Klausur „{name}“ war unter\n{analysis.registered_folder}\nbekannt, dort liegt sie nicht mehr.\n\n"
                "Auf diesen Ordner umstellen?",
            ):
                return False
        elif analysis.situation == "copy":
            choice = choicedialog.askchoice(
                "Klausur liegt doppelt vor",
                f"Die Klausur „{name}“ ist schon aus einem anderen Ordner bekannt:\n{analysis.registered_folder}",
                (
                    ChoiceOption(_COPY_AS_NEW, "Als eigene Klausur übernehmen", "Bekommt eine neue ID; beide Ordner erscheinen in der Übersicht."),
                    ChoiceOption(_COPY_SWITCH, "Auf diesen Ordner umstellen", "Der andere Ordner verschwindet aus der Übersicht; seine Daten bleiben dort liegen."),
                ),
            )
            if choice is None:
                return False
            as_new_exam = choice == _COPY_AS_NEW

        registry = self._deps.exam_repository.registry
        before_entries = registry.entries()
        before_bytes = analysis.exam_file.read_bytes()
        try:
            exam = self._deps.adopt_exam_usecase.adopt(analysis, as_new_exam=as_new_exam)
        except Exception as exc:
            messagebox.showerror("Klausur konnte nicht übernommen werden", str(exc))
            return False
        after_entries = registry.entries()
        after_bytes = analysis.exam_file.read_bytes()
        if (before_entries, before_bytes) != (after_entries, after_bytes):
            self._record_history_action(
                description=f"Klausur übernommen: {exam.exam_name}",
                undo=lambda: self._restore_storage_state(analysis.exam_file, before_bytes, before_entries),
                redo=lambda: self._restore_storage_state(analysis.exam_file, after_bytes, after_entries),
                context="lifecycle",
            )
        self.refresh_exam_overview()
        self._app.open_exam_detail(exam, analysis.exam_file)
        self._app.set_status(f"Klausur „{exam.exam_name}“ aus dem Ordner übernommen")
        return True

    def _restore_storage_state(self, exam_file: Path, exam_bytes: bytes, entries: dict[str, Path]) -> None:
        """Set exam file bytes and the complete Klausurliste back to a recorded state."""
        atomic_write_bytes(exam_file, exam_bytes)
        self._deps.exam_repository.registry.replace_all(entries)

    def delete_selected_exam(self) -> None:
        """"Klausur entfernen": only from the overview, or delete the exam data in the folder (PDFs stay).

        Both ways are undoable with complete states: the Klausurliste entry,
        and for data deletion the byte-exact exam and score files.
        """
        selected = self._app.get_selected_row()
        if selected is None:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Klausur auswählen.")
            return
        choice = choicedialog.askchoice(
            "Klausur entfernen",
            f"Was soll mit der Klausur „{selected.exam_name}“ passieren?",
            (
                ChoiceOption(
                    _REMOVE_UNREGISTER,
                    "Nur aus der Übersicht entfernen",
                    "Die Klausurdaten bleiben im Ordner und lassen sich über „Neue Klausur“ jederzeit wieder übernehmen.",
                ),
                ChoiceOption(
                    _REMOVE_DELETE_DATA,
                    "Klausurdaten im Ordner löschen",
                    "Löscht korrektor_klausur.json und korrektor_scores.csv. Die PDFs und Sicherungen der Scan-Werkstatt bleiben im Ordner.",
                ),
            ),
        )
        if choice is None:
            return
        repo = self._deps.exam_repository
        exam_file = selected.source_file
        try:
            if choice == _REMOVE_UNREGISTER:
                exam_id = repo.unregister_exam(exam_file)
                folder = exam_file.parent
                if exam_id is not None:
                    self._record_history_action(
                        description=f"Klausur aus der Übersicht entfernt: {selected.exam_name}",
                        undo=lambda: repo.registry.register(exam_id, folder),
                        redo=lambda: repo.registry.unregister(exam_id),
                        context="lifecycle",
                    )
                status = "Klausur aus der Übersicht entfernt (Daten bleiben im Ordner)"
            else:
                snapshot = repo.delete_exam_data(exam_file)
                self._record_history_action(
                    description=f"Klausurdaten gelöscht: {selected.exam_name}",
                    undo=lambda: repo.restore_exam_data(snapshot),
                    redo=lambda: repo.delete_exam_data(exam_file),
                    context="lifecycle",
                )
                status = "Klausurdaten gelöscht (PDFs bleiben im Ordner)"
        except Exception as exc:
            messagebox.showerror("Klausur konnte nicht entfernt werden", str(exc))
            return

        self._app.on_exam_deleted(selected.exam_id)
        self.refresh_exam_overview()
        self._app.set_status(status)


def _format_timestamp(value: str) -> str:
    """``2026-10-08T12:03:00.000000Z`` -> ``08.10.2026 12:03`` (UTC); unparseable values are shown as-is."""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return value or "unbekannt"
