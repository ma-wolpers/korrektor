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
        action = self._deps.undo_history.undo()
        if action is None:
            self._app.set_status("Nichts zum Rueckgaengigmachen")
            return False
        self._refresh_after_history_action(context=action.context)
        self._app.set_status(f"Rueckgaengig: {action.description}")
        return True

    def redo(self) -> bool:
        action = self._deps.undo_history.redo()
        if action is None:
            self._app.set_status("Nichts zum Wiederholen")
            return False
        self._refresh_after_history_action(context=action.context)
        self._app.set_status(f"Wiederholt: {action.description}")
        return True

    def _refresh_after_history_action(self, *, context: str) -> None:
        """Refresh the UI after an undo/redo, using the strategy the action's `context` calls for.

        `"lifecycle"` (exam created/deleted, index dir changed) keeps the
        previous behaviour: a full navigation reset back to the
        overview/detail hub via `sync_current_exam_from_repository()`, since
        the exam identity itself changed. `"content"` (the default - every
        mutation on an already-open exam: annotations, scores, regions, ...)
        instead reloads the exam data in place without resetting the active
        mode/view/selection, via `_refresh_exam_content_in_place()` - see
        that method's docstring for what is and isn't preserved.
        """
        self.refresh_exam_overview()
        if context == "lifecycle":
            self._app.sync_current_exam_from_repository()
        else:
            self._app.refresh_exam_content_in_place()

    def _record_history_action(self, *, description: str, undo, redo, context: str = "content") -> None:
        self._deps.undo_history.push(
            HistoryAction(
                description=description,
                undo=undo,
                redo=redo,
                context=context,
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
        context: str = "content",
    ) -> None:
        """Push one undo/redo entry that replays the given exam JSON snapshots.

        `before_payload`/`after_payload` must already be independent snapshots
        (e.g. a fresh `ExamProject.to_dict()` call) — `to_dict()` recursively
        builds new dicts/lists of primitive values with no references back to
        the live exam object, so callers must not deep-copy them again before
        passing them in here.

        `context` defaults to `"content"` (the exam stays open, only its data
        changed) since every current caller of this method mutates an
        already-open exam's content — see `HistoryAction.context` for what
        the two values mean.
        """
        exam_file = self._deps.exam_repository.index_root / f"{exam_id}.json"

        self._record_history_action(
            description=description,
            undo=lambda: self._write_exam_payload(exam_file, before_payload),
            redo=lambda: self._write_exam_payload(exam_file, after_payload),
            context=context,
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
