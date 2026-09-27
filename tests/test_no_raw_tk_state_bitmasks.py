"""Architektur-Guard: die App interpretiert Tk-Modifierbits (``event.state``) nicht selbst.

Prüflogik zentral in bw-gui (``bw_gui.testing.tk_state_guard``), keine Kopie pro Repo.
Hintergrund: unter Windows ist ``0x0008`` NumLock, nicht Alt.
"""

from __future__ import annotations

from pathlib import Path

from bw_gui.testing.tk_state_guard import RULE, find_offenders

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_app_does_not_interpret_tk_state_bits():
    offenders = find_offenders(REPO_ROOT / "app")
    assert offenders == {}, f"{RULE} Fundstellen: {offenders}"
