from __future__ import annotations

from app.adapters.gui.dialog_services import messagebox
from app.core.domain.models import ExamProject
from app.core.domain.page_coverage import (
    all_pages,
    assigned_set,
    compute_uncovered_pages,
    plan_page_for_all,
    template_page_numbers,
    unscored_set,
    unscored_state_for_all,
    uncovered_for_all,
)

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui, widgets
from bw_gui.widgets import Switch


class MainWindowExtraPagesMixin:
    """Zuschnitt, Schritt 2 ("Einzelseiten"): mark task regions on single students' pages.

    Same principle as Schritt 1: draw a box, type the tasks (shorthand,
    points optional for existing tasks) or tick them in the checklist - the
    box becomes an Einzelseiten-Bereich of that student holding the *same*
    tasks as the Superseiten-Bereiche. Navigation walks the pages without a
    Superseiten-Bereich (`page_coverage.compute_uncovered_pages`, handled
    pages included); the switch "Auch Seiten mit Superseiten-Bereich" walks
    every page and shows the Superseiten-Bereiche in grey. A page without a
    region can be marked "ohne Bewertung" (Entf toggles), also "Seite N bei
    allen" - never overwriting pages that carry an Einzelseiten-Bereich
    (`page_coverage.plan_page_for_all`).

    Internal names keep the former "extra" wording (`_extra_mode_active`,
    `_detail_submode == "extra"`); only visible texts changed.
    """

    def _build_reading_view_extra_toolbar(self) -> None:
        """Navigation, "Ohne Bewertung", "bei allen" and the all-pages switch."""
        self._extra_toolbar = widgets.Frame(self._reading_view, style="Surface.TFrame")
        self._extra_toolbar.pack(fill=ui.X, pady=(6, 0))
        prev_button = widgets.Button(self._extra_toolbar, text="◀ Seite", style="SecondaryAction.TButton", command=lambda: self._change_extra_page(-1))
        prev_button.pack(side=ui.LEFT)
        self._attach_hover_help(prev_button, label="Vorherige Einzelseite", shortcut="Links")
        next_button = widgets.Button(self._extra_toolbar, text="Seite ▶", style="SecondaryAction.TButton", command=lambda: self._change_extra_page(1))
        next_button.pack(side=ui.LEFT, padx=(8, 0))
        self._attach_hover_help(next_button, label="Nächste Einzelseite", shortcut="Rechts")

        self._unscored_var = ui.BooleanVar(value=False)
        self._unscored_switch = Switch(self._extra_toolbar, text="Ohne Bewertung", variable=self._unscored_var, on_change=self._on_unscored_switch)
        self._unscored_switch.pack(side=ui.LEFT, padx=(16, 0))
        self._attach_hover_help(self._unscored_switch, label="Diese Seite nicht bewerten", shortcut="Entf")

        self._unscored_all_var = ui.BooleanVar(value=False)
        self._unscored_all_switch = Switch(
            self._extra_toolbar,
            text="Bei allen ohne Bewertung",
            variable=self._unscored_all_var,
            on_change=self._on_unscored_all_switch,
            mixed_click_target=True,
        )
        self._unscored_all_switch.pack(side=ui.LEFT, padx=(16, 0))

        all_pages_switch = Switch(
            self._extra_toolbar,
            text="Auch Seiten mit Superseiten-Bereich",
            variable=self._extra_all_pages_var,
            on_change=self._on_extra_all_pages_switch,
        )
        all_pages_switch.pack(side=ui.RIGHT)
        self._attach_hover_help(all_pages_switch, label="Alle Seiten zeigen, z. B. wenn jemand außerhalb des Kastens weitergeschrieben hat", shortcut=None)

    def _build_extra_sequence(self, exam: ExamProject) -> list[tuple[int, int]]:
        """``[(student_index, page)]`` to walk: pages without a Superseiten-Bereich, or all pages with the switch on."""
        pages = all_pages(exam) if self._extra_all_pages_var.get() else compute_uncovered_pages(exam)
        return [(index, page) for index, student in enumerate(exam.students) for page in pages.get(student.pdf_filename, [])]

    def _start_extra_mode(self) -> None:
        """Enter Zuschnitt Schritt 2, resetting any active reading/naming/correction mode."""
        if not self._current_exam:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Klausur öffnen.")
            return
        sequence = self._build_extra_sequence(self._current_exam)
        if not sequence:
            self._extra_all_pages_var.set(True)
            sequence = self._build_extra_sequence(self._current_exam)
            self._status_var.set("Alle Seiten liegen in Superseiten-Bereichen – es werden alle Seiten gezeigt.")
        if not sequence:
            return
        self._reading_active = False
        self._extra_mode_active = True
        self._superpage_var.set(False)
        self._stop_correction_mode(silent=True)
        self._extra_sequence = sequence
        self._extra_cursor = 0
        self._selected_region_id = None
        self._selected_region_kind = None
        self._set_detail_submode("extra")
        self._show_view("reading")
        self._show_current_extra_page()

    def _toggle_zuschnitt_step(self) -> None:
        """Step button: Schritt 1 (Superseiten) ↔ Schritt 2 (Einzelseiten)."""
        if self._extra_mode_active:
            self._start_reading_mode()
        else:
            self._start_extra_mode()

    def _on_extra_all_pages_switch(self, requested: bool) -> None:
        """Switch "Auch Seiten mit Superseiten-Bereich": rebuild the walk, stay on the same student/page if possible."""
        self._extra_all_pages_var.set(requested)
        if not self._extra_mode_active or self._current_exam is None:
            return
        current = self._extra_sequence[self._extra_cursor] if self._extra_sequence else None
        sequence = self._build_extra_sequence(self._current_exam)
        if not sequence:
            self._extra_all_pages_var.set(True)
            return
        self._extra_sequence = sequence
        self._extra_cursor = sequence.index(current) if current in sequence else 0
        self._show_current_extra_page()

    def _change_extra_page(self, delta: int) -> None:
        """←/→ and the buttons: previous/next page of the walk (wraps around)."""
        if not self._extra_mode_active or not self._extra_sequence:
            return
        self._extra_cursor = (self._extra_cursor + delta) % len(self._extra_sequence)
        self._show_current_extra_page()

    def _show_current_extra_page(self) -> None:
        """New page: clear the selection, refresh list/checklist and render."""
        self._selected_region_id = None
        self._selected_region_kind = None
        self._active_region_var.set("-")
        self._show_task_specs_in_editor([])
        self._refresh_region_tree()
        self._refresh_task_checklist()
        self._render_current_extra_page()

    def _current_extra_target(self):
        """Return ``(student, page_number)`` of the current step-2 page, or ``None``."""
        if not self._current_exam or not self._extra_sequence:
            return None
        student_index, page_number = self._extra_sequence[self._extra_cursor]
        return self._current_exam.students[student_index], page_number

    def _render_current_extra_page(self) -> None:
        """Render the page and update the info line and the "ohne Bewertung" controls."""
        target = self._current_extra_target()
        if target is None:
            return
        student, page_number = target
        exam = self._current_exam
        self._render_pdf_page(student=student, page_number=page_number)
        labels = [
            region.assigned_area_codes[0]
            for region in exam.regions
            if region.student_pdf == student.pdf_filename and region.page_number == page_number and region.assigned_area_codes
        ]
        on_superseite = page_number in template_page_numbers(exam)
        unscored = (student.pdf_filename, page_number) in unscored_set(exam)
        state = f"Bereiche: {', '.join(labels)}" if labels else ("ohne Bewertung" if unscored else ("Superseite" if on_superseite else "offen"))
        self._reading_info_var.set(
            f"Einzelseite {self._extra_cursor + 1}/{len(self._extra_sequence)} | {student.display_name} | Seite {page_number} | {state}"
        )
        self._unscored_var.set(unscored)
        self._unscored_switch.configure(state="disabled" if labels or on_superseite else "normal")
        self._refresh_for_all_controls(page_number)

    def _refresh_for_all_controls(self, page_number: int) -> None:
        """Show "Seite N bei allen ohne Bewertung" only for a page number without a Superseiten-Bereich for everybody."""
        exam = self._current_exam
        if page_number not in uncovered_for_all(exam):
            self._unscored_all_switch.pack_forget()
            return
        plan = plan_page_for_all(exam, page_number)
        excluded = f" ({len(plan.excluded)} mit Bereich, bleiben unverändert)" if plan.excluded else ""
        self._unscored_all_switch.configure(text=f"Seite {page_number} bei allen ohne Bewertung{excluded}")
        self._unscored_all_switch.pack(side=ui.LEFT, padx=(16, 0))
        state = unscored_state_for_all(exam, page_number)
        self._unscored_all_var.set(state == "on")
        self._unscored_all_switch.set_mixed(state == "mixed")

    def _apply_updated_exam(self, updated) -> None:
        """Take over an updated exam after a step-2 action (``None`` = rejected: just re-render the unchanged state)."""
        if updated is None:
            self._render_current_extra_page()
            return
        self._current_exam = updated
        self._apply_detail_labels(updated)
        self._render_current_extra_page()

    def _on_unscored_switch(self, requested: bool) -> None:
        """Switch "Ohne Bewertung" for the current page (one undo step)."""
        target = self._current_extra_target()
        if target is None or self._controller is None:
            return
        student, page_number = target
        self._apply_updated_exam(
            self._controller.set_pages_unscored_immediate(
                exam=self._current_exam, student_pdfs=[student.pdf_filename], page_number=page_number, unscored=requested
            )
        )

    def _toggle_current_page_unscored(self) -> None:
        """Entf in Schritt 2 (nothing selected): toggle "Ohne Bewertung" - not for pages carrying a region."""
        target = self._current_extra_target()
        if target is None:
            return
        student, page_number = target
        if (student.pdf_filename, page_number) in assigned_set(self._current_exam) or page_number in template_page_numbers(self._current_exam):
            self._status_var.set("Auf dieser Seite liegt ein Bereich - sie wird bewertet")
            return
        self._on_unscored_switch(not self._unscored_var.get())

    def _on_unscored_all_switch(self, requested: bool) -> None:
        """"Seite N bei allen ohne Bewertung": pages with an Einzelseiten-Bereich are never touched (see plan_page_for_all)."""
        target = self._current_extra_target()
        if target is None or self._controller is None:
            return
        _student, page_number = target
        plan = plan_page_for_all(self._current_exam, page_number)
        pdfs = list(plan.affected) if requested else list(plan.unchanged)
        if not pdfs:
            self._render_current_extra_page()
            return
        self._apply_updated_exam(
            self._controller.set_pages_unscored_immediate(exam=self._current_exam, student_pdfs=pdfs, page_number=page_number, unscored=requested)
        )
