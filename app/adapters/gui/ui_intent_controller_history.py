from __future__ import annotations

from pathlib import Path

from bw_libs.app_paths import atomic_write_text
from app.adapters.undo import HistoryAction
from app.core.domain.models import ExamProject
from app.infrastructure.repositories.file_utils import atomic_write_json


class UiIntentControllerHistoryMixin:
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
