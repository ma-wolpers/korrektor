"""Helpers to resolve shared bw-gui package paths in local and submodule layouts."""

from __future__ import annotations

from pathlib import Path
import sys


def ensure_bw_gui_on_path() -> Path | None:
    """Ensure the shared bw-gui src directory is importable."""

    repo_root = Path(__file__).resolve().parents[1]
    candidates = (
        repo_root / "bw-gui" / "src",
        repo_root.parent / "bw-gui" / "src",
    )

    for candidate in candidates:
        if not candidate.exists():
            continue
        candidate_str = str(candidate)
        if candidate_str not in sys.path:
            sys.path.insert(0, candidate_str)
        return candidate

    return None
