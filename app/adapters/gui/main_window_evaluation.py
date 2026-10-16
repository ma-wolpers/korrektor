"""The "Auswertung" window: one popup, four views (overview, person, task, symbols).

One modal window instead of nested ones (a second modal bw-gui popup would not hand the
input grab back to the first when it closes). The header with the view buttons stays
fixed; below it every view is its own bw-gui ``ScrollableFrame`` and only one of them is
packed at a time - exactly one visible vertical scroll area, no nesting. Views are built
once per opening and switched with ``pack``/``pack_forget``; returning to the overview
keeps its selection and scroll position.

Data: scores are loaded once per refresh (``load_scores_for_exam``); everything shown is
computed by the controller/domain (``compute_exam_evaluation_for_exam``), the views only
display it. ``_refresh_evaluation`` reloads after every change - the feedback page
actions and every content undo/redo (``refresh_exam_content_in_place``) - so the window
never shows a stale state.

Keys (window binder of the popup): ←/→ browse persons resp. tasks in the person/task
view (let through elsewhere), Backspace returns to the overview, Escape closes (bw-gui).
"""

from __future__ import annotations

from app.adapters.gui.dialog_services import messagebox
from app.adapters.gui.main_window_constants import COMPETENCY_CHART_SCOPE_LABELS, COMPETENCY_CHART_TYPE_LABELS

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.contracts.events import EventResult
from bw_gui.contracts.key_spec import KeySpec
from bw_gui.dialogs import ScrollablePopupWindow
from bw_gui.runtime import WindowShortcutBinder, ui, widgets
from bw_gui.widgets import ScrollableFrame

VIEWS = ("overview", "person", "task", "symbols")


