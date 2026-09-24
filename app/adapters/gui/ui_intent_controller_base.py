from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from app.adapters.bootstrap.wiring import GuiDependencies
from app.adapters.gui.dialog_services import messagebox
from app.core.domain.models import ExamProject
from app.core.domain.validation import ExamConflictError

if TYPE_CHECKING:
    from app.adapters.gui.main_window import MainWindow


class UiIntentControllerBase:
    def __init__(self, app: "MainWindow", deps: GuiDependencies) -> None:
        self._app = app
        self._deps = deps

    def _save_exam_guarded(self, exam: ExamProject) -> Path | None:
        """Shared choke point for every direct `exam_repository.save_exam(exam)` call.

        Catches `ExamConflictError` (see `JsonExamRepository.save_exam`) and
        reports it with a message box instead of letting it propagate as an
        unhandled exception - the mutation the caller already applied to
        `exam` in memory simply stays unsaved; the caller's own early-return
        contract (`None`/the original `exam`) decides what happens next.
        """
        try:
            return self._deps.exam_repository.save_exam(exam)
        except ExamConflictError as exc:
            messagebox.showerror("Speichern abgebrochen", str(exc))
            return None
