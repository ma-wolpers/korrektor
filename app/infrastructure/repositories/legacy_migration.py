from __future__ import annotations

from typing import Any
from uuid import uuid4


def migrate_legacy_area_code_references(raw: dict[str, Any]) -> dict[str, Any]:
    """Upgrade a raw exam JSON dict from the legacy area_code-keyed schema.

    Runs on the raw dict, before `ExamProject.from_dict` ever sees it, and
    closes two independent legacy gaps:

    1. A region missing `region_id` gets a fresh one assigned in place. This
       is always safe: an empty id was never a valid reference target, so
       nothing that depended on it can be broken by giving it one now.
    2. `person_area_completions`/`pdf_annotations` entries that still carry
       the legacy `area_code` key (and no `region_id` yet) are rewritten to
       reference `region_id` instead — but only where every region's primary
       `assigned_area_codes[0]` label is unambiguous. If two regions share a
       label, migrating a reference to either one would be a guess; such
       entries are left as-is, so `ExamProject.from_dict` plus
       `validate_regions` reject the exam with a clear error afterwards
       instead of silently attributing history to the wrong region.
    """
    regions = raw.get("regions")
    if isinstance(regions, list):
        for region in regions:
            if isinstance(region, dict) and not str(region.get("region_id", "")).strip():
                region["region_id"] = f"r-{uuid4().hex[:12]}"

    label_to_region_id = _build_unambiguous_label_map(regions if isinstance(regions, list) else [])
    _migrate_legacy_entries(raw.get("person_area_completions"), label_to_region_id)
    _migrate_legacy_entries(raw.get("pdf_annotations"), label_to_region_id)
    return raw


def _build_unambiguous_label_map(regions: list[Any]) -> dict[str, str]:
    label_to_region_id: dict[str, str] = {}
    ambiguous_labels: set[str] = set()
    for region in regions:
        if not isinstance(region, dict):
            continue
        codes = region.get("assigned_area_codes")
        region_id = str(region.get("region_id", "")).strip()
        if not isinstance(codes, list) or not codes or not region_id:
            continue
        label = str(codes[0]).strip().upper()
        if not label:
            continue
        existing = label_to_region_id.get(label)
        if existing is not None and existing != region_id:
            ambiguous_labels.add(label)
        else:
            label_to_region_id[label] = region_id
    for label in ambiguous_labels:
        label_to_region_id.pop(label, None)
    return label_to_region_id


def _migrate_legacy_entries(entries: Any, label_to_region_id: dict[str, str]) -> None:
    if not isinstance(entries, list):
        return
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("region_id", "")).strip():
            continue
        legacy_label = str(entry.get("area_code", "")).strip().upper()
        if not legacy_label:
            continue
        region_id = label_to_region_id.get(legacy_label)
        if region_id:
            entry["region_id"] = region_id
