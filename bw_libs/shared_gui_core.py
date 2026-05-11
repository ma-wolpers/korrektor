"""Helpers to resolve shared bw-gui package paths in local and submodule layouts."""

from __future__ import annotations

from pathlib import Path
import sys


def _has_laufkern(candidate: Path) -> bool:
    """Return whether the candidate bw_gui package exposes laufkern."""

    package_root = candidate / "bw_gui"
    return (package_root / "laufkern").exists() or (package_root / "laufkern.py").exists()


def ensure_bw_gui_on_path() -> Path | None:
    """Ensure the shared bw-gui src directory is importable."""

    repo_root = Path(__file__).resolve().parents[1]
    candidates = (
        repo_root.parent / "bw-gui" / "src",
        repo_root.parent.parent / "bw-gui" / "src",
        repo_root / "bw-gui" / "src",
    )

    existing_candidates: list[Path] = []
    for candidate in candidates:
        if not candidate.exists():
            continue
        existing_candidates.append(candidate)
        if not _has_laufkern(candidate):
            continue
        candidate_str = str(candidate)
        if candidate_str not in sys.path:
            sys.path.insert(0, candidate_str)
        return candidate

    for candidate in existing_candidates:
        candidate_str = str(candidate)
        if candidate_str not in sys.path:
            sys.path.insert(0, candidate_str)
        return candidate

    return None
