from __future__ import annotations

from pathlib import Path

import fitz

from app.adapters.gui.dialog_services import messagebox
from app.adapters.gui.scan_workshop_session import PdfEditState
from app.core.domain.models import ExamProject
from app.core.domain.page_remap import PdfPagePlan, RemapResult, remap_exam
from app.infrastructure.pdf.page_editing import source_transform, write_edited_pdf
from app.infrastructure.pdf.pdf_replacement import (
    ScanWorkshopApplyError,
    apply_replacements,
    new_action_dir,
    redo_replacements,
    undo_replacements,
)
from app.infrastructure.pdf.pdf_sources import close_quietly


class UiIntentControllerScanWorkshopMixin:
    """Scan-Werkstatt "Änderungen übernehmen": one transaction over PDFs and exam data, fully undoable.

    Order (binding): plan the re-mapped exam in memory -> write every edited
    PDF to ``<Name>.korrektor.tmp.pdf`` (nothing existing touched yet) ->
    swap: original to ``.korrektor_originale/<aid>/roh/``, temp to the real
    name -> save the exam (atomic). Only when `save_exam` returns is the
    apply successful; any failure before rolls back PDFs and leaves the exam
    file untouched (`apply_replacements`). The history action swaps the
    files back and forth with hash checks and asks before each undo/redo.
    """

    def plan_scan_workshop_apply(self, *, exam: ExamProject, states: dict[str, PdfEditState]) -> RemapResult:
        """Re-map all page-bound data for the changed PDFs (pure; nothing is written)."""
        plans: dict[str, PdfPagePlan] = {}
        folder = Path(exam.folder_path)
        for pdf, state in states.items():
            source = fitz.open(folder / pdf)
            try:
                transforms = {page: source_transform(source, page, state.edit_for(page)) for page in range(1, state.page_count + 1)}
            finally:
                close_quietly(source)
            plans[pdf] = PdfPagePlan(mapping=state.page_mapping(), transforms=transforms, new_page_count=len(state.kept_order()))
        return remap_exam(exam, plans)

    def apply_scan_workshop_immediate(
        self, *, exam: ExamProject, states: dict[str, PdfEditState], remap: RemapResult
    ) -> ExamProject | None:
        """Write and swap in the edited PDFs, save the re-mapped exam, record the undo step."""
        folder = Path(exam.folder_path)
        temp_by_target: dict[Path, Path] = {}
        try:
            for pdf, state in states.items():
                target = folder / pdf
                temp = folder / f"{target.stem}.korrektor.tmp.pdf"
                write_edited_pdf(target, state.order, state.edits, temp)
                temp_by_target[target] = temp
        except Exception as exc:
            for temp in temp_by_target.values():
                temp.unlink(missing_ok=True)
            messagebox.showerror("Scan-Werkstatt", f"Die bearbeiteten PDFs konnten nicht erzeugt werden:\n{exc}\n\nEs wurde nichts verändert.")
            return None

        pdfs = list(states)
        self._app.invalidate_doc_cache(pdfs)
        repo = self._deps.exam_repository
        before_payload = exam.to_dict()
        saved: dict[str, Path] = {}
        action_dir = new_action_dir(folder)
        try:
            records = apply_replacements(action_dir, temp_by_target, after=lambda: saved.setdefault("file", repo.save_exam(remap.exam)))
        except ScanWorkshopApplyError as exc:
            rest = ("\n\nDiese Dateien bitte prüfen:\n" + "\n".join(str(path) for path in exc.leftover_files)) if exc.leftover_files else "\n\nEs wurde nichts verändert."
            messagebox.showerror("Scan-Werkstatt", f"Übernehmen fehlgeschlagen:\n{exc.cause}{rest}")
            return None

        exam_file = saved["file"]
        updated = repo.load_exam(exam_file)
        after_payload = updated.to_dict()

        def _undo() -> None:
            """Undo: close cached handles, swap originals back (hash-checked), write the payload from before the apply."""
            self._app.invalidate_doc_cache(pdfs)
            undo_replacements(records, after=lambda: repo.write_exam_payload(exam_file, before_payload))

        def _redo() -> None:
            """Redo: close cached handles, swap edited versions back in (hash-checked), write the payload from after the apply."""
            self._app.invalidate_doc_cache(pdfs)
            redo_replacements(records, after=lambda: repo.write_exam_payload(exam_file, after_payload))

        self._record_history_action(
            description=f"Scan-Werkstatt: {len(pdfs)} PDF(s) geändert",
            undo=_undo,
            redo=_redo,
            context="content",
            confirm_text=(
                f"Dabei werden die PDF-Dateien von {len(pdfs)} Person(en) getauscht "
                f"(Sicherungen in {action_dir.relative_to(folder)}). Fortfahren?"
            ),
        )
        self.refresh_exam_overview()
        self._app.set_status(f"Scan-Werkstatt: {len(pdfs)} PDF(s) geändert, Originale in {action_dir.relative_to(folder)}")
        return updated
