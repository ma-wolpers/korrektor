from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from app.adapters.bootstrap.wiring import GuiDependencies
from app.adapters.gui.dialog_services import filedialog, messagebox, simpledialog
from app.adapters.gui.view_models import ExamOverviewRow
from app.core.domain.models import ExamProject, RegionAssignment, RegionBox, TaskDefinition

if TYPE_CHECKING:
    from app.adapters.gui.main_window import MainWindow


class UiIntentController:
    def __init__(self, app: "MainWindow", deps: GuiDependencies) -> None:
        self._app = app
        self._deps = deps

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

        self._deps.save_score_usecase.execute(
            exam=exam,
            student_id=student_id,
            task_code=task_code.strip(),
            points=points,
            max_points=max_points,
        )
        self._app.set_status("Punkte sofort gespeichert")
        return True

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
            student_pdf=student_pdf,
            page_number=page_number,
            box=RegionBox(x0=box[0], y0=box[1], x1=box[2], y1=box[3]),
            tasks=tasks,
            assigned_area_codes=area_codes,
            is_read_complete=True,
            is_corrected=False,
            is_extra_page=page_number > exam.standard_page_count,
        )
        updated = self._deps.upsert_region_usecase.execute(exam=exam, region=region)
        self.refresh_exam_overview()
        self._app.set_status("Bereich sofort gespeichert")
        return updated

    def save_exam_immediate(self, *, exam: ExamProject) -> ExamProject:
        self._deps.exam_repository.save_exam(exam)
        self.refresh_exam_overview()
        self._app.set_status("Aenderungen sofort gespeichert")
        return exam

    def delete_region_immediate(self, *, exam: ExamProject, region_id: str) -> ExamProject:
        exam.regions = [region for region in exam.regions if region.region_id != region_id]
        self._deps.exam_repository.save_exam(exam)
        self.refresh_exam_overview()
        self._app.set_status("Bereich geloescht")
        return exam

    def finish_reading_mode(self, *, exam: ExamProject) -> ExamProject:
        expected = set(range(1, exam.standard_page_count + 1))
        marked = {
            region.page_number
            for region in exam.regions
            if not region.is_extra_page and 1 <= region.page_number <= exam.standard_page_count
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
        normalized_areas = [code.strip().upper() for code in area_codes if code.strip()]
        if not normalized_areas:
            messagebox.showerror("Ungültige Eingabe", "Bitte mindestens einen Bereich angeben, z. B. A.")
            return None

        existing = next(
            (
                region
                for region in exam.regions
                if region.is_extra_page and region.student_pdf == student_pdf and region.page_number == page_number
            ),
            None,
        )

        region_id = existing.region_id if existing else f"r-extra-{uuid4().hex[:10]}"
        region = RegionAssignment(
            region_id=region_id,
            student_pdf=student_pdf,
            page_number=page_number,
            box=RegionBox(x0=box[0], y0=box[1], x1=box[2], y1=box[3]),
            tasks=existing.tasks if existing else [],
            assigned_area_codes=normalized_areas,
            is_read_complete=True,
            is_corrected=existing.is_corrected if existing else False,
            is_extra_page=True,
        )

        updated = self._deps.upsert_region_usecase.execute(exam=exam, region=region)
        self.refresh_exam_overview()
        self._app.set_status("Extraseite sofort zugeordnet")
        return updated
