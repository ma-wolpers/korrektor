from __future__ import annotations

import csv
import os
from pathlib import Path

from app.core.domain.models import ExamProject
from app.core.ports.repositories import ScoreRepository


class CsvScoreRepository(ScoreRepository):
    BASE_HEADER = ["student_id", "student_name"]

    def save_score(
        self,
        *,
        exam: ExamProject,
        student_id: str,
        task_code: str,
        points: float,
        max_points: float,
    ) -> None:
        csv_path = Path(exam.folder_path) / "korrektor_scores.csv"
        rows, task_columns = self._read_rows(csv_path)

        student_name = next((s.display_name for s in exam.students if s.student_id == student_id), student_id)

        points_col = f"{task_code}_points"
        max_col = f"{task_code}_max"
        if points_col not in task_columns:
            task_columns.append(points_col)
        if max_col not in task_columns:
            task_columns.append(max_col)

        updated = False
        for row in rows:
            if row["student_id"] == student_id:
                row["student_name"] = student_name
                row[points_col] = f"{points:.2f}"
                row[max_col] = f"{max_points:.2f}"
                updated = True
                break

        if not updated:
            new_row = {
                "student_id": student_id,
                "student_name": student_name,
            }
            for column in task_columns:
                new_row[column] = ""
            new_row[points_col] = f"{points:.2f}"
            new_row[max_col] = f"{max_points:.2f}"
            rows.append(
                new_row
            )

        self._atomic_write(csv_path, rows, task_columns)

    def _read_rows(self, csv_path: Path) -> tuple[list[dict[str, str]], list[str]]:
        if not csv_path.exists():
            return [], []
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
            fieldnames = list(reader.fieldnames or [])
            task_columns = [name for name in fieldnames if name not in self.BASE_HEADER]
            return rows, task_columns

    def _atomic_write(self, csv_path: Path, rows: list[dict[str, str]], task_columns: list[str]) -> None:
        header = self.BASE_HEADER + sorted(task_columns)
        temp_file = csv_path.with_suffix(".tmp")
        with temp_file.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=header)
            writer.writeheader()
            for row in rows:
                for column in header:
                    row.setdefault(column, "")
                writer.writerow(row)
        os.replace(temp_file, csv_path)
