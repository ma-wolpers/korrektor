from __future__ import annotations

from typing import Sequence

from app.adapters.gui.dialog_services import messagebox
from app.adapters.gui.main_window_types import CorrectionTemplate
from app.core.domain.score_filter import compute_student_value


class MainWindowCorrectionCompletionMixin:
    @staticmethod
    def _are_all_tasks_scored(
        *, scores: dict[str, dict[str, float]], template: CorrectionTemplate, student_ids: Sequence[str],
    ) -> bool:
        """Check whether every one of the given students has scored every task in `template`.

        Pure check over already-loaded score data (`load_scores_for_exam`,
        loaded once by the caller) — no CSV I/O of its own, no access to
        `self`. Deliberately a `@staticmethod`: directly testable on the
        class (`MainWindow._are_all_tasks_scored(...)`) without constructing
        a real Tkinter instance. The single source of truth for "fully
        scored", used by both the per-person checkbox
        (`student_ids=[current student]`) and the region-wide bulk checkbox
        (`student_ids=<every correction person>`).

        `compute_student_value` (reused here purely for its "some task_code
        is missing -> None" presence check, its actual returned sum is
        discarded) already returns `None` for a student with no scores at
        all, since `scores.get(student_id, {})` then yields `{}` and every
        task lookup inside it misses.

        Zero students is explicitly NOT "all scored": `all(...)` over an
        empty sequence is vacuously `True`, which would wrongly let "nobody"
        pass as "fully done". The first line therefore short-circuits on an
        empty `student_ids` instead of falling through the empty `all(...)`.
        """
        if not student_ids:
            return False
        task_codes = [task.code for task in template.tasks]
        if not task_codes:
            return False
        return all(
            compute_student_value(scores.get(student_id, {}), task_codes) is not None
            for student_id in student_ids
        )

    def _all_tasks_scored_for_current_area(self) -> bool:
        """Whether the current student has scored every task of the current area.

        Thin wrapper kept only for `_on_correction_finished_toggled` (the
        single-person checkbox handler): loads the scores itself, once, and
        delegates the actual check to `_are_all_tasks_scored`.
        `_refresh_correction_completion_controls` no longer calls this - it
        loads `scores` once and calls `_are_all_tasks_scored` directly so
        the same CSV read serves both the single and the bulk check.
        """
        if self._controller is None or self._current_exam is None:
            return False
        student = self._current_correction_student()
        template = self._current_correction_template()
        if student is None or template is None:
            return False
        scores = self._controller.load_scores_for_exam(exam=self._current_exam)
        return self._are_all_tasks_scored(scores=scores, template=template, student_ids=[student.student_id])

    def _is_current_person_area_finished(self) -> bool:
        """Check the finished-flag for the current student on the current region."""
        if self._controller is None or self._current_exam is None:
            return False
        student = self._current_correction_student()
        template = self._current_correction_template()
        if student is None or template is None:
            return False
        return self._controller.is_person_area_finished(
            exam=self._current_exam,
            student_id=student.student_id,
            region_id=template.region_id,
        )

    def _correction_region_student_ids(self) -> list[str]:
        """The bulk-finished target population: unique student_ids in stable order.

        The one place that translates `self._correction_student_indices`
        into student_ids. De-duplicates explicitly (`dict.fromkeys`) - not
        because `_correction_student_indices` could contain duplicates today
        (the indices are already unique), but as a documented invariant:
        every caller (counter, bulk write, "all scored?" check) must receive
        the same, guaranteed-unique list, never independently recomputed,
        potentially diverging variants.
        """
        if self._current_exam is None:
            return []
        students = self._current_exam.students
        ids = [
            students[index].student_id
            for index in self._correction_student_indices
            if 0 <= index < len(students)
        ]
        return list(dict.fromkeys(ids))

    def _refresh_correction_completion_controls(self) -> None:
        """Refresh both the per-person and the region-wide bulk finished checkbox.

        Loads `scores` (via `load_scores_for_exam`) at most once per call
        and reuses that same loaded dict for the per-person check
        (`_are_all_tasks_scored` with a one-element `student_ids`) and the
        bulk check (`student_ids=self._correction_region_student_ids()`) -
        avoiding the O(N x M) CSV re-parse that calling
        `_all_tasks_scored_for_current_area` per person would cost here.
        """
        if self._correction_finished_check is None:
            return

        template = self._current_correction_template() if self._correction_mode_active else None
        student = self._current_correction_student() if self._correction_mode_active else None
        scores: dict[str, dict[str, float]] = {}
        if self._controller is not None and self._current_exam is not None and template is not None:
            scores = self._controller.load_scores_for_exam(exam=self._current_exam)

        can_toggle = (
            self._correction_mode_active
            and student is not None
            and template is not None
            and self._are_all_tasks_scored(scores=scores, template=template, student_ids=[student.student_id])
        )
        is_finished = self._is_current_person_area_finished() if self._correction_mode_active else False
        self._correction_finished_var.set(is_finished)

        self._correction_finished_check.configure(state="normal" if (can_toggle or is_finished) else "disabled")
        if is_finished:
            self._correction_finished_hint_var.set("Fertig markiert: Punkteingabe ist gesperrt")
        elif can_toggle:
            self._correction_finished_hint_var.set("Alle Aufgaben bewertet: Fertig kann gesetzt werden")
        else:
            self._correction_finished_hint_var.set("Fertig wird aktiv, sobald alle Aufgaben bewertet sind")

        self._correction_points_entry.configure(state="disabled" if is_finished else "normal")
        if self._save_correction_button is not None:
            self._save_correction_button.configure(state="disabled" if is_finished else "normal")

        if self._correction_finished_all_check is None:
            return

        if (
            not self._correction_mode_active
            or self._controller is None
            or self._current_exam is None
            or template is None
        ):
            self._correction_finished_all_var.set(False)
            self._correction_finished_all_check.state(["!alternate"])
            self._correction_finished_all_check.configure(state="disabled")
            self._correction_finished_all_hint_var.set("")
            return

        student_ids = self._correction_region_student_ids()
        total = len(student_ids)
        finished_count = self._controller.count_persons_area_finished(
            exam=self._current_exam, region_id=template.region_id, student_ids=student_ids
        )
        all_finished = total > 0 and finished_count == total
        any_finished = finished_count > 0
        all_scored = self._are_all_tasks_scored(scores=scores, template=template, student_ids=student_ids)
        # Equivalent to `any_finished or all_scored` (all_finished implies
        # any_finished for total > 0); spelled out to match the decision
        # table directly rather than writing an unexplained simplification.
        enabled = any_finished or (all_scored and not all_finished)

        self._correction_finished_all_var.set(all_finished)
        if 0 < finished_count < total:
            self._correction_finished_all_check.state(["alternate"])
        else:
            self._correction_finished_all_check.state(["!alternate"])
        self._correction_finished_all_check.configure(state="normal" if enabled else "disabled")
        self._correction_finished_all_hint_var.set(f"{finished_count}/{total} Personen fertig")

    def _on_correction_finished_toggled(self) -> None:
        """Persist the finished-checkbox state for the current student/region."""
        if not self._correction_mode_active or self._controller is None or self._current_exam is None:
            return

        student = self._current_correction_student()
        template = self._current_correction_template()
        if student is None or template is None:
            return

        requested = bool(self._correction_finished_var.get())
        if requested and not self._all_tasks_scored_for_current_area():
            self._correction_finished_var.set(False)
            messagebox.showinfo("Hinweis", "Bitte zuerst alle Aufgaben im Bereich bewerten.")
            self._refresh_correction_completion_controls()
            return

        updated = self._controller.set_persons_area_finished_immediate(
            exam=self._current_exam,
            student_ids=[student.student_id],
            region_id=template.region_id,
            is_finished=requested,
        )
        if updated is None:
            self._refresh_correction_completion_controls()
            return

        self._current_exam = updated
        self._apply_detail_labels(updated)
        self._refresh_correction_completion_controls()

    def _on_correction_finished_all_toggled(self) -> None:
        """Set/reset the finished flag for every person of the current region at once.

        Click semantics (tri-state, not a plain toggle of the raw checkbox
        value): nobody finished yet (0/N, unchecked) -> a click marks
        everyone finished, and requires every person to have scored every
        task first; anybody already finished (mixed N', alternate, or N/N,
        checked) -> a click resets everyone to "not finished", always
        allowed regardless of scoring completeness. So the only two cases
        are `finished_count == 0` (set) and `finished_count > 0` (reset) -
        deliberately not `finished_count != total`, which would wrongly
        treat a mixed state the same as the empty state and try to set
        instead of reset.

        Reads the actual `ExamProject`/persistence state to decide intent,
        not the Tkinter variable's own (already-flipped-by-Tk) value - the
        tri-state "alternate" display has no unambiguous single-bit
        "requested" meaning to read back from the widget itself.
        """
        if not self._correction_mode_active or self._controller is None or self._current_exam is None:
            self._refresh_correction_completion_controls()
            return

        template = self._current_correction_template()
        if template is None:
            self._refresh_correction_completion_controls()
            return

        student_ids = self._correction_region_student_ids()
        if not student_ids:
            # Only reachable if `exam.students` is empty, in which case the
            # bulk checkbox is already disabled (see
            # `_refresh_correction_completion_controls`: `total > 0` gates
            # `all_finished`/`enabled` via `all_scored`) - guarded here too
            # instead of relying solely on that disabled state.
            self._refresh_correction_completion_controls()
            return

        scores = self._controller.load_scores_for_exam(exam=self._current_exam)
        finished_count = self._controller.count_persons_area_finished(
            exam=self._current_exam, region_id=template.region_id, student_ids=student_ids
        )
        requested = finished_count == 0

        if requested and not self._are_all_tasks_scored(scores=scores, template=template, student_ids=student_ids):
            messagebox.showinfo("Hinweis", "Bitte zuerst alle Aufgaben aller Personen im Bereich bewerten.")
            self._refresh_correction_completion_controls()
            return

        updated = self._controller.set_persons_area_finished_immediate(
            exam=self._current_exam,
            student_ids=student_ids,
            region_id=template.region_id,
            is_finished=requested,
        )
        if updated is None:
            self._refresh_correction_completion_controls()
            return

        self._current_exam = updated
        self._apply_detail_labels(updated)
        self._refresh_correction_completion_controls()
