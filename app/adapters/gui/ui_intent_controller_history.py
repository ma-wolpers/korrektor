from __future__ import annotations

from pathlib import Path

from bw_libs.app_paths import atomic_write_text
from app.adapters.gui.dialog_services import messagebox
from app.adapters.undo import HistoryAction


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
        """Undo the newest action; asks first if it carries a ``confirm_text``; reports failures."""
        pending = self._deps.undo_history.peek_undo_action()
        if pending is not None and pending.confirm_text and not messagebox.askyesno("Rückgängig", pending.confirm_text):
            return False
        try:
            action = self._deps.undo_history.undo()
        except Exception as exc:
            messagebox.showerror("Rückgängig nicht möglich", str(exc))
            return False
        if action is None:
            self._app.set_status("Nichts zum Rückgängigmachen")
            return False
        self._refresh_after_history_action(context=action.context)
        self._app.set_status(f"Rückgängig: {action.description}")
        return True

    def redo(self) -> bool:
        """Redo the newest undone action; asks first if it carries a ``confirm_text``; reports failures."""
        pending = self._deps.undo_history.peek_redo_action()
        if pending is not None and pending.confirm_text and not messagebox.askyesno("Wiederholen", pending.confirm_text):
            return False
        try:
            action = self._deps.undo_history.redo()
        except Exception as exc:
            messagebox.showerror("Wiederholen nicht möglich", str(exc))
            return False
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

    def _record_history_action(
        self, *, description: str, undo, redo, context: str = "content", confirm_text: str | None = None
    ) -> None:
        self._deps.undo_history.push(
            HistoryAction(
                description=description,
                undo=undo,
                redo=redo,
                context=context,
                confirm_text=confirm_text,
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

    def _write_exam_payload(self, exam_file: Path, payload: dict[str, object]) -> None:
        """Write a full exam snapshot for undo/redo (atomic, folder file, re-registers the exam)."""
        self._deps.exam_repository.write_exam_payload(exam_file, payload)

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
        # The snapshot itself says where the exam lives (folder_path is always
        # the folder the exam was loaded from), so no registry lookup is needed.
        exam_file = self._deps.exam_repository.exam_file_for_folder(Path(str(after_payload["folder_path"])))

        self._record_history_action(
            description=description,
            undo=lambda: self._write_exam_payload(exam_file, before_payload),
            redo=lambda: self._write_exam_payload(exam_file, after_payload),
            context=context,
        )
