from __future__ import annotations

from pathlib import Path

import fitz

from app.infrastructure.pdf.page_editing import render_edited_page, source_transform

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui

_CROSSHAIR_COLOR = "#e11d48"
_LOCKED_HINT = "gesperrt: Auswertungsseite zuerst entfernen (Auswertung → von der PDF entfernen)"


def parse_rotation_input(text: str) -> float | None:
    """Degree field input -> clockwise degrees: accepts "3,5", "3.5", "-2°", " 1 "; ``None`` if invalid."""
    cleaned = text.strip().replace("°", "").replace(",", ".").strip()
    if not cleaned:
        return 0.0
    try:
        return float(cleaned)
    except ValueError:
        return None


class MainWindowScanWorkshopViewMixin:
    """Scan-Werkstatt rendering and actions (keys arrive via the central shortcuts and the dispatcher).

    The preview is rendered by `render_edited_page` - the same function that
    writes the result - fitted into the canvas. The crosshair is two lines
    across the page at the session's fraction; it stays where it was clicked
    across pages and persons. Deleted pages stay visible, greyed out.
    """

    # --- rendering -------------------------------------------------------------------

    def _scan_document(self, pdf: str) -> fitz.Document:
        """Open (and cache in the shared doc cache) the current *on-disk* PDF; apply/undo invalidate this cache before swapping files."""
        document = self._doc_cache.get(pdf)
        if document is None:
            document = fitz.open(Path(self._current_exam.folder_path) / pdf)
            self._doc_cache[pdf] = document
        return document

    def _schedule_scan_render(self) -> None:
        """Debounced re-render (120 ms) for canvas resizes, so dragging the window edge does not render per pixel."""
        view = self._scan_view
        if view is None or self._scan_session is None:
            return
        if view.pending_render is not None:
            view.canvas.after_cancel(view.pending_render)
        view.pending_render = view.canvas.after(120, self._render_scan_workshop)

    def _render_scan_workshop(self) -> None:
        """Render the current page exactly as it will be written (same transform), fitted into the canvas, plus crosshair and deleted overlay."""
        session, view = self._scan_session, self._scan_view
        if session is None or view is None or self._current_exam is None:
            return
        view.pending_render = None
        pdf, page, edit = session.current_pdf, session.current_original_page, session.current_edit
        canvas = view.canvas
        canvas.delete("all")
        try:
            document = self._scan_document(pdf)
            width, height = source_transform(document, page, edit).target_size
            canvas_width = max(int(canvas.winfo_width()), 200)
            canvas_height = max(int(canvas.winfo_height()), 200)
            zoom = max(0.05, min((canvas_width - 16) / width, (canvas_height - 16) / height))
            pix = render_edited_page(document, page, edit, zoom)
        except Exception as exc:
            view.info_var.set(f"{session.display_names[pdf]}: Seite kann nicht dargestellt werden ({exc})")
            return
        view.photo = ui.PhotoImage(data=pix.tobytes("ppm"), format="ppm")
        left = (canvas_width - pix.width) / 2
        top = 8.0
        view.image_box = (left, top, float(pix.width), float(pix.height))
        canvas.create_image(left, top, anchor=ui.NW, image=view.photo)
        if edit.deleted:
            canvas.create_rectangle(left, top, left + pix.width, top + pix.height, fill="#808080", stipple="gray50", outline="")
            canvas.create_text(left + pix.width / 2, top + pix.height / 2, text="wird gelöscht", fill="#b91c1c", font=("TkDefaultFont", 20, "bold"))
        fraction_x, fraction_y = session.crosshair
        x, y = left + fraction_x * pix.width, top + fraction_y * pix.height
        canvas.create_line(left, y, left + pix.width, y, fill=_CROSSHAIR_COLOR, width=1)
        canvas.create_line(x, top, x, top + pix.height, fill=_CROSSHAIR_COLOR, width=1)
        self._refresh_scan_labels()

    def _refresh_scan_labels(self) -> None:
        """Update info line, pending counter, delete-button text, degree field (without re-triggering its flush) and the page list."""
        session, view = self._scan_session, self._scan_view
        state, edit = session.current_state, session.current_edit
        info = (
            f"{session.display_names[session.current_pdf]} ({session.student_index + 1}/{len(session.pdfs)}) · "
            f"Seite {session.position}/{len(state.order)} (Original {session.current_original_page}) · "
            f"Drehung {edit.rotation_deg:+.1f}°"
        )
        if edit.deleted:
            info += " · wird gelöscht"
        if session.is_current_locked():
            info += f" · {_LOCKED_HINT}"
        view.info_var.set(info)
        changed = session.changed_pdfs()
        view.pending_var.set(f"Offene Änderungen: {len(changed)} Person(en)" if changed else "Keine offenen Änderungen")
        view.delete_button.configure(text="Wiederherstellen" if edit.deleted else "Seite löschen")
        view.suppress_degree = True
        try:
            view.degree_var.set(f"{edit.rotation_deg:g}")
        finally:
            view.suppress_degree = False
        view.degree_hint_var.set("")
        tree = view.page_tree
        tree.delete(*tree.get_children())
        for position, original in enumerate(state.order, start=1):
            page_edit = state.edit_for(original)
            status = "gelöscht" if page_edit.deleted else ("gedreht" if page_edit.rotation_deg else "")
            iid = tree.insert("", ui.END, values=(position, original, f"{page_edit.rotation_deg:g}°", status))
            if position == session.position:
                tree.selection_set(iid)
                tree.see(iid)

    # --- actions (buttons, keys) -----------------------------------------------------

    def _scan_active(self) -> bool:
        """True while the Scan-Werkstatt view is shown with a session (guards key handlers shared with other views)."""
        return self._active_view == "scan_workshop" and self._scan_session is not None

    def _scan_after(self, changed: bool, locked_message: bool = False) -> None:
        """Re-render after a successful session change; on a refused edit of a locked person explain why in the status line."""
        if changed:
            self._render_scan_workshop()
        elif locked_message and self._scan_session.is_current_locked():
            self._status_var.set(f"Scan-Werkstatt: {_LOCKED_HINT}")

    def _scan_go_student(self, delta: int) -> None:
        """←/→ and buttons: previous/next person; page position is kept where possible."""
        if self._scan_active():
            self._scan_after(self._scan_session.go_student(delta))

    def _scan_go_page(self, delta: int) -> None:
        """↑/↓ and buttons: previous/next page position of the current person."""
        if self._scan_active():
            self._scan_after(self._scan_session.go_page(delta))

    def _scan_move_page(self, delta: int) -> None:
        """Strg+↑/↓ and buttons: move the current page one position up/down (pop/insert, it stays selected)."""
        if self._scan_active():
            self._scan_after(self._scan_session.move_page(delta), locked_message=True)

    def _scan_toggle_delete(self) -> None:
        """Entf and button: mark the current page as deleted, or restore it."""
        if self._scan_active():
            self._scan_after(self._scan_session.toggle_delete(), locked_message=True)

    def _scan_rotate_key(self, direction: int):
        """Strg+←/→ and the ↺/↻ buttons: rotate by the configured step; ``"break"`` only when handled."""
        if not self._scan_active():
            return None
        self._scan_after(self._scan_session.rotate_by(direction * self._scan_rotation_step_deg), locked_message=True)
        return "break"

    def _scan_rotate_quarter_key(self, direction: int):
        """Strg+Shift+←/→ and the 90° buttons: quarter turn; ``"break"`` only when handled."""
        if not self._scan_active():
            return None
        self._scan_after(self._scan_session.rotate_quarter(direction), locked_message=True)
        return "break"

    def _on_scan_canvas_click(self, event) -> None:
        """Click on the page: move the crosshair there (it stays for all pages and persons)."""
        view, session = self._scan_view, self._scan_session
        if session is None:
            return
        left, top, width, height = view.image_box
        if left <= event.x <= left + width and top <= event.y <= top + height:
            session.set_crosshair((event.x - left) / width, (event.y - top) / height)
            self._render_scan_workshop()

    def _on_scan_page_selected(self, _event=None) -> None:
        """Selecting a row in the page list jumps to that position (ignored while the list is rebuilt for the same position)."""
        session, view = self._scan_session, self._scan_view
        if session is None:
            return
        selection = view.page_tree.selection()
        if not selection:
            return
        position = view.page_tree.index(selection[0]) + 1
        if position != session.position:
            session.position = position
            self._render_scan_workshop()

    def _on_scan_degree_typed(self, _event=None) -> None:
        """Typing in the degree field flushes 600 ms after the last key (no live render per keystroke)."""
        view = self._scan_view
        if view is None or view.suppress_degree:
            return
        if view.degree_flush is not None:
            view.degree_entry.after_cancel(view.degree_flush)
        view.degree_flush = view.degree_entry.after(600, self._flush_scan_degree)

    def _flush_scan_degree(self) -> None:
        """Apply the typed degree value (after the delay, on Enter or focus-out); invalid input only shows a hint."""
        view, session = self._scan_view, self._scan_session
        if view is None or session is None:
            return
        if view.degree_flush is not None:
            view.degree_entry.after_cancel(view.degree_flush)
            view.degree_flush = None
        value = parse_rotation_input(view.degree_var.get())
        if value is None:
            view.degree_hint_var.set("Ungültige Gradzahl")
            return
        if abs(value - session.current_edit.rotation_deg) > 1e-9:
            self._scan_after(session.set_rotation(value), locked_message=True)
