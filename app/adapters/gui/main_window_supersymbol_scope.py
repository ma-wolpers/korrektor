"""Supersymbol-Filter: Auswahl "Aufgabe(n)" - welche Aufgaben die Filter-Punktzahl bilden.

Aus `main_window_supersymbol.py` ausgelagert (Dateigroessen-Regel); dort liegen
Widgets, Filterstart und Platzieren.
"""

from __future__ import annotations

from app.adapters.gui.main_window_constants import SUPERSYMBOL_MAIN_TASK_SCOPE_LABEL, SUPERSYMBOL_SUM_SCOPE_LABEL
from app.adapters.gui.main_window_types import CorrectionTemplate
from app.core.domain.score_filter import main_task_sums
from app.core.domain.task_spec import TaskSpec, format_task_specs


class MainWindowSupersymbolScopeMixin:
    def _supersymbol_scope_options(self, template: CorrectionTemplate) -> dict[str, list[str]]:
        """``{Anzeigetext: task_codes}`` of every Supersymbol scope for ``template``, in display order.

        Each task of the template alone, then "Aufgabe N gesamt (…)" for every
        main task above them (all its subtasks in the exam, also those in
        other Bereichen - see `main_task_sums`), then "Summe aller Aufgaben"
        when the template has more than one task (a sum over a single task
        would just duplicate that task's own value). In the task-centric
        Korrekturmodus `_current_correction_template` holds only the current
        (sub)task, so the choice is in practice "2B" or "Aufgabe 2 gesamt".
        """
        region_codes = [task.code for task in template.tasks]
        options = {code: [code] for code in region_codes}
        exam_codes = [task.code for task in self._current_exam.tasks] if self._current_exam is not None else region_codes
        for main, members in main_task_sums(region_codes, exam_codes):
            listed = format_task_specs([TaskSpec(code, None) for code in members], separator=", ")
            options[SUPERSYMBOL_MAIN_TASK_SCOPE_LABEL.format(main=main, members=listed)] = members
        if len(region_codes) > 1:
            options[SUPERSYMBOL_SUM_SCOPE_LABEL] = region_codes
        return options

    def _refresh_supersymbol_scope_choices(self, template: CorrectionTemplate | None) -> None:
        """Populate the Supersymbol "Aufgabe(n)" scope combobox for the current Bereich (`_supersymbol_scope_options`).

        A still offered selection is kept; otherwise the first task is selected.
        """
        if template is None or not template.tasks:
            self._supersymbol_scope_combo["values"] = ()
            self._supersymbol_scope_var.set("")
            return
        values = tuple(self._supersymbol_scope_options(template))
        self._supersymbol_scope_combo["values"] = values
        if self._supersymbol_scope_var.get() not in values:
            self._supersymbol_scope_var.set(values[0])
        self._prefill_supersymbol_value_for_scope(template)

    def _on_supersymbol_scope_changed(self, _event: object) -> None:
        """Re-prefill the Punkte field whenever the "Aufgabe(n)"-Auswahl changes by hand."""
        self._prefill_supersymbol_value_for_scope(self._current_correction_template())

    def _prefill_supersymbol_value_for_scope(self, template: CorrectionTemplate | None) -> None:
        """Set the Supersymbol-Punktwert to the current scope's Maximalpunktwert-Summe.

        Runs both on Bereich-Wechsel (`_refresh_supersymbol_scope_choices`)
        and on manual Aufgabe(n)-Auswahl (`_on_supersymbol_scope_changed`),
        so the field always starts at a sensible default (the maximum
        achievable value for the current scope) instead of empty - the
        teacher can still overwrite it before starting the filter, this only
        saves typing the common case (Filter: "hat volle Punktzahl"). The
        maxima come from the whole exam, because "Aufgabe N gesamt" may
        include subtasks of other Bereiche.
        """
        if template is None:
            return
        task_codes = self._resolve_supersymbol_task_codes(template)
        if not task_codes:
            return
        tasks = self._current_exam.tasks if self._current_exam is not None else template.tasks
        max_points_by_code = {task.code: task.max_points for task in tasks}
        total_max_points = sum(max_points_by_code.get(code, 0.0) for code in task_codes)
        self._supersymbol_value_var.set(f"{total_max_points:g}")

    def _resolve_supersymbol_task_codes(self, template: CorrectionTemplate) -> list[str]:
        """Resolve the Supersymbol scope selection to a concrete task_code list.

        Fixed once, at filter-start time (Invariant: the bulk apply is a
        one-time action, not a live filter that would need to react to the
        Bereich's tasks changing later).
        """
        return list(self._supersymbol_scope_options(template).get(self._supersymbol_scope_var.get(), []))
