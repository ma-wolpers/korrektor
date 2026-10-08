from __future__ import annotations

from pathlib import Path

import fitz

from app.adapters.gui.dialog_services import messagebox, simpledialog
from app.core.domain.models import ExamProject
from app.core.domain.page_coverage import (
    compute_uncovered_pages,
    plan_page_for_all,
    unscored_set,
    unscored_state_for_all,
    uncovered_for_all,
)

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui, widgets
from bw_gui.widgets import Switch


class MainWindowExtraPagesMixin:
    """Zuschnitt, Schritt 2: walk every page without a template region and decide what it is.

    Each such page (1-based within its student's PDF) is either assigned to
    existing area(s) or marked "ohne Bewertung" (Entf toggles). For a page
    number that has no region for *everybody* (e.g. a Deckblatt) both
    decisions are also offered "für alle Personen": a switch with a mixed
    state for "ohne Bewertung" and a button for the assignment. "Für alle"
    never overwrites conscious individual decisions - see
    `page_coverage.plan_page_for_all`.

    Internal names keep the former "extra" wording (`_extra_mode_active`,
    `_detail_submode == "extra"`); only visible texts changed.
    """

    def _build_reading_view_extra_toolbar(self) -> None:
        self._extra_toolbar = widgets.Frame(self._reading_view, style="Surface.TFrame")
        self._extra_toolbar.pack(fill=ui.X, pady=(6, 0))
        prev_extra_page_button = widgets.Button(
            self._extra_toolbar, text="◀ Seite", style="SecondaryAction.TButton", command=lambda: self._change_extra_page(-1)
        )
        prev_extra_page_button.pack(side=ui.LEFT)
        self._attach_hover_help(prev_extra_page_button, label="Vorherige Seite ohne Bereich", shortcut="Links")
        next_extra_page_button = widgets.Button(
            self._extra_toolbar, text="Seite ▶", style="SecondaryAction.TButton", command=lambda: self._change_extra_page(1)
        )
        next_extra_page_button.pack(side=ui.LEFT, padx=(8, 0))
        self._attach_hover_help(next_extra_page_button, label="Nächste Seite ohne Bereich", shortcut="Rechts")

        self._unscored_var = ui.BooleanVar(value=False)
        self._unscored_switch = Switch(
            self._extra_toolbar, text="Ohne Bewertung", variable=self._unscored_var, on_change=self._on_unscored_switch
        )
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

        assign_extra_page_button = widgets.Button(
            self._extra_toolbar, text="Bereich zuordnen", style="PrimaryAction.TButton", command=self._assign_current_extra_page
        )
        assign_extra_page_button.pack(side=ui.RIGHT)
        self._attach_hover_help(assign_extra_page_button, label="Diese Seite einem Bereich zuordnen", shortcut=None)
        self._assign_all_button = widgets.Button(
            self._extra_toolbar, text="Für alle zuordnen…", style="SecondaryAction.TButton", command=self._assign_page_for_all
        )
        self._assign_all_button.pack(side=ui.RIGHT, padx=(0, 8))

    @staticmethod
    def _build_extra_sequence(exam: ExamProject) -> list[tuple[int, int]]:
        """``[(student_index, page)]`` of every page without a template region (handled ones included)."""
        uncovered = compute_uncovered_pages(exam)
        return [
            (student_index, page)
            for student_index, student in enumerate(exam.students)
            for page in uncovered.get(student.pdf_filename, [])
        ]

    def _start_extra_mode(self) -> None:
        """Enter Zuschnitt Schritt 2, resetting any active reading/naming/correction mode."""
        if not self._current_exam:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Klausur öffnen.")
            return
        sequence = self._build_extra_sequence(self._current_exam)
        if not sequence:
            messagebox.showinfo("Hinweis", "Alle Seiten liegen in einem Bereich - Schritt 2 ist nicht nötig.")
            return

        self._reading_active = False
        self._extra_mode_active = True
        self._naming_mode_active = False
        self._naming_capture_active = False
        self._superpage_var.set(False)
        self._stop_correction_mode(silent=True)
        self._extra_sequence = sequence
        self._extra_cursor = 0
        self._selected_region_id = None
        self._selected_region_kind = None
        self._set_detail_submode("extra")
        self._show_view("reading")
        self._refresh_region_tree()
        self._render_current_extra_page()
        self._status_var.set("Zuschnitt · Schritt 2 aktiv")

    def _toggle_zuschnitt_step(self) -> None:
        """Step button: Schritt 1 (Bereiche) ↔ Schritt 2 (Seiten ohne Bereich)."""
        if self._extra_mode_active:
            self._start_reading_mode()
        else:
            self._start_extra_mode()

    def _change_extra_page(self, delta: int) -> None:
        if not self._extra_mode_active or not self._extra_sequence:
            return
        self._extra_cursor = (self._extra_cursor + delta) % len(self._extra_sequence)
        self._render_current_extra_page()

    def _current_extra_target(self):
        """Return ``(student, page_number)`` of the current step-2 page, or ``None``."""
        if not self._current_exam or not self._extra_sequence:
            return None
        student_index, page_number = self._extra_sequence[self._extra_cursor]
        return self._current_exam.students[student_index], page_number

    def _render_current_extra_page(self) -> None:
        target = self._current_extra_target()
        if target is None:
            return
        student, page_number = target
        self._render_pdf_page(student=student, page_number=page_number)
        assigned = self._areas_for_extra_page(student.pdf_filename, page_number)
        unscored = (student.pdf_filename, page_number) in unscored_set(self._current_exam)
        state = f"Bereich: {','.join(assigned)}" if assigned else ("ohne Bewertung" if unscored else "offen")
        self._reading_info_var.set(
            f"Seite ohne Bereich {self._extra_cursor + 1}/{len(self._extra_sequence)} | {student.display_name} | Seite {page_number} | {state}"
        )
        self._unscored_var.set(unscored)
        self._unscored_switch.configure(state="disabled" if assigned else "normal")
        self._refresh_for_all_controls(page_number)

    def _refresh_for_all_controls(self, page_number: int) -> None:
        """Show the "für alle" switch/button only for a page number that has no region for everybody."""
        exam = self._current_exam
        if page_number not in uncovered_for_all(exam):
            self._unscored_all_switch.pack_forget()
            self._assign_all_button.pack_forget()
            return
        plan = plan_page_for_all(exam, page_number, "unscore")
        excluded = f" ({len(plan.excluded)} zugeordnet, bleiben unverändert)" if plan.excluded else ""
        self._unscored_all_switch.configure(text=f"Seite {page_number} bei allen ohne Bewertung{excluded}")
        self._unscored_all_switch.pack(side=ui.LEFT, padx=(16, 0))
        self._assign_all_button.pack(side=ui.RIGHT, padx=(0, 8))
        state = unscored_state_for_all(exam, page_number)
        self._unscored_all_var.set(state == "on")
        self._unscored_all_switch.set_mixed(state == "mixed")

    def _apply_updated_exam(self, updated) -> None:
        if updated is None:
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
        """Entf in Schritt 2: toggle "Ohne Bewertung" (not for pages already assigned to an area)."""
        target = self._current_extra_target()
        if target is None:
            return
        student, page_number = target
        if self._areas_for_extra_page(student.pdf_filename, page_number):
            self._status_var.set("Seite ist einem Bereich zugeordnet - zuerst die Zuordnung löschen")
            return
        self._on_unscored_switch(not self._unscored_var.get())

    def _on_unscored_all_switch(self, requested: bool) -> None:
        """"Seite N bei allen ohne Bewertung": assigned pages are never touched (see plan_page_for_all)."""
        target = self._current_extra_target()
        if target is None or self._controller is None:
            return
        _student, page_number = target
        plan = plan_page_for_all(self._current_exam, page_number, "unscore")
        pdfs = list(plan.affected) if requested else list(plan.unchanged)
        if not pdfs:
            self._render_current_extra_page()
            return
        self._apply_updated_exam(
            self._controller.set_pages_unscored_immediate(
                exam=self._current_exam, student_pdfs=pdfs, page_number=page_number, unscored=requested
            )
        )

    def _areas_for_extra_page(self, student_pdf: str, page_number: int) -> list[str]:
        if not self._current_exam:
            return []
        result: list[str] = []
        for assignment in self._current_exam.extra_page_assignments:
            if assignment.student_pdf == student_pdf and assignment.page_number == page_number:
                for code in assignment.assigned_area_codes:
                    if code not in result:
                        result.append(code)
        return result

    def _ask_extra_area_codes(self, title: str) -> list[str] | None:
        default_areas = ",".join(self._existing_standard_areas()[:1] or ["A"])
        raw_areas = simpledialog.askstring(title, "Bestehende Bereich(e) eingeben (z. B. A,B)", initialvalue=default_areas)
        if raw_areas is None:
            return None
        return [item.strip().upper() for item in raw_areas.split(",") if item.strip()]

    def _assign_current_extra_page(self) -> None:
        if not self._extra_mode_active or not self._extra_sequence or not self._current_exam or not self._controller:
            return
        student, page_number = self._current_extra_target()
        area_codes = self._ask_extra_area_codes("Seite zuordnen")
        if area_codes is None or self._render_photo is None:
            return
        canvas_width = float(self._reading_canvas.winfo_width())
        canvas_height = float(self._reading_canvas.winfo_height())
        box = (0.0, 0.0, canvas_width * self._x_factor, canvas_height * self._y_factor)
        self._apply_updated_exam(
            self._controller.assign_extra_page_immediate(
                exam=self._current_exam, student_pdf=student.pdf_filename, page_number=page_number, box=box, area_codes=area_codes
            )
        )

    def _assign_page_for_all(self) -> None:
        """"Für alle zuordnen…": only students whose page N is neither assigned nor "ohne Bewertung"."""
        target = self._current_extra_target()
        if target is None or self._controller is None:
            return
        _student, page_number = target
        plan = plan_page_for_all(self._current_exam, page_number, "assign")
        if not plan.affected:
            messagebox.showinfo("Nichts zu tun", f"Seite {page_number} ist bei allen schon entschieden.")
            return
        area_codes = self._ask_extra_area_codes(f"Seite {page_number} für {len(plan.affected)} Person(en) zuordnen")
        if area_codes is None:
            return
        box_by_pdf = {pdf: self._full_page_box(pdf, page_number) for pdf in plan.affected}
        self._apply_updated_exam(
            self._controller.assign_extra_pages_for_all_immediate(
                exam=self._current_exam, page_number=page_number, box_by_pdf=box_by_pdf, area_codes=area_codes
            )
        )

    def _full_page_box(self, pdf_filename: str, page_number: int) -> tuple[float, float, float, float]:
        """The extra-page box model: the whole visible page ``(0, 0, width, height)`` in PDF points."""
        document = self._doc_cache.get(pdf_filename)
        if document is None:
            document = fitz.open(Path(self._current_exam.folder_path) / pdf_filename)
            self._doc_cache[pdf_filename] = document
        rect = document.load_page(page_number - 1).rect
        return (0.0, 0.0, float(rect.width), float(rect.height))
