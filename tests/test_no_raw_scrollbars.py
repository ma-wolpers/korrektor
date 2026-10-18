"""Architektur-Guard: Scrollbars nur über die bw-gui-Primitive (SCROLLABILITY_CONTRACT).

``tui.Scrollbar`` (``bw_gui.runtime.widgets.Scrollbar``) ist die native, schlanke
Scrollbar, die dem Theme selbst folgt (Darkmode unter Windows). Rohe
``ttk``/``tk``/``ui.Scrollbar`` müsste die App wieder selbst einfärben. Die Prüfung
liegt zentral in bw_gui.testing.scrollbar_guard.
"""

from __future__ import annotations

from pathlib import Path

from bw_gui.testing.scrollbar_guard import RULE, find_offenders

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_app_uses_no_raw_scrollbars():
    offenders = find_offenders(REPO_ROOT / "app")
    assert offenders == {}, f"{RULE} Fundstellen: {offenders}"
