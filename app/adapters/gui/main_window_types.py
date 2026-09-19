from __future__ import annotations

from dataclasses import dataclass

from app.core.domain.models import TaskDefinition


@dataclass(slots=True)
class DraftRegion:
    draft_id: str
    student_pdf: str
    page_number: int
    box: tuple[float, float, float, float]
    area_codes: list[str]
    task_specs: list[tuple[str, float]]


@dataclass(slots=True)
class CorrectionTemplate:
    """One region as used by Korrekturmodus.

    `region_id` is the stable technical identity (matches
    `RegionAssignment.region_id`) and is the key used in
    `MainWindow._correction_templates`. `area_code` is only the current
    human-visible label for that region — used for the Bereich-Auswahl UI
    and status text, never as a lookup key.
    """

    region_id: str
    area_code: str
    page_number: int
    box: tuple[float, float, float, float]
    tasks: list[TaskDefinition]
