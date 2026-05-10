from __future__ import annotations

import csv
import copy
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from bw_libs.app_paths import atomic_write_text
from app.adapters.bootstrap.wiring import GuiDependencies
from app.adapters.gui.dialog_services import filedialog, messagebox, simpledialog
from app.adapters.gui.view_models import ExamOverviewRow
from app.adapters.undo import HistoryAction
from app.core.domain.models import ExamProject, ExtraPageAssignment, RegionAssignment, RegionBox, TaskDefinition
from app.infrastructure.repositories.file_utils import atomic_write_json

if TYPE_CHECKING:
    from app.adapters.gui.main_window import MainWindow


class UiIntentController:
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

    @staticmethod
    def _index_to_area_label(index: int) -> str:
        letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        result = ""
        value = index
        while True:
            value, remainder = divmod(value, 26)
            result = letters[remainder] + result
            if value == 0:
                break
            value -= 1
        return result

    def _record_exam_payload_action(
        self,
        *,
        description: str,
        exam_id: str,
        before_payload: dict[str, object],
        after_payload: dict[str, object],
    ) -> None:
        exam_file = self._deps.exam_repository.index_root / f"{exam_id}.json"
        before_copy = copy.deepcopy(before_payload)
        after_copy = copy.deepcopy(after_payload)

        self._record_history_action(
            description=description,
            undo=lambda: self._write_exam_payload(exam_file, before_copy),
            redo=lambda: self._write_exam_payload(exam_file, after_copy),
        )

    def _apply_exam_index_dir(self, target: Path) -> None:
        self._deps.settings_repository.save_exam_index_dir(target)
        self._deps.exam_repository.set_index_root(target)
        self._app.on_exam_index_dir_changed(target)
        self.refresh_exam_overview()

    def refresh_exam_overview(self) -> None:
        overviews = self._deps.list_exams_usecase.execute()
        by_id = {item.exam_id: item for item in overviews}

        rows: list[ExamOverviewRow] = []
        for exam_file in self._deps.exam_repository.list_exam_files():
            exam = self._deps.exam_repository.load_exam(exam_file)
            item = by_id.get(exam.exam_id)
            if item is None:
                continue
            rows.append(
                ExamOverviewRow(
                    exam_id=exam.exam_id,
                    exam_name=exam.exam_name,
                    reading_percent=item.reading_percent,
                    correction_percent=item.correction_percent,
                    region_count=item.region_count,
                    corrected_region_count=item.corrected_region_count,
                    reading_complete=item.reading_complete,
                    has_open_flags=item.has_unassigned_extra_pages or item.has_missing_page_markings,
                    source_file=exam_file,
                )
            )
        self._app.render_overview_rows(rows)

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

        payload = copy.deepcopy(result.exam.to_dict())
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
        selected = self._app.get_selected_row()
        if selected is None:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Klausur auswählen.")
            return

        exam = self._deps.load_exam_usecase.execute(exam_file=selected.source_file)
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
        payload = copy.deepcopy(snapshot_exam.to_dict())
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

    @staticmethod
    def _existing_standard_area_codes(exam: ExamProject) -> set[str]:
        return {
            code.strip().upper()
            for region in exam.regions
            for code in region.assigned_area_codes
            if code.strip()
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

        before_payload = copy.deepcopy(exam.to_dict())
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
        before_payload = copy.deepcopy(exam.to_dict())
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
        before_payload = copy.deepcopy(exam.to_dict())
        exam.regions = [region for region in exam.regions if region.region_id != region_id]
        ordered = list(exam.regions)
        for idx, region in enumerate(ordered):
            code = self._index_to_area_label(idx)
            region.assigned_area_codes = [code]
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
        before_payload = copy.deepcopy(exam.to_dict())
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
        before_payload = copy.deepcopy(exam.to_dict())
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
    ) -> ExamProject | None:
        before_payload = copy.deepcopy(exam.to_dict())
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
