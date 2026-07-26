"""Bootstrap helper that adds the shared bw-gui library to Python's import path.

THIS FILE IS NOT THE LIBRARY. It is a bootstrap helper.

bw-gui (the actual GUI library) lives at a fixed location on this machine:
  c:\Users\7thpl\Desktop\Code\bw-gui

This file's only job is to find that directory and add its src/ folder to
sys.path so that "import bw_gui" works regardless of how the program is launched
(from an IDE, from the terminal, or as a double-clicked .pyw file).

HOW IT WORKS:
  1. It looks for bw-gui/src/ as a sibling of this program's root directory
     (e.g. Desktop/Code/bw-gui/src — the expected and normal location).
  2. If not found there, it tries one level higher (for nested repo layouts).
  3. As a last resort, it looks inside the program itself for a local copy
     (this is the stale-copy fallback; do not rely on it).

A valid bw-gui installation must contain the "laufkern" subpackage. If no valid
installation is found, ensure_bw_gui_on_path() returns None without raising.

DO NOT MODIFY THIS FILE. It is a standard bootstrap helper shared across all
Blattwerk-family programs. If the bw-gui path has changed, update the
directory layout instead.

Usage (call once at program startup, before any bw_gui imports):

    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "bw_libs"))
    from shared_gui_core import ensure_bw_gui_on_path
    ensure_bw_gui_on_path()

    # Now bw_gui is importable:
    from bw_gui import BwBaseWindow
"""

from __future__ import annotations

from pathlib import Path
import sys


def _has_laufkern(candidate: Path) -> bool:
    """Return True if the candidate src/ directory contains a valid bw_gui package.

    Checks for the presence of the laufkern subpackage, which is the minimum
    signal that this is the current bw-gui installation (not an old local copy).

    Args:
        candidate: A Path pointing to a bw-gui/src/ directory.

    Returns:
        True if bw_gui/laufkern exists under this candidate.
    """
    package_root = candidate / "bw_gui"
    return (package_root / "laufkern").exists() or (package_root / "laufkern.py").exists()


def ensure_bw_gui_on_path() -> Path | None:
    """Add the shared bw-gui src/ directory to sys.path if not already present.

    Searches three candidate locations in priority order:
      1. Sibling directory: <program_root>/../bw-gui/src/  (expected location)
      2. Grandparent sibling: <program_root>/../../bw-gui/src/  (nested layouts)
      3. Local copy fallback: <program_root>/bw-gui/src/  (stale copy — deprecated)

    Among candidates that exist on disk, prefers the first one that contains a
    valid bw_gui package with laufkern. Falls back to the first existing candidate
    if none has laufkern.

    Returns:
        The Path of the bw-gui src/ directory that was added to sys.path,
        or None if no candidate was found.
    """
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
