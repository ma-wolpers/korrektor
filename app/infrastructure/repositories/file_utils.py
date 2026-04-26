from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def atomic_write_json(file_path: Path, payload: dict[str, Any]) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temp_file = file_path.with_suffix(file_path.suffix + ".tmp")
    with temp_file.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    os.replace(temp_file, file_path)


def slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "klausur"
