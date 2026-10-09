"""Exam data schema v1 -> v2 on the raw JSON dict (pure, idempotent).

v1: tasks inside each region (``regions[*].tasks``), whole-page
``extra_page_assignments`` pointing to region *labels*, "Fertig" per region
(``person_area_completions``). v2 (`SCHEMA_VERSION`): exam-wide ``tasks``,
regions with ``task_codes`` (Superseiten or Einzelseiten), "Fertig" per task
(``person_task_completions``).

Steps (binding):

1. Collect every region's tasks into ``tasks`` - codes canonicalised
   (``strip().upper()``) *before* duplicates are compared; the first
   definition of a code wins; natural order.
2. ``regions[*].task_codes`` = the region's canonical codes; ``tasks`` and
   ``is_extra_page`` are dropped from the region.
3. Every extra-page assignment becomes an Einzelseiten-Bereich with the
   **same id** (marks referencing it stay valid), its box, and the union of
   the task codes of the labels it referenced, plus a fresh unique label.
   GRENZE: an assignment whose labels resolve to no task is dropped (the old
   GUI rejected unknown labels, so this does not occur in practice).
4. Marks without ``region_id`` (legacy) get the id of the one Superseiten-
   Bereich on their page whose box contains them; ambiguous or unresolvable
   marks stay untouched.
5. Each "Fertig" per region becomes one entry per task of that region.

Data with ``schema_version == 2`` is returned unchanged, so a second run is a
no-op. Saving writes v2 without ``extra_page_assignments``; older Korrektor
versions therefore reject such files loudly ("Unsupported exam schema").
"""

from __future__ import annotations

from typing import Any

from app.core.domain.models import SCHEMA_VERSION
from app.core.domain.task_regions import next_free_label
from app.core.domain.task_spec import task_sort_key


def migrate_v1_tasks(raw: dict[str, Any]) -> dict[str, Any]:
    """Upgrade ``raw`` to schema v2 in place and return it.

    Only data *without* ``schema_version`` is v1. v2 is returned unchanged;
    any other (e.g. future) version is also left untouched, so
    `ExamProject.from_dict` rejects it instead of it being "downgraded".
    """
    if "schema_version" in raw:
        return raw
    regions = [region for region in raw.get("regions", []) if isinstance(region, dict)]
    tasks: dict[str, dict[str, Any]] = {}
    codes_by_label: dict[str, list[str]] = {}
    codes_by_region: dict[str, list[str]] = {}
    for region in regions:
        codes: list[str] = []
        for task in region.pop("tasks", []) or []:
            code = str(task.get("code", "")).strip().upper()
            if not code or code in codes:
                continue
            codes.append(code)
            tasks.setdefault(code, {"code": code, "name": str(task.get("name", "")).strip() or code, "max_points": float(task.get("max_points", 0.0))})
        region.pop("is_extra_page", None)
        region["task_codes"] = codes
        codes_by_region[str(region.get("region_id", "")).strip()] = codes
        for label in region.get("assigned_area_codes", []) or []:
            codes_by_label.setdefault(str(label).strip().upper(), codes)

    used_labels = {str(label).strip().upper() for region in regions for label in (region.get("assigned_area_codes") or [])[:1]}
    for assignment in raw.pop("extra_page_assignments", []) or []:
        codes = []
        for label in assignment.get("assigned_area_codes", []) or []:
            for code in codes_by_label.get(str(label).strip().upper(), []):
                if code not in codes:
                    codes.append(code)
        if not codes:
            continue
        label = next_free_label(used_labels)
        used_labels.add(label)
        region_id = str(assignment.get("assignment_id") or assignment.get("region_id") or "").strip()
        regions.append({
            "region_id": region_id or f"x-{len(regions)}-{label}",
            "student_pdf": str(assignment.get("student_pdf", "")).strip(),
            "page_number": int(assignment.get("page_number", 1)),
            "box": assignment.get("box", {}),
            "task_codes": codes,
            "assigned_area_codes": [label],
            "is_read_complete": bool(assignment.get("is_read_complete", True)),
            "is_corrected": bool(assignment.get("is_corrected", False)),
        })
    raw["regions"] = regions
    raw["tasks"] = sorted(tasks.values(), key=lambda task: task_sort_key(task["code"]))
    _resolve_marks_without_region(raw.get("pdf_annotations"), regions)
    raw["person_task_completions"] = _completions_per_task(raw.pop("person_area_completions", []) or [], codes_by_region)
    raw["schema_version"] = SCHEMA_VERSION
    return raw


def _resolve_marks_without_region(marks: Any, regions: list[dict[str, Any]]) -> None:
    """Step 4: give legacy marks without ``region_id`` the unique Superseiten-Bereich containing them."""
    if not isinstance(marks, list):
        return
    for mark in marks:
        if not isinstance(mark, dict) or str(mark.get("region_id", "")).strip():
            continue
        x, y, page = float(mark.get("x", 0.0)), float(mark.get("y", 0.0)), int(mark.get("page_number", 0))
        hits = [
            region["region_id"]
            for region in regions
            if not region.get("student_pdf") and int(region.get("page_number", 0)) == page and _contains(region.get("box", {}), x, y)
        ]
        if len(hits) == 1:
            mark["region_id"] = hits[0]


def _contains(box: dict[str, Any], x: float, y: float) -> bool:
    """Whether the raw box dict contains the point ``(x, y)`` (edges included)."""
    return float(box.get("x0", 0)) <= x <= float(box.get("x1", 0)) and float(box.get("y0", 0)) <= y <= float(box.get("y1", 0))


def _completions_per_task(completions: list[Any], codes_by_region: dict[str, list[str]]) -> list[dict[str, Any]]:
    """Step 5: one entry per (student, task); finished wins if several regions disagree."""
    merged: dict[tuple[str, str], bool] = {}
    for item in completions:
        if not isinstance(item, dict):
            continue
        student_id = str(item.get("student_id", "")).strip()
        for code in codes_by_region.get(str(item.get("region_id", "")).strip(), []):
            if student_id:
                merged[(student_id, code)] = merged.get((student_id, code), False) or bool(item.get("is_finished", True))
    return [{"student_id": student, "task_code": code, "is_finished": finished} for (student, code), finished in merged.items()]
