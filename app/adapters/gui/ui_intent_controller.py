from __future__ import annotations

import csv
from pathlib import Path
from typing import TYPE_CHECKING, Sequence
from uuid import uuid4

from bw_libs.app_paths import atomic_write_text
from app.adapters.bootstrap.wiring import GuiDependencies
from app.adapters.gui.dialog_services import filedialog, messagebox, simpledialog
from app.adapters.gui.ui_intent_controller_supersymbol import UiIntentControllerSupersymbolMixin
from app.adapters.gui.view_models import ExamOverviewRow
from app.adapters.undo import HistoryAction
from app.core.domain.models import (
    ExamProject,
    ExtraPageAssignment,
    PersonAreaCompletion,
    RegionAssignment,
    RegionBox,
    TaskDefinition,
)
from app.core.domain.rename_planning import find_external_conflicts, plan_target_filenames, validate_rename_set
from app.infrastructure.repositories.file_utils import atomic_write_json

if TYPE_CHECKING:
    from app.adapters.gui.main_window import MainWindow


class UiIntentController(UiIntentControllerSupersymbolMixin):
    def __init__(self, app: "MainWindow", deps: GuiDependencies) -> None:
        self._app = app
        self._deps = deps

    def can_undo(self) -> bool:
        return self._deps.undo_history.can_undo()

    def can_redo(self) -> bool:
        return self._deps.undo_history.can_redo()

    def undo_label(self) -> str | None:
        return self._deps.undo_history.peek_undo()

    def redo_label(self) -> str | None:
        return self._deps.undo_history.peek_redo()

    def undo(self) -> bool:
        description = self._deps.undo_history.undo()
        if description is None:
            self._app.set_status("Nichts zum Rueckgaengigmachen")
            return False
        self._refresh_after_history_action()
        self._app.set_status(f"Rueckgaengig: {description}")
        return True

    def redo(self) -> bool:
        description = self._deps.undo_history.redo()
        if description is None:
            self._app.set_status("Nichts zum Wiederholen")
            return False
        self._refresh_after_history_action()
        self._app.set_status(f"Wiederholt: {description}")
        return True

    def _refresh_after_history_action(self) -> None:
        self.refresh_exam_overview()
        self._app.sync_current_exam_from_repository()

    def _record_history_action(self, *, description: str, undo, redo) -> None:
        self._deps.undo_history.push(
            HistoryAction(
                description=description,
                undo=undo,
                redo=redo,
            )
        )

    @staticmethod
    def _read_text_or_none(path: Path) -> str | None:
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    @staticmethod
    def _restore_text(path: Path, content: str | None) -> None:
        if content is None:
            if path.exists():
                path.unlink()
            return
        atomic_write_text(path, content, encoding="utf-8")

    @staticmethod
    def _write_exam_payload(exam_file: Path, payload: dict[str, object]) -> None:
        exam_file.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(exam_file, payload)

    def _record_exam_payload_action(
        self,
        *,
        description: str,
        exam_id: str,
        before_payload: dict[str, object],
        after_payload: dict[str, object],
    ) -> None:
        """Push one undo/redo entry that replays the given exam JSON snapshots.

        `before_payload`/`after_payload` must already be independent snapshots
        (e.g. a fresh `ExamProject.to_dict()` call) — `to_dict()` recursively
        builds new dicts/lists of primitive values with no references back to
        the live exam object, so callers must not deep-copy them again before
        passing them in here.
        """
        exam_file = self._deps.exam_repository.index_root / f"{exam_id}.json"

        self._record_history_action(
            description=description,
            undo=lambda: self._write_exam_payload(exam_file, before_payload),
            redo=lambda: self._write_exam_payload(exam_file, after_payload),
        )

    def _apply_exam_index_dir(self, target: Path) -> None:
        self._deps.settings_repository.save_exam_index_dir(target)
        self._deps.exam_repository.set_index_root(target)
        self._app.on_exam_index_dir_changed(target)
        self.refresh_exam_overview()

    def refresh_exam_overview(self) -> None:
        """Rebuild the exam overview list from a single load pass.

        `ListExamsUseCase.execute()` already loads and parses every exam file
        once; it must not be followed by a second directory-wide reload just
        to look up `exam_id`/`exam_name`/the source path, since `exam_file`
        is already carried on each `ExamOverview` result. A file that fails
        to load is skipped (not shown) rather than aborting the whole
        overview; if any did, a short status hint names how many and the
        first one, instead of a popup on every refresh.
        """
        overviews, load_errors = self._deps.list_exams_usecase.execute()
        rows = [
            ExamOverviewRow(
                exam_id=item.exam_id,
                exam_name=item.exam_name,
                reading_percent=item.reading_percent,
                correction_percent=item.correction_percent,
                region_count=item.region_count,
                corrected_region_count=item.corrected_region_count,
                reading_complete=item.reading_complete,
                has_open_flags=item.has_unassigned_extra_pages or item.has_missing_page_markings,
                source_file=item.exam_file,
            )
            for item in overviews
        ]
        self._app.render_overview_rows(rows)
        if load_errors:
            first = load_errors[0]
            suffix = f" ({len(load_errors) - 1} weitere)" if len(load_errors) > 1 else ""
            self._app.set_status(
                f"{len(load_errors)} Klausur(en) uebersprungen - fehlerhaft: {first.exam_file.name}: {first.message}{suffix}"
            )

    def create_exam(self) -> None:
        folder = filedialog.askdirectory(title="Klausurordner wählen")
        if not folder:
            return

        suggested = Path(folder).name
        exam_name = simpledialog.askstring("Neue Klausur", "Name der Klausur:", initialvalue=suggested)
        if exam_name is None:
            return

        try:
            result = self._deps.create_exam_usecase.execute(folder_path=Path(folder), exam_name=exam_name)
        except Exception as exc:  # pragma: no cover - UI messaging
            messagebox.showerror("Fehler", str(exc))
            return

        payload = result.exam.to_dict()
        exam_file = result.exam_file
        self._record_history_action(
            description=f"Klausur angelegt: {result.exam.exam_name}",
            undo=lambda: exam_file.exists() and exam_file.unlink(),
            redo=lambda: self._write_exam_payload(exam_file, payload),
        )

        self.refresh_exam_overview()
        self._app.open_exam_detail(result.exam, result.exam_file)
        self._app.start_reading_mode_for_current_exam()

    def open_selected_exam(self) -> None:
        """Open the exam selected in the overview, reporting a broken file instead of crashing.

        A structurally invalid exam (see `validate_regions`) or an
        unsupported legacy schema raises here; the user gets a clear error
        naming the file instead of an unhandled exception.
        """
        selected = self._app.get_selected_row()
        if selected is None:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Klausur auswählen.")
            return

        try:
            exam = self._deps.load_exam_usecase.execute(exam_file=selected.source_file)
        except Exception as exc:
            messagebox.showerror("Klausur fehlerhaft", f"'{selected.source_file.name}' konnte nicht geoeffnet werden:\n{exc}")
            return
        self._app.open_exam_detail(exam, selected.source_file)

    def delete_selected_exam(self) -> None:
        selected = self._app.get_selected_row()
        if selected is None:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Klausur auswählen.")
            return

        confirm = messagebox.askyesno(
            "Klausur loeschen",
            f"Klausur '{selected.exam_name}' wirklich loeschen?\nDie zugehoerige JSON-Datei wird entfernt.",
        )
        if not confirm:
            return

        try:
            snapshot_exam = self._deps.load_exam_usecase.execute(exam_file=selected.source_file)
        except Exception as exc:
            messagebox.showerror("Fehler", f"Klausur konnte nicht geladen werden: {exc}")
            return
        payload = snapshot_exam.to_dict()
        exam_file = selected.source_file

        try:
            self._deps.delete_exam_usecase.execute(exam_file=selected.source_file)
        except Exception as exc:
            messagebox.showerror("Fehler", f"Klausur konnte nicht geloescht werden: {exc}")
            return

        self._record_history_action(
            description=f"Klausur geloescht: {selected.exam_name}",
            undo=lambda: self._write_exam_payload(exam_file, payload),
            redo=lambda: exam_file.exists() and exam_file.unlink(),
        )

        self._app.on_exam_deleted(selected.exam_id)
        self.refresh_exam_overview()
        self._app.set_status("Klausur geloescht")

    def update_exam_index_dir(self, raw_path: str) -> Path | None:
        try:
            normalized = self._deps.settings_repository.normalize_exam_index_dir(raw_path)
        except Exception as exc:
            messagebox.showerror("Ungueltiger Pfad", str(exc))
            return None

        current = self._deps.exam_repository.index_root
        if normalized == current:
            self._app.set_status(f"JSON-Ablagepfad unveraendert: {normalized}")
            return normalized

        self._apply_exam_index_dir(normalized)
        self._record_history_action(
            description=f"JSON-Ablagepfad geaendert: {normalized}",
            undo=lambda: self._apply_exam_index_dir(current),
            redo=lambda: self._apply_exam_index_dir(normalized),
        )
        self._app.set_status(f"JSON-Ablagepfad aktualisiert: {normalized}")
        return normalized

    def save_score_immediate(
        self,
        *,
        exam: ExamProject,
        student_id: str,
        task_code: str,
        points_text: str,
        max_points_text: str,
    ) -> bool:
        if not task_code.strip():
            messagebox.showinfo("Hinweis", "Bitte zuerst einen Aufgaben-Code eintragen, z. B. A1.")
            return False

        try:
            points = float(points_text.replace(",", ".")) if points_text.strip() else 0.0
            max_points = float(max_points_text.replace(",", ".")) if max_points_text.strip() else 0.0
        except ValueError:
            messagebox.showerror("Ungültige Eingabe", "Punkte und Max-Punkte müssen Zahlen sein.")
            return False

        score_file = Path(exam.folder_path) / "korrektor_scores.csv"
        before_csv = self._read_text_or_none(score_file)

        self._deps.save_score_usecase.execute(
            exam=exam,
            student_id=student_id,
            task_code=task_code.strip(),
            points=points,
            max_points=max_points,
        )
        after_csv = self._read_text_or_none(score_file)
        if before_csv != after_csv:
            self._record_history_action(
                description=f"Punkte gesetzt: {task_code.strip()}",
                undo=lambda: self._restore_text(score_file, before_csv),
                redo=lambda: self._restore_text(score_file, after_csv),
            )
        self._app.set_status("Punkte sofort gespeichert")
        return True

    def load_saved_points(self, *, exam: ExamProject, student_id: str, task_code: str) -> str | None:
        score_file = Path(exam.folder_path) / "korrektor_scores.csv"
        if not score_file.exists():
            return None

        points_col = f"{task_code.strip()}_points"
        try:
            with score_file.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    if row.get("student_id", "").strip() != student_id:
                        continue
                    raw_points = str(row.get(points_col, "") or "").strip()
                    return raw_points or None
        except Exception:
            return None
        return None

    def load_saved_comment(self, *, exam: ExamProject, student_id: str, task_code: str) -> str | None:
        normalized_task = task_code.strip().upper()
        if not normalized_task:
            return None
        return exam.task_comments.get(student_id, {}).get(normalized_task)

    def set_task_comment_immediate(
        self,
        *,
        exam: ExamProject,
        student_id: str,
        task_code: str,
        comment_text: str,
    ) -> ExamProject | None:
        normalized_task = task_code.strip().upper()
        if not normalized_task:
            messagebox.showerror("Ungueltige Eingabe", "Aufgabencode fehlt.")
            return None

        if student_id not in {student.student_id for student in exam.students}:
            messagebox.showerror("Ungueltige Eingabe", "Unbekannte Person fuer Aufgabenkommentar.")
            return None

        valid_tasks = self._existing_task_codes(exam)
        if normalized_task not in valid_tasks:
            messagebox.showerror("Unbekannte Aufgabe", f"Aufgabe {normalized_task} existiert nicht.")
            return None

        normalized_comment = comment_text.strip()
        current_comment = exam.task_comments.get(student_id, {}).get(normalized_task, "")
        if current_comment == normalized_comment:
            return exam

        before_payload = exam.to_dict()

        if normalized_comment:
            by_student = exam.task_comments.setdefault(student_id, {})
            by_student[normalized_task] = normalized_comment
        else:
            by_student = exam.task_comments.get(student_id)
            if by_student is not None and normalized_task in by_student:
                del by_student[normalized_task]
                if not by_student:
                    del exam.task_comments[student_id]

        exam_file = self._deps.exam_repository.save_exam(exam)
        updated = self._deps.exam_repository.load_exam(exam_file)
        self._record_exam_payload_action(
            description=(
                f"Aufgabenkommentar gesetzt: {normalized_task}"
                if normalized_comment
                else f"Aufgabenkommentar entfernt: {normalized_task}"
            ),
            exam_id=updated.exam_id,
            before_payload=before_payload,
            after_payload=updated.to_dict(),
        )
        self.refresh_exam_overview()
        self._app.set_status(
            f"Kommentar gespeichert: {normalized_task}"
            if normalized_comment
            else f"Kommentar entfernt: {normalized_task}"
        )
        return updated

    def export_scores_for_exam(self, *, exam: ExamProject) -> bool:
        default_name = f"{exam.exam_name}_punkte_export.csv" if exam.exam_name.strip() else "punkte_export.csv"
        output_path_raw = filedialog.asksaveasfilename(
            title="Punkte exportieren",
            defaultextension=".csv",
            filetypes=[("CSV-Dateien", "*.csv"), ("Alle Dateien", "*.*")],
            initialdir=str(Path(exam.folder_path)),
            initialfile=default_name,
        )
        if not output_path_raw:
            return False

        output_path = Path(output_path_raw)
        try:
            self._deps.export_scores_usecase.execute(exam=exam, output_csv=output_path)
        except Exception as exc:
            messagebox.showerror("Export fehlgeschlagen", str(exc))
            return False

        self._app.set_status(f"Punkte exportiert: {output_path.name}")
        return True

    @staticmethod
    def _area_label_for_region(exam: ExamProject, region_id: str) -> str:
        """Resolve a region's display label for status/history messages.

        `region_id` stays the technical lookup key; this only affects text
        shown to the user, never how `PersonAreaCompletion` entries are matched.
        """
        region = next((item for item in exam.regions if item.region_id == region_id), None)
        if region is not None and region.assigned_area_codes:
            return region.assigned_area_codes[0]
        return region_id

    def is_person_area_finished(self, *, exam: ExamProject, student_id: str, region_id: str) -> bool:
        """Check whether the given student is marked finished for this region."""
        normalized_region_id = region_id.strip()
        if not normalized_region_id:
            return False
        return any(
            item.student_id == student_id and item.region_id == normalized_region_id and item.is_finished
            for item in exam.person_area_completions
        )

    def count_persons_area_finished(
        self, *, exam: ExamProject, region_id: str, student_ids: Sequence[str]
    ) -> int:
        """Count how many of the given students are marked finished for this region.

        Expects `student_ids` to already be a unique sequence (contract, not
        re-deduplicated here) — the same invariant `MainWindow._correction_region_student_ids()`
        establishes at its one canonical call site. Deliberately no defensive
        de-duplication here: the population is canonicalized at exactly one
        place, not re-guarded in every function that consumes it — otherwise
        different consumers could drift apart depending on whether (or how)
        each one deduplicates. A call with a list that contains duplicates
        therefore overcounts accordingly (each duplicate is counted again)
        — a documented contract violation by the calling side, not a bug in
        this method.

        One pass over `exam.person_area_completions` builds the finished-id
        set, then one pass over `student_ids` counts matches — O(Completions
        + Personen), not the O(N×M) full-CSV-per-cell cost that
        `load_saved_points` would incur if called once per person and task.
        """
        normalized_region_id = region_id.strip()
        if not normalized_region_id:
            return 0
        finished_ids = {
            item.student_id
            for item in exam.person_area_completions
            if item.region_id == normalized_region_id and item.is_finished
        }
        return sum(1 for student_id in student_ids if student_id in finished_ids)

    def set_persons_area_finished_immediate(
        self,
        *,
        exam: ExamProject,
        student_ids: Sequence[str],
        region_id: str,
        is_finished: bool,
    ) -> ExamProject | None:
        """Set/clear the finished flag for one or more student+region pairs, with undo/redo.

        Generalizes the former single-student `set_person_area_finished_immediate`:
        for `len(student_ids) == 1` behavior is unchanged byte-for-byte (same
        error messages, same status/history texts) — everything below only
        branches on the count to pick between the singular and plural text.

        Validation is all-or-nothing: `student_ids` is de-duplicated
        (`dict.fromkeys`, stable order) but never silently filtered down. If
        even one id is unknown, the *entire* call is rejected (no partial
        update, no `HistoryAction`) rather than proceeding with the known
        subset — `student_ids` always comes from
        `MainWindow._correction_region_student_ids()` internally, so an
        unknown id here signals an inconsistent program/data state, not a
        legitimate partial case worth a best-effort attempt.

        Unlike the read-only `count_persons_area_finished`, this method
        deliberately does de-duplicate its own input: it writes and creates
        a `HistoryAction`, so an accidental duplicate here must not distort
        the reported person count or do redundant work, whereas a miscount
        in a display-only counter is comparatively harmless.
        """
        normalized_region_id = region_id.strip()
        if not normalized_region_id:
            messagebox.showerror("Ungueltige Eingabe", "Bereich fehlt.")
            return None

        target_ids = list(dict.fromkeys(student_ids))
        if not target_ids:
            messagebox.showerror("Ungueltige Eingabe", "Keine Personen fuer Fertigstatus ausgewaehlt.")
            return None

        known_ids = {student.student_id for student in exam.students}
        unknown_ids = [student_id for student_id in target_ids if student_id not in known_ids]
        if unknown_ids:
            messagebox.showerror(
                "Ungueltige Eingabe",
                f"Unbekannte Person(en) fuer Fertigstatus: {', '.join(unknown_ids)}",
            )
            return None

        if normalized_region_id not in {region.region_id for region in exam.regions}:
            messagebox.showerror("Unbekannter Bereich", "Dieser Bereich existiert nicht (mehr).")
            return None

        area_label = self._area_label_for_region(exam, normalized_region_id)
        before_payload = exam.to_dict()
        target_id_set = set(target_ids)
        exam.person_area_completions = [
            item
            for item in exam.person_area_completions
            if not (item.student_id in target_id_set and item.region_id == normalized_region_id)
        ]
        if is_finished:
            exam.person_area_completions.extend(
                PersonAreaCompletion(student_id=student_id, region_id=normalized_region_id, is_finished=True)
                for student_id in target_ids
            )

        exam_file = self._deps.exam_repository.save_exam(exam)
        updated = self._deps.exam_repository.load_exam(exam_file)
        if len(target_ids) == 1:
            description = (
                f"Bereich als fertig markiert: {area_label}"
                if is_finished
                else f"Bereich als offen markiert: {area_label}"
            )
            status = (
                f"Fertigstatus aktualisiert: {area_label}"
                if is_finished
                else f"Fertigstatus entfernt: {area_label}"
            )
        else:
            description = (
                f"Bereich {area_label}: {len(target_ids)} Personen als fertig markiert"
                if is_finished
                else f"Bereich {area_label}: {len(target_ids)} Personen als offen markiert"
            )
            status = description
        self._record_exam_payload_action(
            description=description,
            exam_id=updated.exam_id,
            before_payload=before_payload,
            after_payload=updated.to_dict(),
        )
        self.refresh_exam_overview()
        self._app.set_status(status)
        return updated

    @staticmethod
    def _existing_standard_area_codes(exam: ExamProject) -> set[str]:
        return {
            code.strip().upper()
            for region in exam.regions
            for code in region.assigned_area_codes
            if code.strip()
        }

    @staticmethod
    def _existing_task_codes(exam: ExamProject) -> set[str]:
        return {
            task.code.strip().upper()
            for region in exam.regions
            for task in region.tasks
            if task.code.strip()
        }

    def upsert_region_immediate(
        self,
        *,
        exam: ExamProject,
        student_pdf: str,
        page_number: int,
        box: tuple[float, float, float, float],
        task_specs: list[tuple[str, float]],
        area_codes: list[str],
        region_id: str | None = None,
    ) -> ExamProject | None:
        if page_number > exam.standard_page_count:
            messagebox.showerror(
                "Ungültige Eingabe",
                "Im Extraseitenmodus koennen keine Aufgaben definiert werden. Bitte nur Bereich(e) zuordnen.",
            )
            return None

        before_payload = exam.to_dict()
        tasks = [
            TaskDefinition(code=code.strip().upper(), name=code.strip().upper(), max_points=max_points)
            for code, max_points in task_specs
            if code.strip()
        ]
        if not tasks:
            messagebox.showerror("Ungültige Eingabe", "Bitte mindestens eine Aufgabe mit Code und Punkten angeben.")
            return None

        if not area_codes:
            messagebox.showerror("Ungültige Eingabe", "Bitte mindestens einen Aufgabenbereich angeben, z. B. A.")
            return None

        region = RegionAssignment(
            region_id=region_id or f"r-{uuid4().hex[:12]}",
            student_pdf="",
            page_number=page_number,
            box=RegionBox(x0=box[0], y0=box[1], x1=box[2], y1=box[3]),
            tasks=tasks,
            assigned_area_codes=area_codes,
            is_read_complete=True,
            is_corrected=False,
            is_extra_page=False,
        )
        updated = self._deps.upsert_region_usecase.execute(exam=exam, region=region)
        self._record_exam_payload_action(
            description=f"Bereich gespeichert: {region.assigned_area_codes[0]}",
            exam_id=updated.exam_id,
            before_payload=before_payload,
            after_payload=updated.to_dict(),
        )
        self.refresh_exam_overview()
        self._app.set_status("Bereich sofort gespeichert")
        return updated

    def save_exam_immediate(self, *, exam: ExamProject) -> ExamProject:
        before_payload = exam.to_dict()
        exam_file = self._deps.exam_repository.save_exam(exam)
        updated = self._deps.exam_repository.load_exam(exam_file)
        self._record_exam_payload_action(
            description="Klausur gespeichert",
            exam_id=updated.exam_id,
            before_payload=before_payload,
            after_payload=updated.to_dict(),
        )
        self.refresh_exam_overview()
        self._app.set_status("Aenderungen sofort gespeichert")
        return updated

    def delete_region_immediate(self, *, exam: ExamProject, region_id: str) -> ExamProject:
        """Remove one region without touching any other region's identity.

        Previously this relabeled every remaining region's `assigned_area_codes`
        by list index, which silently rewrote other regions' visible labels
        (and, before the region_id migration, corrupted any stored reference
        keyed by that label) on every unrelated deletion. Area codes are now
        stable once assigned (see `_next_area_label`) and `region_id` is the
        only technical identity, so no relabeling is needed here.
        """
        before_payload = exam.to_dict()
        exam.regions = [region for region in exam.regions if region.region_id != region_id]
        exam_file = self._deps.exam_repository.save_exam(exam)
        updated = self._deps.exam_repository.load_exam(exam_file)
        self._record_exam_payload_action(
            description="Bereich geloescht",
            exam_id=updated.exam_id,
            before_payload=before_payload,
            after_payload=updated.to_dict(),
        )
        self.refresh_exam_overview()
        self._app.set_status("Bereich geloescht")
        return updated

    def delete_extra_page_assignment_immediate(self, *, exam: ExamProject, assignment_id: str) -> ExamProject:
        before_payload = exam.to_dict()
        exam.extra_page_assignments = [
            assignment for assignment in exam.extra_page_assignments if assignment.assignment_id != assignment_id
        ]
        exam_file = self._deps.exam_repository.save_exam(exam)
        updated = self._deps.exam_repository.load_exam(exam_file)
        self._record_exam_payload_action(
            description="Extraseiten-Zuordnung geloescht",
            exam_id=updated.exam_id,
            before_payload=before_payload,
            after_payload=updated.to_dict(),
        )
        self.refresh_exam_overview()
        self._app.set_status("Extraseiten-Zuordnung geloescht")
        return updated

    def finish_reading_mode(self, *, exam: ExamProject) -> ExamProject:
        before_payload = exam.to_dict()
        expected = set(range(1, exam.standard_page_count + 1))
        marked = {
            region.page_number
            for region in exam.regions
            if 1 <= region.page_number <= exam.standard_page_count
        }
        missing_pages = sorted(expected - marked)

        if missing_pages:
            joined = ", ".join(str(page) for page in missing_pages)
            proceed = messagebox.askyesno(
                "Unvollständiges Einlesen",
                f"Es fehlen noch Markierungen auf Standardseiten: {joined}.\nTrotzdem abschließen?",
            )
            if not proceed:
                return exam

        updated = self._deps.set_reading_complete_usecase.execute(exam=exam, is_complete=True)
        self._record_exam_payload_action(
            description="Einlesemodus abgeschlossen",
            exam_id=updated.exam_id,
            before_payload=before_payload,
            after_payload=updated.to_dict(),
        )
        self.refresh_exam_overview()
        self._app.set_status("Einlesemodus abgeschlossen")
        return updated

    def assign_extra_page_immediate(
        self,
        *,
        exam: ExamProject,
        student_pdf: str,
        page_number: int,
        box: tuple[float, float, float, float],
        area_codes: list[str],
        assignment_id: str | None = None,
    ) -> ExamProject | None:
        before_payload = exam.to_dict()
        normalized_areas = [code.strip().upper() for code in area_codes if code.strip()]
        if not normalized_areas:
            messagebox.showerror("Ungültige Eingabe", "Bitte mindestens einen Bereich angeben, z. B. A.")
            return None

        existing_areas = self._existing_standard_area_codes(exam)
        if not existing_areas:
            messagebox.showerror("Keine Bereiche", "Bitte zuerst Standardbereiche im Einlesemodus anlegen.")
            return None

        unknown = [code for code in normalized_areas if code not in existing_areas]
        if unknown:
            unknown_text = ", ".join(unknown)
            messagebox.showerror(
                "Unbekannter Bereich",
                f"Folgende Bereiche existieren nicht als Standardbereich: {unknown_text}",
            )
            return None

        existing = None
        if assignment_id is not None:
            existing = next(
                (item for item in exam.extra_page_assignments if item.assignment_id == assignment_id),
                None,
            )
        if existing is None:
            existing = next(
                (
                    assignment
                    for assignment in exam.extra_page_assignments
                    if assignment.student_pdf == student_pdf and assignment.page_number == page_number
                ),
                None,
            )

        assignment_id = existing.assignment_id if existing else f"x-{uuid4().hex[:10]}"
        assignment = ExtraPageAssignment(
            assignment_id=assignment_id,
            student_pdf=student_pdf,
            page_number=page_number,
            box=RegionBox(x0=box[0], y0=box[1], x1=box[2], y1=box[3]),
            assigned_area_codes=normalized_areas,
            is_read_complete=True,
            is_corrected=existing.is_corrected if existing else False,
        )

        replaced = False
        for index, item in enumerate(exam.extra_page_assignments):
            if item.assignment_id == assignment.assignment_id:
                exam.extra_page_assignments[index] = assignment
                replaced = True
                break
        if not replaced:
            exam.extra_page_assignments.append(assignment)

        exam_file = self._deps.exam_repository.save_exam(exam)
        updated = self._deps.exam_repository.load_exam(exam_file)
        self._record_exam_payload_action(
            description="Extraseite zugeordnet",
            exam_id=updated.exam_id,
            before_payload=before_payload,
            after_payload=updated.to_dict(),
        )
        self.refresh_exam_overview()
        self._app.set_status("Extraseite sofort zugeordnet")
        return updated

    def set_name_region_immediate(
        self,
        *,
        exam: ExamProject,
        box: tuple[float, float, float, float],
        page_number: int,
    ) -> ExamProject:
        """Persist the (single, shared) Namenmodus region immediately.

        Unlike a standard Aufgaben-Bereich, a name region needs no
        accompanying task/points input, so a drag commits directly here
        instead of going through a draft-then-save step. Any previous
        `name_region` is replaced outright (only one may exist); each
        replacement is its own undo/redo entry, since the region is
        meaningful configuration independent of whether names have been
        typed yet.
        """
        before_payload = exam.to_dict()
        exam.name_region = RegionBox(x0=box[0], y0=box[1], x1=box[2], y1=box[3])
        exam.name_region_page = page_number
        exam_file = self._deps.exam_repository.save_exam(exam)
        updated = self._deps.exam_repository.load_exam(exam_file)
        self._record_exam_payload_action(
            description="Namensbereich gesetzt",
            exam_id=updated.exam_id,
            before_payload=before_payload,
            after_payload=updated.to_dict(),
        )
        self.refresh_exam_overview()
        self._app.set_status("Namensbereich gespeichert")
        return updated

    @staticmethod
    def _rename_file(folder: Path, source_name: str, target_name: str) -> None:
        (folder / source_name).rename(folder / target_name)

    @classmethod
    def _apply_staged_renames(cls, folder: Path, pairs: list[tuple[str, str]]) -> None:
        """Rename every (old, new) filename pair via a unique temp name in between.

        Two phases (old -> temp, then temp -> new) so pairs that swap names
        (A->B and B->A in the same batch) never collide on an intermediate
        state. If any single rename in either phase fails, every rename
        already applied within this call is undone, in reverse order,
        before the original `OSError` is re-raised - the folder ends up
        exactly as it was before this call. This does not protect against a
        hard process/OS crash mid-call (see docs/ARCHITEKTUR.md); it only
        guarantees a clean rollback for errors raised during the call.
        """
        temp_by_old = {old: f"{old}.__rename_tmp_{uuid4().hex[:8]}__" for old, _new in pairs}
        applied: list[tuple[str, str]] = []

        def _rollback() -> None:
            for source, target in reversed(applied):
                try:
                    cls._rename_file(folder, target, source)
                except OSError:
                    pass

        try:
            for old, _new in pairs:
                temp = temp_by_old[old]
                cls._rename_file(folder, old, temp)
                applied.append((old, temp))
            for old, new in pairs:
                temp = temp_by_old[old]
                cls._rename_file(folder, temp, new)
                applied.append((temp, new))
        except OSError:
            _rollback()
            raise

    def rename_students_immediate(
        self,
        *,
        exam: ExamProject,
        name_by_student_id: dict[str, str],
    ) -> ExamProject | None:
        """Batch-rename every student's PDF from newly entered Namenmodus names.

        One rollback-capable operation: preflight (1:1 rename-set check,
        target-name planning, external-conflict check) -> staged physical
        rename -> in-memory exam update -> `save_exam` -> a single
        `HistoryAction`. A failure at any step reverts whatever was already
        applied, so the filesystem and the exam JSON never end up
        disagreeing about filenames (see docs/ARCHITEKTUR.md for the
        accepted crash-atomicity limitation). `student_id` is never
        touched - only `pdf_filename` (sanitized target) and `display_name`
        (the raw entered name, unmodified) change.
        """
        folder = Path(exam.folder_path)
        actual_pdf_filenames = {path.name for path in folder.glob("*.pdf")}

        set_errors = validate_rename_set(exam.students, actual_pdf_filenames)
        if set_errors:
            messagebox.showerror("Umbenennen nicht moeglich", "\n".join(set_errors))
            return None

        plan = plan_target_filenames(exam.students, name_by_student_id)
        if plan.errors:
            messagebox.showerror("Ungueltige Namen", "\n".join(plan.errors))
            return None

        rename_set_filenames = {student.pdf_filename for student in exam.students}
        external_conflicts = find_external_conflicts(
            plan.target_filename_by_student_id, actual_pdf_filenames, rename_set_filenames
        )
        if external_conflicts:
            messagebox.showerror("Umbenennen nicht moeglich", "\n".join(external_conflicts))
            return None

        rename_operations = [
            (student.student_id, student.pdf_filename, plan.target_filename_by_student_id[student.student_id])
            for student in exam.students
            if plan.target_filename_by_student_id[student.student_id] != student.pdf_filename
        ]
        if not rename_operations:
            messagebox.showinfo("Hinweis", "Keine Umbenennung noetig - alle Namen entsprechen bereits den Dateinamen.")
            return exam

        rename_pairs = [(old, new) for _sid, old, new in rename_operations]
        old_to_new = {old: new for old, new in rename_pairs}

        self._app.invalidate_doc_cache(old_to_new.keys())
        before_payload = exam.to_dict()

        try:
            self._apply_staged_renames(folder, rename_pairs)
        except OSError as exc:
            messagebox.showerror("Umbenennen fehlgeschlagen", f"Dateisystem-Fehler, keine Datei wurde veraendert: {exc}")
            return None

        for student in exam.students:
            new_filename = old_to_new.get(student.pdf_filename)
            if new_filename is None:
                continue
            student.display_name = name_by_student_id[student.student_id].strip()
            student.pdf_filename = new_filename
        for assignment in exam.extra_page_assignments:
            if assignment.student_pdf in old_to_new:
                assignment.student_pdf = old_to_new[assignment.student_pdf]
        for annotation in exam.pdf_annotations:
            if annotation.student_pdf in old_to_new:
                annotation.student_pdf = old_to_new[annotation.student_pdf]

        try:
            exam_file = self._deps.exam_repository.save_exam(exam)
            updated = self._deps.exam_repository.load_exam(exam_file)
        except Exception as exc:
            try:
                self._apply_staged_renames(folder, [(new, old) for old, new in rename_pairs])
            except OSError:
                pass
            messagebox.showerror(
                "Umbenennen fehlgeschlagen",
                f"Klausur konnte nicht gespeichert werden, Dateinamen wurden zurueckgesetzt: {exc}",
            )
            return None

        after_payload = updated.to_dict()
        exam_file_path = exam_file

        def _undo() -> None:
            self._app.invalidate_doc_cache(new for _old, new in rename_pairs)
            self._apply_staged_renames(folder, [(new, old) for old, new in rename_pairs])
            self._write_exam_payload(exam_file_path, before_payload)

        def _redo() -> None:
            self._app.invalidate_doc_cache(old for old, _new in rename_pairs)
            self._apply_staged_renames(folder, rename_pairs)
            self._write_exam_payload(exam_file_path, after_payload)

        self._record_history_action(
            description=f"{len(rename_operations)} Schueler:in(nen) umbenannt",
            undo=_undo,
            redo=_redo,
        )
        self.refresh_exam_overview()
        self._app.set_status(f"{len(rename_operations)} PDF(s) umbenannt")
        return updated

    def load_scores_for_exam(self, *, exam: ExamProject) -> dict[str, dict[str, float]]:
        """Load every recorded points value for `exam`, keyed by student_id then task_code.

        Thin pass-through to the score repository, used by the Supersymbol
        filter to evaluate a points condition across all students at once.
        """
        return self._deps.score_repository.load_scores(exam=exam)

