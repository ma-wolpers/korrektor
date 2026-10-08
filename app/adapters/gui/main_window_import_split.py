from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from app.adapters.gui.dialog_services import filedialog, messagebox
from app.adapters.gui.import_split_ordering import natural_sort_paths
from app.adapters.gui.import_split_session import ImportSplitSession, SplitCompleteCallback
from app.adapters.gui.import_split_texts import ALREADY_RUNNING_TEXT, source_problems_text
from app.infrastructure.pdf.pdf_merger import PdfImportError, open_merged_pdf
from app.infrastructure.pdf.pdf_sources import inspect_pdf_sources


class MainWindowImportSplitMixin:
    """Lifecycle of the PDF import wizard (Korrektor-Wunschliste "Dateien").

    One import at a time: either ``_import_split_pending`` (order dialog for
    several PDFs, `MainWindowImportSplitOrderMixin`) or
    ``_import_split_session`` (the wizard itself, state in
    `ImportSplitSession`, widgets in ``_import_split_view``). This mixin
    owns starting and ending; layout/refresh, input and export live in the
    sibling mixins ``..._view``, ``..._input`` and ``..._export``.

    Ownership contract: the merged ``fitz.Document`` belongs to the session
    from the moment `open_merged_pdf` returns; `_end_import_split_session`
    is the only place that ends a session (closes the document, unregisters
    and destroys the popup) and is idempotent. The popup's ``<Destroy>``
    handler calls it too, so app shutdown or an external ``destroy()`` can
    never leave a dangling session.
    """

    def open_import_split_wizard(self, *, on_split_complete: SplitCompleteCallback | None = None) -> bool:
        """Start a PDF import; return True if an import is now running (order dialog or wizard).

        A second call while an import runs is rejected - regardless of its
        callback - the running window is brought to the front, the new
        callback is never stored, and ``False`` is returned. Stale state
        whose window no longer exists is cleaned up first, so a crashed or
        externally closed import never blocks the next one.

        Args:
            on_split_complete: Bound to the new session; called exactly once
                with ``(output_dir, {filename: display_name})`` after a
                successful split ("Neue Klausur" flow). ``None`` for the
                standalone wizard from the "Datei" menu.
        """
        self._heal_stale_import_split_state()
        if self._import_split_pending is not None or self._import_split_session is not None:
            self._focus_running_import_split()
            messagebox.showinfo("PDF-Import läuft", ALREADY_RUNNING_TEXT, parent=self._running_import_split_window())
            return False

        selected = filedialog.askopenfilenames(
            title="PDF(s) mit allen Abgaben wählen", filetypes=[("PDF-Dateien", "*.pdf")]
        )
        if not selected:
            return False
        paths = natural_sort_paths(Path(raw) for raw in selected)
        infos, problems = inspect_pdf_sources(paths)
        if problems:
            messagebox.showerror("PDF-Import nicht möglich", source_problems_text(problems))
            return False
        if len(infos) > 1:
            return self._open_import_split_order_popup(infos, on_split_complete)
        return self._start_import_split_session([infos[0].path], on_split_complete)

    def _start_import_split_session(
        self, paths: Sequence[Path], on_split_complete: SplitCompleteCallback | None
    ) -> bool:
        """Merge ``paths`` (in this order), create the session and open the wizard window.

        Merging blocks the UI on purpose (expected size up to ~800 pages, see
        docs/ARCHITEKTUR.md); a status text is shown first. Any failure is
        reported and leaves no session and no open document behind.
        """
        self.set_status("PDF wird geladen…" if len(paths) == 1 else f"{len(paths)} PDFs werden zusammengeführt…")
        self.update_idletasks()
        try:
            document, spans = open_merged_pdf(paths)
        except PdfImportError as exc:
            messagebox.showerror("Zusammenführen fehlgeschlagen", f"{exc.path.name}: {exc.reason}")
            self.set_status("PDF-Import abgebrochen")
            return False
        except Exception as exc:
            messagebox.showerror("Zusammenführen fehlgeschlagen", str(exc))
            self.set_status("PDF-Import abgebrochen")
            return False

        self._import_split_session = ImportSplitSession(document, spans, on_split_complete)
        try:
            self._build_import_split_view(self._import_split_session)
            self._refresh_import_split_view(page_changed=True)
        except Exception as exc:
            self._end_import_split_session()
            messagebox.showerror("PDF-Import konnte nicht geöffnet werden", str(exc))
            self.set_status("PDF-Import abgebrochen")
            return False
        self.set_status("PDF-Import: Abgaben markieren und benennen")
        return True

    def _end_import_split_session(self) -> None:
        """End the running session: close its document, unregister and destroy its window. Idempotent."""
        session = self._import_split_session
        view = self._import_split_view
        self._import_split_session = None
        self._import_split_view = None
        if session is not None:
            session.close()
        if view is not None:
            self._destroy_import_split_window(view.popup)

    def _request_close_import_split(self) -> None:
        """Close button / window manager close: confirm if work would be lost, then end the session."""
        session = self._import_split_session
        view = self._import_split_view
        if session is None or view is None:
            self._end_import_split_session()
            return
        if session.has_user_input() and not messagebox.askyesno(
            "PDF-Import schließen",
            "Gesetzte Aufteilungen und Namen gehen verloren. Wirklich schließen?",
            parent=view.popup,
        ):
            self._focus_import_split_name_field()
            return
        creates_exam = session.creates_exam
        self._end_import_split_session()
        self.set_status("Neue Klausur abgebrochen – es wurde nichts angelegt." if creates_exam else "PDF-Import geschlossen")

    def _on_import_split_popup_destroyed(self, event) -> None:
        """``<Destroy>`` on the wizard toplevel: end the session if it was destroyed from outside.

        The toplevel's bindtag is part of every child's bindtags, so this
        fires for each destroyed child as well - only the toplevel itself counts.
        """
        view = self._import_split_view
        if view is None or event.widget is not view.popup:
            return
        self._end_import_split_session()

    def _destroy_import_split_window(self, window) -> None:
        """Unregister ``window`` from the popup registry and destroy it if it still exists."""
        if window is None:
            return
        popup_id = str(window)
        self._popup_registry.close_popup(popup_id)
        self._tracked_popup_ids.discard(popup_id)
        try:
            if int(window.winfo_exists()):
                window.destroy()
        except Exception:
            pass

    def _heal_stale_import_split_state(self) -> None:
        """End a pending phase or session whose window no longer exists (defence in depth)."""
        pending = self._import_split_pending
        if pending is not None and not self._import_split_window_alive(pending.popup):
            self._end_import_split_pending()
        view = self._import_split_view
        if self._import_split_session is not None and (view is None or not self._import_split_window_alive(view.popup)):
            self._end_import_split_session()

    @staticmethod
    def _import_split_window_alive(window) -> bool:
        if window is None:
            return False
        try:
            return bool(int(window.winfo_exists()))
        except Exception:
            return False

    def _running_import_split_window(self):
        """Return the toplevel of the running import (order dialog or wizard), if any."""
        if self._import_split_pending is not None:
            return self._import_split_pending.popup
        if self._import_split_view is not None:
            return self._import_split_view.popup
        return None

    def _focus_running_import_split(self) -> None:
        window = self._running_import_split_window()
        if window is None:
            return
        try:
            window.deiconify()
            window.lift()
            window.focus_force()
        except Exception:
            pass
