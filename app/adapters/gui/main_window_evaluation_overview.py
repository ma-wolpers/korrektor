"""Evaluation overview: one table, persons × tasks, with footer statistics and click navigation.

Columns: Name | one per task "1A (2)" | Σ | Note | Feedbackseite. Rows: every person
(``exam.students`` order, item id = ``student_id``), then footer rows (id ``footer:*``):
Ø, Ø %, Min–Max, bewertet x/n, fertig x/n. The table shows all rows (``height`` = row
count), so it never scrolls vertically itself - the wheel goes to the view's
``ScrollableFrame`` (bw-gui scroll rule); a horizontal scrollbar handles many tasks.

Clicks (``bind_click`` on the widget tag, before Tk's own Treeview selection):

* header of a task column, no modifier -> task view (consumed);
* name cell of a person row, no modifier -> person view (consumed, selection unchanged);
* everything else - incl. Ctrl/Shift clicks on names - passes on: Tk's native extended
  selection (Ctrl toggles, Shift extends). Footer rows are deselected right away.

Values come finished from ``ExamEvaluation`` (domain); this module only formats them.
"""

from __future__ import annotations

from app.adapters.gui import evaluation_format as fmt

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.contracts import KeyModifiers
from bw_gui.contracts.events import EventResult
from bw_gui.runtime import bind_click, on_treeview_select, treeview_selection, ui, widgets

FOOTER_PREFIX = "footer:"
_FOOTERS = ("avg", "avg_percent", "range", "scored", "finished")
_FOOTER_LABELS = {"avg": "Ø", "avg_percent": "Ø %", "range": "Min–Max", "scored": "bewertet", "finished": "fertig"}


class MainWindowEvaluationOverviewMixin:
    """Overview table of the evaluation window."""

    def _build_evaluation_overview(self, parent: widgets.Frame) -> None:
        """Hint, table with horizontal scrollbar, then actions and statistics blocks."""
        widgets.Label(
            parent, style="Muted.TLabel", justify=ui.LEFT,
            text="Klick auf einen Namen: Auswertung der Person · Klick auf eine Aufgabe: Auswertung der Aufgabe\n"
                 "Strg- bzw. Umschalt-Klick wählt mehrere Personen für Feedbackseite und Export aus.",
        ).pack(anchor=ui.W)
        table = widgets.Frame(parent)
        table.pack(fill=ui.X, pady=(6, 0))
        tree = widgets.Treeview(table, show="headings", selectmode="extended", height=4)
        scrollbar = widgets.Scrollbar(table, orient=ui.HORIZONTAL, command=tree.xview)
        tree.configure(xscrollcommand=scrollbar.set)
        tree.pack(fill=ui.X)
        scrollbar.pack(fill=ui.X)
        tree.tag_configure("footer", foreground="#6b7280")
        bind_click(tree, self._on_evaluation_overview_click)
        on_treeview_select(tree, lambda _change: self._drop_footer_selection())
        self._evaluation_overview_tree = tree
        self._evaluation_task_columns: list[str] = []
        self._build_evaluation_overview_actions(parent)
        self._build_evaluation_statistics(parent)

    def _configure_evaluation_columns(self) -> None:
        """(Re)create the columns when the task list changed; headings and widths."""
        tree = self._evaluation_overview_tree
        codes = [task.code for task in self._current_exam.tasks]
        columns = ("name", *(f"t{index}" for index in range(len(codes))), "sum", "grade", "feedback")
        if list(tree["columns"]) != list(columns) or codes != self._evaluation_task_columns:
            self._evaluation_task_columns = codes
            tree.configure(columns=columns, displaycolumns=columns)
        tree.heading("name", text="Name")
        tree.column("name", width=170, stretch=False)
        for index, task in enumerate(self._current_exam.tasks):
            tree.heading(f"t{index}", text=f"{task.code} ({task.max_points:g})")
            tree.column(f"t{index}", width=72, anchor=ui.CENTER, stretch=False)
        for column, text, width in (("sum", "Σ", 80), ("grade", "Note", 70), ("feedback", "Feedbackseite", 100)):
            tree.heading(column, text=text)
            tree.column(column, width=width, anchor=ui.CENTER, stretch=False)

    def _fill_evaluation_overview(self) -> None:
        """Refill rows and footers from ``_evaluation_data``; keeps the selected persons."""
        data = self._evaluation_data
        if data is None or self._current_exam is None:
            return
        tree = self._evaluation_overview_tree
        selected = [item for item in tree.selection() if not item.startswith(FOOTER_PREFIX)]
        self._configure_evaluation_columns()
        tree.delete(*tree.get_children())
        appended = {student.student_id: student.stats_report_appended for student in self._current_exam.students}
        for result in data.results:
            values = (
                result.display_name,
                *(fmt.number(task.achieved_points) for task in result.task_results),
                fmt.points(result.total_achieved_points, result.total_max_points),
                result.grade_label or fmt.UNSCORED,
                "✓" if appended.get(result.student_id) else "",
            )
            tree.insert("", ui.END, iid=result.student_id, values=values)
        for footer in _FOOTERS:
            cells = [self._evaluation_footer_cell(footer, stat) for stat in data.task_statistics]
            tree.insert("", ui.END, iid=f"{FOOTER_PREFIX}{footer}", values=(_FOOTER_LABELS[footer], *cells, "", "", ""), tags=("footer",))
        tree.configure(height=len(data.results) + len(_FOOTERS))
        treeview_selection.set(tree, [item for item in selected if tree.exists(item)])

    @staticmethod
    def _evaluation_footer_cell(footer: str, stat) -> str:
        """Text of one footer cell for one task."""
        if footer == "avg":
            return fmt.number(None if stat.average is None else round(stat.average, 2))
        if footer == "avg_percent":
            return fmt.percent(stat.average_percent)
        if footer == "range":
            return fmt.UNSCORED if stat.minimum is None else f"{stat.minimum:g}–{stat.maximum:g}"
        if footer == "scored":
            return fmt.count_of(stat.scored_count, stat.total_count)
        return fmt.count_of(stat.finished_count, stat.total_count)

    def _on_evaluation_overview_click(self, event):
        """Header click -> task view, name click -> person view; anything else stays a native selection click."""
        modifiers = event.modifiers
        if isinstance(modifiers, KeyModifiers) and (modifiers.control or modifiers.shift):
            return None
        tree = self._evaluation_overview_tree
        region = tree.identify_region(event.x, event.y)
        column = tree.identify_column(event.x)
        index = int(column[1:]) - 2 if column.startswith("#") and column[1:].isdigit() else -1
        if region == "heading" and 0 <= index < len(self._evaluation_task_columns):
            self._show_evaluation_task(self._evaluation_task_columns[index])
            return EventResult.HANDLED
        if region == "cell" and column == "#1":
            row = tree.identify_row(event.y)
            if row and not row.startswith(FOOTER_PREFIX):
                self._show_evaluation_person(row)
                return EventResult.HANDLED
        return None

    def _drop_footer_selection(self) -> None:
        """Footer rows are not selectable: remove them from the selection right away."""
        tree = self._evaluation_overview_tree
        footers = [item for item in tree.selection() if item.startswith(FOOTER_PREFIX)]
        if footers:
            treeview_selection.remove(tree, footers)

    def _evaluation_selected_ids(self) -> list[str]:
        """Selected persons in ``exam.students`` order (footers never count)."""
        selected = set(self._evaluation_overview_tree.selection())
        return [student.student_id for student in self._current_exam.students if student.student_id in selected]
