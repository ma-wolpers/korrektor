from __future__ import annotations

from pathlib import Path

import fitz

from app.adapters.gui.dialog_services import messagebox
from app.core.domain.page_coverage import single_pages_with_regions

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui, widgets
from bw_gui.theming import theme_canvas
from bw_gui.widgets import ScrollableImagePreview


class MainWindowExtraPagesPopupMixin:
    """"Einzelseiten ansehen": popup with the current person's pages that carry an Einzelseiten-Bereich.

    Read-only, whole page (`page_coverage.single_pages_with_regions`); the
    header names the regions and their tasks on that page.
    """

    def _gradable_extra_pages(self, student) -> list[int]:
        """Pages of ``student`` with an Einzelseiten-Bereich (1-based, within the student's PDF)."""
        if self._current_exam is None:
            return []
        return single_pages_with_regions(self._current_exam, student.pdf_filename)

    def _toggle_extra_pages_popup_for_current(self) -> None:
        if self._extra_popup is not None and self._extra_popup.winfo_exists():
            self._close_extra_popup()
            self._status_var.set("Einzelseitenansicht geschlossen")
            return
        self._open_extra_pages_popup_for_current(notify_if_missing=True)

    def _open_extra_pages_popup_for_current(self, *, notify_if_missing: bool) -> None:
        if not self._current_exam or not self._current_exam.students:
            return
        current_student_index = self._student_cursor
        student = self._current_exam.students[self._student_cursor]
        if not self._gradable_extra_pages(student):
            self._close_extra_popup()
            if notify_if_missing:
                messagebox.showinfo("Hinweis", "Für die aktuelle Person gibt es keine Einzelseiten mit Bereichen.")
            return

        pdf_path = Path(self._current_exam.folder_path) / student.pdf_filename
        if not pdf_path.exists():
            messagebox.showerror("Fehler", f"Datei fehlt: {student.pdf_filename}")
            return

        if self._extra_popup is None or not self._extra_popup.winfo_exists():
            # A plain `ui.Toplevel`, not `ScrollablePopupWindow`: only the page
            # preview needs to scroll, which bw-gui's `ScrollableImagePreview`
            # does (see bw-gui `docs/SCROLLABILITY_CONTRACT.md`). The navigation
            # bar is packed *before* the preview (side=BOTTOM) so it always
            # stays visible - a canvas sized to an A4 page used to push it out
            # of the window. Shrinking the window only shrinks the preview.
            popup = ui.Toplevel(self.root)
            popup.title(f"Einzelseiten: {student.display_name}")
            popup.geometry("760x860")
            popup.minsize(420, 320)
            popup.transient(self.root)
            self._register_popup_window(popup)

            header = widgets.Frame(popup, padding=10)
            header.pack(side=ui.TOP, fill=ui.X)
            self._extra_popup_info_var = ui.StringVar(value="")
            widgets.Label(header, textvariable=self._extra_popup_info_var, style="Muted.TLabel").pack(side=ui.LEFT)

            nav = widgets.Frame(popup, padding=(10, 0, 10, 10))
            nav.pack(side=ui.BOTTOM, fill=ui.X)
            popup_prev_button = widgets.Button(
                nav,
                text="◀",
                style="SecondaryAction.TButton",
                command=lambda: self._change_extra_popup_page(-1),
            )
            popup_prev_button.pack(side=ui.LEFT)
            self._attach_hover_help(popup_prev_button, label="Vorherige Einzelseite", shortcut="Links")

            popup_next_button = widgets.Button(
                nav,
                text="▶",
                style="SecondaryAction.TButton",
                command=lambda: self._change_extra_popup_page(1),
            )
            popup_next_button.pack(side=ui.LEFT, padx=(8, 0))
            self._attach_hover_help(popup_next_button, label="Nächste Einzelseite", shortcut="Rechts")

            popup_close_button = widgets.Button(
                nav,
                text="Schließen",
                style="SecondaryAction.TButton",
                command=self._close_extra_popup,
            )
            popup_close_button.pack(side=ui.RIGHT)
            self._attach_hover_help(popup_close_button, label="Einzelseiten-Ansicht schließen", shortcut="Esc")

            self._extra_popup_preview = ScrollableImagePreview(popup, render=self._render_extra_popup_image)
            self._extra_popup_preview.pack(side=ui.TOP, fill=ui.BOTH, expand=True, padx=10, pady=(0, 10))
            theme_canvas(self._extra_popup_preview.canvas, self._tooltip_theme_key)

            popup.protocol("WM_DELETE_WINDOW", self._close_extra_popup)
            self._extra_popup = popup

        if self._extra_popup is not None:
            self._extra_popup.title(f"Einzelseiten: {student.display_name}")
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
        if not self._gradable_extra_pages(student):
            return
        self._extra_popup_cursor = (self._extra_popup_cursor + delta) % len(self._gradable_extra_pages(student))
        self._render_extra_popup_page()

    def _render_extra_popup_page(self) -> None:
        """Show the current extra page: update the header and re-render the preview from the top."""
        if (
            not self._current_exam
            or self._extra_popup is None
            or not self._extra_popup.winfo_exists()
            or self._extra_popup_preview is None
            or self._extra_popup_info_var is None
            or self._extra_popup_student_index is None
        ):
            return

        student = self._current_exam.students[self._extra_popup_student_index]
        if not self._gradable_extra_pages(student):
            return

        page_number = self._gradable_extra_pages(student)[self._extra_popup_cursor]
        regions = [
            region for region in self._current_exam.regions if region.student_pdf == student.pdf_filename and region.page_number == page_number
        ]
        area_text = "; ".join(
            f"{region.assigned_area_codes[0] if region.assigned_area_codes else '-'}: {', '.join(region.task_codes)}" for region in regions
        ) or "-"
        self._extra_popup_info_var.set(
            f"Einzelseite {self._extra_popup_cursor + 1}/{len(self._gradable_extra_pages(student))} | Seite {page_number} | Bereiche {area_text}"
        )
        self._extra_popup_preview.refresh(scroll_to_top=True)

    def _render_extra_popup_image(self, width: int):
        """`ScrollableImagePreview` render callback: the current extra page scaled to ``width`` pixels.

        Rendering errors are shown in the header (as before the preview
        existed) instead of escaping into Tk; the preview then stays empty.
        """
        if not self._current_exam or self._extra_popup_student_index is None:
            return None
        student = self._current_exam.students[self._extra_popup_student_index]
        if not self._gradable_extra_pages(student):
            return None
        page_number = self._gradable_extra_pages(student)[self._extra_popup_cursor]
        try:
            document = self._doc_cache.get(student.pdf_filename)
            if document is None:
                document = fitz.open(Path(self._current_exam.folder_path) / student.pdf_filename)
                self._doc_cache[student.pdf_filename] = document
            page = document.load_page(page_number - 1)
            scale = width / max(page.rect.width, 1.0)
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            return ui.PhotoImage(data=pix.tobytes("ppm"), format="ppm")
        except Exception as exc:
            if self._extra_popup_info_var is not None:
                self._extra_popup_info_var.set(f"Fehler beim Popup-Rendering: {exc}")
            return None

    def _close_extra_popup(self) -> None:
        if self._extra_popup is not None and self._extra_popup.winfo_exists():
            popup_id = str(self._extra_popup)
            self._popup_registry.close_popup(popup_id)
            self._tracked_popup_ids.discard(popup_id)
            self._extra_popup.destroy()
        self._extra_popup = None
        self._extra_popup_preview = None
        self._extra_popup_info_var = None
        self._extra_popup_student_index = None
        self._extra_popup_cursor = 0
