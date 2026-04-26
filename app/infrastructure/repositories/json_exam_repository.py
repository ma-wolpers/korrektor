from __future__ import annotations

import json
from pathlib import Path

from app.core.domain.models import ExamProject, utc_now_iso
from app.core.ports.repositories import ExamRepository
from app.infrastructure.repositories.file_utils import atomic_write_json


class JsonExamRepository(ExamRepository):
    def __init__(self, index_root: Path) -> None:
        self._index_root = index_root
        self._index_root.mkdir(parents=True, exist_ok=True)

    def list_exam_files(self) -> list[Path]:
        return sorted(self._index_root.glob("*.json"))

    def load_exam(self, exam_file: Path) -> ExamProject:
        with exam_file.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        return ExamProject.from_dict(raw)

    def save_exam(self, exam: ExamProject) -> Path:
        exam.updated_at = utc_now_iso()
        target = self._index_root / f"{exam.exam_id}.json"
        atomic_write_json(target, exam.to_dict())
        return target
