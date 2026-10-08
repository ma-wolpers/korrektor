from __future__ import annotations

from pathlib import Path

from app.adapters.gui.dialog_services import filedialog, messagebox
from app.adapters.gui.import_split_texts import fallback_warning_text, split_summary_text, write_error_text
from app.core.domain.pdf_split_naming import plan_split_files
from app.infrastructure.pdf.pdf_splitter import SplitWriteError, write_split_outputs
from app.infrastructure.repositories.json_exam_repository import EXAM_DATA_FILENAME


class MainWindowImportSplitExportMixin:
    """"Aufteilen…": plan, confirm, write and hand over the result of the PDF import wizard.

    Error contract (V5): every expected failure is reported with a message,
    the wizard stays open with unchanged splits and names, and the rollback
    of `write_split_outputs` guarantees that no partial result stays in the
    target folder (files it could not remove are listed). Only after a
    successful write does the session end; then the bound
    ``on_split_complete`` is called exactly once. If that callback fails, the
    session is already over - the message names the folder so the split
    files can still be opened later.
    """

    def _run_import_split(self) -> None:
        """Run the split for the current session (button "Aufteilen…")."""
        session = self._import_split_session
        view = self._import_split_view
        if session is None or view is None:
            return
        plan = plan_split_files(session.sections())
        if plan.needs_fallback_confirmation and not messagebox.askyesno(
            "Abschnitte ohne Namen", fallback_warning_text(plan), parent=view.popup
        ):
            self._jump_to_first_unnamed_import_split_section(plan)
            return

        output_dir = self._ask_import_split_output_dir(creates_exam=session.creates_exam)
        if output_dir is None:
            self._focus_import_split_name_field()
            return

        view.info_var.set("Aufteilen läuft…")
        view.popup.update_idletasks()
        try:
            created = write_split_outputs(session.document, plan.files, output_dir)
        except FileExistsError as exc:
            self._report_import_split_error("Aufteilen nicht möglich", str(exc))
            return
        except SplitWriteError as exc:
            self._report_import_split_error("Aufteilen fehlgeschlagen", write_error_text(exc.cause, exc.leftover_files))
            return
        except ValueError as exc:
            self._report_import_split_error("Aufteilen nicht möglich", f"Interner Fehler bei der Dateinamenplanung:\n{exc}")
            return
        except Exception as exc:
            self._report_import_split_error("Aufteilen fehlgeschlagen", str(exc))
            return

        callback = session.on_split_complete
        display_names = {planned.filename: planned.display_name for planned in plan.files}
        self._end_import_split_session()
        if callback is None:
            self.set_status(f"PDF aufgeteilt: {len(created)} Datei(en) in {output_dir}")
            messagebox.showinfo("Aufteilen abgeschlossen", split_summary_text(plan, output_dir, len(created)))
            return
        try:
            callback(output_dir, display_names)
        except Exception as exc:
            messagebox.showerror(
                "Klausur konnte nicht angelegt werden",
                f"{exc}\n\nDie aufgeteilten PDFs liegen in:\n{output_dir}\n\n"
                "Du kannst den Ordner später über 'Neue Klausur' → 'Ordner mit einzelnen Abgaben' öffnen.",
            )

    def _ask_import_split_output_dir(self, *, creates_exam: bool) -> Path | None:
        """Ask for the target folder; in the "Neue Klausur" flow it must not contain any PDF yet.

        Returns ``None`` when the user cancels or the folder is rejected (the
        rejection is reported; the wizard stays open).
        """
        view = self._import_split_view
        raw = filedialog.askdirectory(
            title="Zielordner für die aufgeteilten PDFs wählen", parent=view.popup if view is not None else None
        )
        if not raw:
            return None
        output_dir = Path(raw)
        if creates_exam and (output_dir / EXAM_DATA_FILENAME).exists():
            self._report_import_split_error(
                "Ordner enthält bereits eine Klausur",
                "In diesem Ordner liegen schon Klausurdaten (korrektor_klausur.json). "
                "Für eine neue Klausur bitte einen leeren Ordner wählen.",
            )
            return None
        if creates_exam and _folder_contains_pdfs(output_dir):
            self._report_import_split_error(
                "Ordner enthält bereits PDFs",
                "Für eine neue Klausur bitte einen leeren Ordner wählen (oder im Dialog neu anlegen):\n"
                "alle PDFs im Klausurordner würden sonst mit als Abgaben geladen.",
            )
            return None
        return output_dir

    def _report_import_split_error(self, title: str, message: str) -> None:
        """Show an error over the wizard and restore its header; the session stays unchanged."""
        view = self._import_split_view
        messagebox.showerror(title, message, parent=view.popup if view is not None else None)
        self._refresh_import_split_view()
        self._focus_import_split_name_field()

    def _jump_to_first_unnamed_import_split_section(self, plan) -> None:
        """After "Nein" on the fallback warning: show the first section without a valid name."""
        session = self._import_split_session
        starts = [section.start_page for section in (*plan.fallback_sections, *plan.invalid_name_sections)]
        if session is not None and starts and session.go_to_page(min(starts)):
            self._refresh_import_split_view(page_changed=True)
        self._focus_import_split_name_field()


def _folder_contains_pdfs(folder: Path) -> bool:
    """True if ``folder`` exists and already holds a ``.pdf`` file (any letter case)."""
    if not folder.is_dir():
        return False
    return any(child.is_file() and child.suffix.lower() == ".pdf" for child in folder.iterdir())
