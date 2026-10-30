from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import fitz

from app.adapters.gui.dialog_services import messagebox
from app.core.domain.models import ExamProject, StudentExam
from app.infrastructure.pdf.pdf_document_writer import (
    drop_trailing_page,
    flatten_annotations,
    read_trailing_page_marker,
    stamp_marked_stats_page,
    write_pdf_copy_atomically,
)
from app.infrastructure.repositories.file_utils import render_filename_template, sanitize_filename_stem
from app.infrastructure.rendering.competency_chart_renderer import figure_to_pdf_bytes
from app.infrastructure.rendering.student_result_report_renderer import render_student_result_report


@dataclass(slots=True)
class _BatchExportTarget:
    """One resolved, still-unwritten export destination for a single student."""

    student: StudentExam
    source_path: Path
    destination_path: Path


class UiIntentControllerBatchExportMixin:
    """Zentraler Exportmodus: alle ausgewaehlten Schueler:innen-PDFs in einem Rutsch exportieren.

    Rein lesend gegenueber Exam und Arbeits-PDFs (kein Exam-Mutator, keine
    `HistoryAction` - Muster `export_student_results`): die Klausur-JSON
    und jede Arbeits-PDF (`exam.folder_path / student.pdf_filename`)
    bleiben unangetastet, es entstehen ausschliesslich neue Dateien unter
    dem gewaehlten Zielordner. Quelle ist immer der zuletzt gespeicherte
    Stand der Arbeits-PDF - kein automatisches "Alle PDFs ueberschreiben".

    Jede Kopie wird zum Schluss geflattet (`flatten_annotations`):
    Markierungen und sonstige Kommentare sind dort fester Seiteninhalt und
    sehen in jedem PDF-Programm gleich aus. Die Arbeits-PDF behaelt ihre
    Annotationen, damit "Alle PDFs ueberschreiben" sie ersetzen kann.

    Ablauf in zwei Phasen: zuerst ein vollstaendiger, alles-oder-nichts-
    Preflight ueber die **gesamte** Auswahl (unbekannte Person, fehlende
    Arbeits-PDF, nicht sanitisierbarer Ordner-/Dateiname, Ziel ist eine
    Arbeits-PDF der Klausur, Ziel-Kollision mit einer bereits
    existierenden Datei, Ziel-Kollision zweier Personen
    innerhalb derselben Auswahl) - schlaegt irgendeine Pruefung fehl, wird
    **nichts** geschrieben und die Methode gibt `None` zurueck (Diagnose
    bereits per `messagebox` gezeigt). Erst danach beginnt das eigentliche
    Schreiben; ab hier ist ein Fehlschlag bei einer einzelnen Person kein
    Grund, die uebrigen nicht zu exportieren (`(exported, failed)`,
    Rueckgabekonvention von `export_student_results`).

    Leere `sections` sind erlaubt: Dann wird keine Statistikseite
    angehaengt, eine vorhandene (per Markierung bestaetigte) faellt in der
    Kopie weg, und die Auswertung wird gar nicht erst berechnet - der
    Export dient dann nur dem Kopieren und Umbenennen. Die Konsistenzpruefung
    Markierung vs. `stats_report_appended` gilt trotzdem, weil sie
    entscheidet, ob die letzte Seite geloescht werden darf.
    """

    def export_students_batch(
        self,
        *,
        exam: ExamProject,
        student_ids: Sequence[str],
        scores: dict[str, dict[str, float]],
        sections: frozenset[str],
        chart_type: str,
        chart_scope: str,
        output_dir: Path,
        per_student_folders: bool,
        filename_template: str,
    ) -> tuple[list[str], list[str]] | None:
        target_ids = list(dict.fromkeys(student_ids))
        if not target_ids:
            messagebox.showerror("Ungültige Eingabe", "Keine Personen ausgewählt.")
            return None

        targets = self._resolve_batch_export_targets_or_none(
            exam=exam,
            target_ids=target_ids,
            output_dir=output_dir,
            per_student_folders=per_student_folders,
            filename_template=filename_template,
        )
        if targets is None:
            return None
        collision_diagnostic = self._check_batch_export_spares_working_pdfs_or_none(
            exam, targets
        ) or self._check_batch_export_collisions_or_none(targets)
        if collision_diagnostic is not None:
            messagebox.showerror("Export nicht möglich", collision_diagnostic)
            return None

        exported: list[str] = []
        failed: list[str] = []
        for target in targets:
            has_existing_marker = read_trailing_page_marker(target.source_path) is not None
            if target.student.stats_report_appended and not has_existing_marker:
                failed.append(
                    f"{target.student.display_name}: laut Klausurdaten ist eine Statistikseite angehängt, "
                    "die letzte PDF-Seite trägt aber keine Korrektor-Markierung - die Datei wurde vermutlich "
                    "extern verändert."
                )
                continue
            if not target.student.stats_report_appended and has_existing_marker:
                failed.append(
                    f"{target.student.display_name}: die letzte PDF-Seite trägt bereits eine Korrektor-"
                    "Statistikseiten-Markierung, laut Klausurdaten ist aber keine angehängt - widersprüchlicher Zustand."
                )
                continue

            prepare: Callable[[fitz.Document], None] | None
            if sections:
                result = self.compute_student_result_for_exam(
                    exam=exam, student_id=target.student.student_id, scores=scores
                )
                if result is None:
                    failed.append(f"{target.student.display_name}: Auswertung nicht verfügbar.")
                    continue
                report_bytes = figure_to_pdf_bytes(
                    render_student_result_report(result, chart_type=chart_type, chart_scope=chart_scope, sections=sections)
                )

                def _stamp(
                    document: fitz.Document, _page_bytes: bytes = report_bytes, _replace: bool = has_existing_marker
                ) -> None:
                    stamp_marked_stats_page(document, _page_bytes, replace_existing=_replace)

                prepare = _stamp
            else:
                # Ohne Baustein: nur kopieren/umbenennen, eine vorhandene Statistikseite faellt weg.
                prepare = drop_trailing_page if has_existing_marker else None

            def mutate(
                document: fitz.Document, _prepare: Callable[[fitz.Document], None] | None = prepare
            ) -> None:
                if _prepare is not None:
                    _prepare(document)
                flatten_annotations(document)

            try:
                write_pdf_copy_atomically(target.source_path, target.destination_path, mutate=mutate)
            except Exception as exc:
                failed.append(f"{target.student.display_name}: {exc}")
                continue
            exported.append(target.student.display_name)

        return exported, failed

    @staticmethod
    def _resolve_batch_export_targets_or_none(
        *,
        exam: ExamProject,
        target_ids: list[str],
        output_dir: Path,
        per_student_folders: bool,
        filename_template: str,
    ) -> list[_BatchExportTarget] | None:
        """Resolve every selected id to a concrete, still-unwritten destination path, or reject the whole batch.

        `index` (fed into `render_filename_template`'s `{Nr}`) is the
        person's stable position in `exam.students` - built once from the
        full roster, not from `target_ids` - so the same person keeps the
        same number regardless of which subset is currently selected for
        export.
        """
        students_by_id = {student.student_id: student for student in exam.students}
        index_by_student_id = {student.student_id: position for position, student in enumerate(exam.students, start=1)}

        targets: list[_BatchExportTarget] = []
        for student_id in target_ids:
            student = students_by_id.get(student_id)
            if student is None:
                messagebox.showerror("Export nicht möglich", f"Unbekannte Person-ID: {student_id}")
                return None

            source_path = Path(exam.folder_path) / student.pdf_filename
            if not source_path.exists():
                messagebox.showerror("Export nicht möglich", f"Datei fehlt: {student.pdf_filename}")
                return None

            destination_dir = output_dir
            if per_student_folders:
                folder_name = sanitize_filename_stem(student.display_name, replace_spaces_with=None)
                if folder_name is None:
                    messagebox.showerror(
                        "Export nicht möglich", f"{student.display_name}: kein gültiger Ordnername ableitbar."
                    )
                    return None
                destination_dir = output_dir / folder_name

            stem = render_filename_template(
                filename_template,
                display_name=student.display_name,
                school_class=exam.school_class,
                subject=exam.subject,
                index=index_by_student_id[student.student_id],
            )
            if stem is None:
                messagebox.showerror(
                    "Export nicht möglich", f"{student.display_name}: kein gültiger Dateiname aus dem Namensschema ableitbar."
                )
                return None

            targets.append(
                _BatchExportTarget(student=student, source_path=source_path, destination_path=destination_dir / f"{stem}.pdf")
            )
        return targets

    @staticmethod
    def _check_batch_export_spares_working_pdfs_or_none(
        exam: ExamProject, targets: list[_BatchExportTarget]
    ) -> str | None:
        """Return a diagnostic if a destination is any working PDF of this exam, else `None`.

        Covers the whole roster, not only the selected people. `samefile`
        compares the files themselves, so differing upper/lower case, a
        mapped drive or a link cannot hide a match. A destination that does
        not exist yet cannot be a working PDF.
        """
        working_pdfs = [Path(exam.folder_path) / student.pdf_filename for student in exam.students]
        existing_pdfs = [path for path in working_pdfs if path.exists()]
        hits = [
            str(target.destination_path)
            for target in targets
            if target.destination_path.exists()
            and any(os.path.samefile(target.destination_path, path) for path in existing_pdfs)
        ]
        if hits:
            return "Der Export darf keine Klausur-PDF überschreiben: " + ", ".join(hits)
        return None

    @staticmethod
    def _check_batch_export_collisions_or_none(targets: list[_BatchExportTarget]) -> str | None:
        """Return a diagnostic naming every colliding path, or `None` if the whole batch's targets are unique and free.

        Checked in full before any file is written: a collision with an
        already-existing file, and a collision between two people within
        this same selection (e.g. an under-specified naming template
        without a distinguishing `{Nr}`), both abort the entire export -
        never a silent "later overwrites earlier" ordering.
        """
        existing = [str(target.destination_path) for target in targets if target.destination_path.exists()]
        if existing:
            return "Diese Datei(en) existieren bereits im Zielordner: " + ", ".join(existing)

        seen: dict[Path, str] = {}
        duplicates: list[str] = []
        for target in targets:
            previous_owner = seen.get(target.destination_path)
            if previous_owner is not None:
                duplicates.append(
                    f"{target.destination_path} ({previous_owner} und {target.student.display_name})"
                )
            else:
                seen[target.destination_path] = target.student.display_name
        if duplicates:
            return "Namensschema ergibt für mehrere Personen denselben Dateinamen: " + ", ".join(duplicates)
        return None