class MainWindowEvaluationMixin:
    """Window shell of the evaluation: open, refresh, switch views, keys, close."""

    def _open_evaluation_popup(self) -> None:
        """Knopf „Auswertung“: open the window on the overview."""
        if self._controller is None or self._current_exam is None:
            return
        if not self._current_exam.students:
            messagebox.showinfo("Hinweis", "Diese Klausur hat keine Schüler:innen.")
            return
        self._build_evaluation_popup()
        self._evaluation_person_cursor = 0
        self._evaluation_task_cursor = 0
        self._refresh_evaluation()
        self._show_evaluation_view("overview")

    def _build_evaluation_popup(self) -> None:
        """Window, header, one ``ScrollableFrame`` per view, key bindings."""
        popup = ScrollablePopupWindow(
            self.root, title="Auswertung", geometry="1040x800", minsize=(640, 480),
            theme_key=self._tooltip_theme_key, scrollable=False,
        )
        header = widgets.Frame(popup.content, padding=(10, 10, 10, 0))
        header.pack(fill=ui.X)
        for text, view in (("Übersicht", "overview"), ("Symbole", "symbols")):
            widgets.Button(header, text=text, style="SecondaryAction.TButton",
                           command=lambda view=view: self._show_evaluation_view(view)).pack(side=ui.LEFT, padx=(0, 8))
        self._evaluation_title_var = ui.StringVar(value="")
        widgets.Label(header, textvariable=self._evaluation_title_var, style="Muted.TLabel").pack(side=ui.LEFT, padx=(8, 0))

        self._evaluation_chart_type_var = ui.StringVar(value=COMPETENCY_CHART_TYPE_LABELS[0])
        self._evaluation_chart_scope_var = ui.StringVar(value=COMPETENCY_CHART_SCOPE_LABELS[0])
        self._evaluation_views = {view: ScrollableFrame(popup.content) for view in VIEWS}
        self._evaluation_photos = {}
        self._build_evaluation_overview(self._evaluation_views["overview"].content)
        self._build_evaluation_person(self._evaluation_views["person"].content)
        self._build_evaluation_task(self._evaluation_views["task"].content)
        self._build_evaluation_symbols(self._evaluation_views["symbols"].content)

        keys = WindowShortcutBinder(popup)
        for notation, handler, binding_id, in_text in (
            ("Left (tolerate: Shift)", lambda _e: self._on_evaluation_arrow(-1), "evaluation.prev", True),
            ("Right (tolerate: Shift)", lambda _e: self._on_evaluation_arrow(1), "evaluation.next", True),
            ("Backspace", lambda _e: self._on_evaluation_back(), "evaluation.back", False),
        ):
            keys.bind(KeySpec.parse(notation), handler, binding_id=binding_id, intent=binding_id, allow_when_text_input=in_text)
        self._evaluation_popup = popup
        self._evaluation_view = ""

    def _evaluation_open(self) -> bool:
        """True while the evaluation window exists."""
        popup = self._evaluation_popup
        return popup is not None and bool(popup.winfo_exists())

    def _refresh_evaluation(self) -> None:
        """Reload scores and exam data, then refill every view (keeps view, cursors and overview selection)."""
        if not self._evaluation_open() or self._controller is None or self._current_exam is None:
            return
        exam = self._current_exam
        self._evaluation_scores = self._controller.load_scores_for_exam(exam=exam)
        self._evaluation_data = self._controller.compute_exam_evaluation_for_exam(exam=exam, scores=self._evaluation_scores)
        self._evaluation_person_cursor %= max(1, len(exam.students))
        self._evaluation_task_cursor %= max(1, len(exam.tasks))
        self._fill_evaluation_overview()
        self._fill_evaluation_statistics()
        if self._evaluation_view == "person":
            self._fill_evaluation_person()
        elif self._evaluation_view == "task":
            self._fill_evaluation_task()
        elif self._evaluation_view == "symbols":
            self._fill_evaluation_symbols()

    def _refresh_evaluation_if_open(self) -> None:
        """Hook for in-place exam reloads (undo/redo): refresh the window if it is open."""
        if self._evaluation_open():
            self._refresh_evaluation()

    def _show_evaluation_view(self, view: str) -> None:
        """Make ``view`` the visible one; detail views are filled and scrolled to the top."""
        if not self._evaluation_open() or view not in VIEWS:
            return
        if view == "person":
            self._fill_evaluation_person()
        elif view == "task":
            self._fill_evaluation_task()
        elif view == "symbols":
            self._fill_evaluation_symbols()
        for name, frame in self._evaluation_views.items():
            if name != view:
                frame.pack_forget()
        frame = self._evaluation_views[view]
        frame.pack(fill=ui.BOTH, expand=True, padx=10, pady=10)
        if view != "overview":
            frame.canvas.yview_moveto(0)
        self._evaluation_view = view
        self._evaluation_title_var.set({"overview": "Gesamtübersicht", "person": "Person", "task": "Aufgabe",
                                        "symbols": "Verwendete Symbole"}[view])

    def _show_evaluation_person(self, student_id: str) -> None:
        """Open the person view on ``student_id``."""
        ids = [student.student_id for student in self._current_exam.students] if self._current_exam else []
        if student_id in ids:
            self._evaluation_person_cursor = ids.index(student_id)
            self._show_evaluation_view("person")

    def _show_evaluation_task(self, task_code: str) -> None:
        """Open the task view on ``task_code``."""
        codes = [task.code for task in self._current_exam.tasks] if self._current_exam else []
        if task_code in codes:
            self._evaluation_task_cursor = codes.index(task_code)
            self._show_evaluation_view("task")

    def _on_evaluation_arrow(self, delta: int):
        """←/→: browse persons/tasks in the detail views; let the key through elsewhere."""
        if self._current_exam is None:
            return None
        if self._evaluation_view == "person" and self._current_exam.students:
            self._evaluation_person_cursor = (self._evaluation_person_cursor + delta) % len(self._current_exam.students)
            self._fill_evaluation_person()
            return EventResult.HANDLED
        if self._evaluation_view == "task" and self._current_exam.tasks:
            self._evaluation_task_cursor = (self._evaluation_task_cursor + delta) % len(self._current_exam.tasks)
            self._fill_evaluation_task()
            return EventResult.HANDLED
        return None

    def _on_evaluation_back(self):
        """Backspace: back to the overview from a detail view."""
        if self._evaluation_view in ("person", "task", "symbols"):
            self._show_evaluation_view("overview")
            return EventResult.HANDLED
        return None

    def _close_evaluation_popup(self) -> None:
        """Close the window (one-shot popup, rebuilt on the next opening)."""
        if self._evaluation_open():
            self._evaluation_popup._request_close()
