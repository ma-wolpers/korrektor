from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ExamOverviewRow:
    exam_id: str
    exam_name: str
    reading_percent: float
    correction_percent: float
    region_count: int
    corrected_region_count: int
    reading_complete: bool
    has_open_flags: bool
    source_file: Path
