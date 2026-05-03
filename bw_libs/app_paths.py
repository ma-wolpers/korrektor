"""Shared app path discovery and atomic write helpers."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any


@dataclass(frozen=True)
class AppPaths:
    """Resolved data directory information for one application."""

    app_name: str
    data_dir: Path
    portable_root: Path | None = None

    @classmethod
    def discover(
        cls,
        app_name: str,
        portable_markers: tuple[str, ...] = (".portable",),
        start_dir: Path | None = None,
    ) -> "AppPaths":
        """Discover data directory using portable marker or platform defaults."""

        if not app_name or not app_name.strip():
            raise ValueError("app_name must be a non-empty string")

        base_dir = (start_dir or Path.cwd()).resolve()
        portable_root = _find_portable_root(base_dir, portable_markers)
        if portable_root is not None:
            data_dir = portable_root / ".appdata" / app_name
        else:
            data_dir = _default_data_dir(app_name)

        data_dir.mkdir(parents=True, exist_ok=True)
        return cls(app_name=app_name, data_dir=data_dir, portable_root=portable_root)


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    """Write text atomically by replacing the target with a temp file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = f"{path.suffix}.tmp" if path.suffix else ".tmp"
    with NamedTemporaryFile(
        "w",
        delete=False,
        encoding=encoding,
        dir=str(path.parent),
        suffix=suffix,
    ) as handle:
        handle.write(text)
        temp_path = Path(handle.name)
    temp_path.replace(path)


def atomic_write_json(
    path: Path,
    payload: dict[str, Any],
    *,
    ensure_ascii: bool = False,
    indent: int = 2,
) -> None:
    """Serialize and write JSON payload atomically."""

    content = json.dumps(payload, ensure_ascii=ensure_ascii, indent=indent)
    atomic_write_text(path, content, encoding="utf-8")


def _find_portable_root(start: Path, markers: tuple[str, ...]) -> Path | None:
    current = start
    while True:
        for marker in markers:
            if marker and (current / marker).exists():
                return current
        if current.parent == current:
            return None
        current = current.parent


def _default_data_dir(app_name: str) -> Path:
    normalized_name = app_name.strip()
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / normalized_name
    return Path.home() / f".{normalized_name.lower()}"
