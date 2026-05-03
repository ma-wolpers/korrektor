from __future__ import annotations

from pathlib import Path
from typing import Any

from bw_libs.app_paths import atomic_write_json as _shared_atomic_write_json


def atomic_write_json(file_path: Path, payload: dict[str, Any]) -> None:
    _shared_atomic_write_json(file_path, payload)


def slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "klausur"
