from __future__ import annotations

from pathlib import Path

import fitz

from app.adapters.gui.dialog_services import messagebox, simpledialog
from app.core.domain.models import ExamProject

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui, widgets


class MainWindowExtraPagesMixin:
    def _build_reading_view_extra_toolbar(self) -> None:
        self._extra_toolbar = widgets.Frame(self._reading_view, style="Surface.TFrame")
        self._extra_toolbar.pack(fill=ui.X, pady=(6, 0))
        prev_extra_page_button = widgets.Button(
            self._extra_toolbar,
            text="◀ Extraseite",
            style="SecondaryAction.TButton",
            command=lambda: self._change_extra_page(-1),
        )
        prev_extra_page_button.pack(side=ui.LEFT)
        self._attach_hover_help(prev_extra_page_button, label="Vorherige Extraseite", shortcut=None)

        next_extra_page_button = widgets.Button(
            self._extra_toolbar,
            text="Extraseite ▶",
            style="SecondaryAction.TButton",
            command=lambda: self._change_extra_page(1),
        )
        next_extra_page_button.pack(side=ui.LEFT, padx=(8, 0))
        self._attach_hover_help(next_extra_page_button, label="Naechste Extraseite", shortcut=None)

        assign_extra_page_button = widgets.Button(
            self._extra_toolbar,
            text="Bereich zuordnen",
            style="PrimaryAction.TButton",
            command=self._assign_current_extra_page,
        )
        assign_extra_page_button.pack(side=ui.RIGHT)
        self._attach_hover_help(assign_extra_page_button, label="Aktuelle Extraseite einem Bereich zuordnen", shortcut=None)

    @staticmethod
    def _build_extra_sequence(exam: ExamProject) -> list[tuple[int, int]]:
        sequence: list[tuple[int, int]] = []
        for student_index, student in enumerate(exam.students):
            for page in sorted(student.extra_pages):
                sequence.append((student_index, page))
        return sequence

    def _start_extra_mode(self) -> None:
        """Enter Extraseiten-Modus, resetting any active reading/naming/correction mode."""
        if not self._current_exam:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Klausur öffnen.")
            return
        sequence = self._build_extra_sequence(self._current_exam)
        if not sequence:
            messagebox.showinfo("Hinweis", "Für diese Klausur sind keine Extraseiten vorhanden.")
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
        self._status_var.set("Extraseiten-Modus aktiv")

    def _change_extra_page(self, delta: int) -> None:
        if not self._extra_mode_active or not self._extra_sequence:
            return
        self._extra_cursor = (self._extra_cursor + delta) % len(self._extra_sequence)
        self._render_current_extra_page()

    def _render_current_extra_page(self) -> None:
        if not self._current_exam or not self._extra_sequence:
            return

        student_index, page_number = self._extra_sequence[self._extra_cursor]
        student = self._current_exam.students[student_index]
        self._render_pdf_page(student=student, page_number=page_number)

        assigned = self._areas_for_extra_page(student.pdf_filename, page_number)
        assigned_text = f" | Bereich: {','.join(assigned)}" if assigned else " | Bereich: -"
        self._reading_info_var.set(
            f"Extraseite {self._extra_cursor + 1}/{len(self._extra_sequence)} | {student.display_name} | Seite {page_number}{assigned_text}"
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

    def _assign_current_extra_page(self) -> None:
        if not self._extra_mode_active or not self._extra_sequence or not self._current_exam or not self._controller:
            return

        student_index, page_number = self._extra_sequence[self._extra_cursor]
        student = self._current_exam.students[student_index]

        default_areas = ",".join(self._existing_standard_areas()[:1] or ["A"])
        raw_areas = simpledialog.askstring(
            "Extraseite zuordnen",
            "Bestehende Bereich(e) fuer Extraseite eingeben (z. B. A,B)",
            initialvalue=default_areas,
        )
        if raw_areas is None:
            return
        area_codes = [item.strip().upper() for item in raw_areas.split(",") if item.strip()]

        if self._render_photo is None:
            return
        canvas_width = float(self._reading_canvas.winfo_width())
        canvas_height = float(self._reading_canvas.winfo_height())
        box = (
            0.0,
            0.0,
            canvas_width * self._x_factor,
            canvas_height * self._y_factor,
        )

        updated = self._controller.assign_extra_page_immediate(
            exam=self._current_exam,
            student_pdf=student.pdf_filename,
            page_number=page_number,
            box=box,
            area_codes=area_codes,
        )
        if updated is not None:
            self._current_exam = updated
            self._apply_detail_labels(updated)
            self._render_current_extra_page()

    def _toggle_extra_pages_popup_for_current(self) -> None:
        if self._extra_popup is not None and self._extra_popup.winfo_exists():
            self._close_extra_popup()
            self._status_var.set("Extraseitenansicht geschlossen")
            return
        self._open_extra_pages_popup_for_current(notify_if_missing=True)

    def _open_extra_pages_popup_for_current(self, *, notify_if_missing: bool) -> None:
        if not self._current_exam or not self._current_exam.students:
            return
        current_student_index = self._student_cursor
        student = self._current_exam.students[self._student_cursor]
        if not student.extra_pages:
            self._close_extra_popup()
            if notify_if_missing:
                messagebox.showinfo("Hinweis", "Für die aktuelle Person sind keine Extraseiten vorhanden.")
            return

        pdf_path = Path(self._current_exam.folder_path) / student.pdf_filename
        if not pdf_path.exists():
            messagebox.showerror("Fehler", f"Datei fehlt: {student.pdf_filename}")
            return

        if self._extra_popup is None or not self._extra_popup.winfo_exists():
            # Deliberate exception from the bw-gui default-scrollable popup
            # convention (`bw-gui/docs/SCROLLABILITY_CONTRACT.md`): a plain
            # `ui.Toplevel`, not `ScrollablePopupWindow`. This popup is a
            # single-image PDF-page viewer (fixed-size Canvas sized to the
            # rendered page, nav buttons below) - structurally the same
            # "self-contained canvas display, an outer scroll layer adds no
            # value" shape as Kursplaner's `kompetenzgraph_dialog.py`
            # (`scrollable=False`), not a growing list of fields/rows.
            popup = ui.Toplevel(self.root)
            popup.title(f"Extraseiten: {student.display_name}")
            popup.geometry("760x860")
            popup.transient(self.root)
            self._register_popup_window(popup)

            header = widgets.Frame(popup, padding=10)
            header.pack(fill=ui.X)
            self._extra_popup_info_var = ui.StringVar(value="")
            widgets.Label(header, textvariable=self._extra_popup_info_var, style="Muted.TLabel").pack(side=ui.LEFT)

            canvas_bg, canvas_border = self._canvas_theme_tokens()
            self._extra_popup_canvas = ui.Canvas(
                popup,
                bg=canvas_bg,
                highlightthickness=1,
                highlightbackground=canvas_border,
            )
            self._extra_popup_canvas.pack(fill=ui.BOTH, expand=True, padx=10, pady=(0, 10))

            nav = widgets.Frame(popup, padding=(10, 0, 10, 10))
            nav.pack(fill=ui.X)
            popup_prev_button = widgets.Button(
                nav,
                text="◀",
                style="SecondaryAction.TButton",
                command=lambda: self._change_extra_popup_page(-1),
            )
            popup_prev_button.pack(side=ui.LEFT)
            self._attach_hover_help(popup_prev_button, label="Vorherige Extraseite", shortcut="Links")

            popup_next_button = widgets.Button(
                nav,
                text="▶",
                style="SecondaryAction.TButton",
                command=lambda: self._change_extra_popup_page(1),
            )
            popup_next_button.pack(side=ui.LEFT, padx=(8, 0))
            self._attach_hover_help(popup_next_button, label="Naechste Extraseite", shortcut="Rechts")

            popup_close_button = widgets.Button(
                nav,
                text="Schließen",
                style="SecondaryAction.TButton",
                command=self._close_extra_popup,
            )
            popup_close_button.pack(side=ui.RIGHT)
            self._attach_hover_help(popup_close_button, label="Extraseiten-Popup schliessen", shortcut="Esc")

            popup.protocol("WM_DELETE_WINDOW", self._close_extra_popup)
            self._extra_popup = popup

        if self._extra_popup is not None:
            self._extra_popup.title(f"Extraseiten: {student.display_name}")
            self._extra_popup.deiconify()
            self._extra_popup.lift()

        if self._extra_popup_student_index != current_student_index:
            self._extra_popup_cursor = 0
        self._extra_popup_student_index = current_student_index
        self._render_extra_popup_page()

    def _change_extra_popup_page(self, delta: int) -> None:
        if not self._current_exam or self._extra_popup_student_index is None:
            return
        student = self._current_exam.students[self._extra_popup_student_index]
        if not student.extra_pages:
            return
        self._extra_popup_cursor = (self._extra_popup_cursor + delta) % len(student.extra_pages)
        self._render_extra_popup_page()

    def _render_extra_popup_page(self) -> None:
        if (
            not self._current_exam
            or self._extra_popup is None
            or not self._extra_popup.winfo_exists()
            or self._extra_popup_canvas is None
            or self._extra_popup_info_var is None
            or self._extra_popup_student_index is None
        ):
            return

        student = self._current_exam.students[self._extra_popup_student_index]
        if not student.extra_pages:
            return

        page_number = student.extra_pages[self._extra_popup_cursor]
        pdf_path = Path(self._current_exam.folder_path) / student.pdf_filename

        document = self._doc_cache.get(student.pdf_filename)
        if document is None:
            document = fitz.open(pdf_path)
            self._doc_cache[student.pdf_filename] = document

        page = document.load_page(page_number - 1)
        page_rect = page.rect
        scale = 700.0 / max(page_rect.width, 1.0)
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        try:
            self._popup_photo = ui.PhotoImage(data=pix.tobytes("ppm"), format="ppm")
            self._extra_popup_canvas.configure(width=pix.width, height=pix.height)
            self._extra_popup_canvas.delete("all")
            self._extra_popup_canvas.create_image(0, 0, anchor=ui.NW, image=self._popup_photo)
        except Exception as exc:
            self._extra_popup_canvas.delete("all")
            self._extra_popup_info_var.set(f"Fehler beim Popup-Rendering: {exc}")
            return

        areas = self._areas_for_extra_page(student.pdf_filename, page_number)
        area_text = ",".join(areas) if areas else "-"
        self._extra_popup_info_var.set(
            f"Extraseite {self._extra_popup_cursor + 1}/{len(student.extra_pages)} | Seite {page_number} | Bereich {area_text}"
        )

    def _close_extra_popup(self) -> None:
        if self._extra_popup is not None and self._extra_popup.winfo_exists():
            popup_id = str(self._extra_popup)
            self._popup_registry.close_popup(popup_id)
            self._tracked_popup_ids.discard(popup_id)
            self._extra_popup.destroy()
        self._extra_popup = None
        self._extra_popup_canvas = None
        self._extra_popup_info_var = None
        self._extra_popup_student_index = None
        self._extra_popup_cursor = 0
