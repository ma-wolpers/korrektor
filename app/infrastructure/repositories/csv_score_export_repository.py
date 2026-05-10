from __future__ import annotations

import csv
import os
from pathlib import Path

from app.core.domain.models import ExamProject
from app.core.ports.repositories import ScoreExportRepository


class CsvScoreExportRepository(ScoreExportRepository):
    def export_scores(
        self,
        *,
        exam: ExamProject,
        output_csv: Path,
    ) -> None:
        task_codes, task_max_points = self._ordered_task_codes_and_max_points(exam)

        source_scores = self._read_scores(Path(exam.folder_path) / "korrektor_scores.csv")
        header = ["student_id", "student_name", *task_codes]
        rows: list[dict[str, str]] = []

        max_row = {"student_id": "", "student_name": "MAX"}
        for task_code in task_codes:
            max_row[task_code] = f"{task_max_points.get(task_code, 0.0):g}"
        rows.append(max_row)

        for student in exam.students:
            source_row = source_scores.get(student.student_id, {})
            row = {
                "student_id": student.student_id,
                "student_name": student.display_name,
            }
            for task_code in task_codes:
                row[task_code] = str(source_row.get(f"{task_code}_points", "") or "").strip()
            rows.append(row)

        self._atomic_write(output_csv, header, rows)

    @staticmethod
    def _ordered_task_codes_and_max_points(exam: ExamProject) -> tuple[list[str], dict[str, float]]:
        ordered_codes: list[str] = []
        max_points_by_code: dict[str, float] = {}
        for region in exam.regions:
            for task in region.tasks:
                code = task.code.strip().upper()
                if not code:
                    continue
                if code not in max_points_by_code:
                    ordered_codes.append(code)
                    max_points_by_code[code] = float(task.max_points)
        return ordered_codes, max_points_by_code

    @staticmethod
    def _read_scores(csv_path: Path) -> dict[str, dict[str, str]]:
        if not csv_path.exists():
            return {}
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            return {
                str(row.get("student_id", "") or "").strip(): row
                for row in reader
                if str(row.get("student_id", "") or "").strip()
            }

    @staticmethod
    def _atomic_write(output_csv: Path, header: list[str], rows: list[dict[str, str]]) -> None:
        output_csv.parent.mkdir(parents=True, exist_ok=True)
        temp_path = output_csv.with_suffix(output_csv.suffix + ".tmp")
        with temp_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=header)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        os.replace(temp_path, output_csv)
